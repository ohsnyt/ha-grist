"""Forecast Solar integration utilities for Home Assistant.

This module provides the ForecastSolar class, which manages the retrieval, storage,
and processing of solar PV forecast data from the Forecast.Solar API for use in the
Grist integration. It supports multiple panel configurations, handles API rate limits,
and provides mock data for testing and development.

Key Features:
- Fetches and aggregates hourly PV forecasts for all configured solar panels.
- Stores and loads forecast data using Home Assistant's async storage helpers.
- Handles API rate limiting and provides mock data for development/testing.
- Provides methods to access forecasts for specific dates and all available data.
- Cleans up outdated forecast data based on a configurable retention period.

Classes:
    ForecastSolar: Manages Forecast.Solar API data, storage, and access for Grist.

Functions:
    generate_day_data: Generates mock hourly PV data for a given day based on sunrise and sunset times.

All I/O is asynchronous and compatible with Home Assistant's async patterns.
Logging follows Home Assistant conventions and respects the DEBUGGING flag.
"""

from datetime import datetime, timedelta
import json
import logging
from zoneinfo import ZoneInfo

import aiohttp
import anyio
from astral import LocationInfo
from astral.sun import sun

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ..const import (  # noqa: TID252
    CORE_CONFIG_STORAGE,
    CORE_ENERGY_STORAGE,
    CORE_FORECAST_FILTER,
    DATE_FORMAT,
    DEBUGGING,
    DEFAULT_PV_MAX_DAYS,
    FORECAST_KEY,
    FORECAST_SOLAR_API_URL,
    HRS_PER_DAY,
    PURPLE,
    RESET,
    STORAGE_VERSION,
    Status,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUGGING else logging.INFO)

# Testing flag. Set to True to use mock data instead of the API.
USE_MOCK_DATA = False


class ForecastSolar:
    """Utility class for managing and updating Forecast Solar data in Home Assistant.

    Handles multiple solar panel configurations, aggregates hourly forecasts,
    manages storage, and provides access to forecast data for the Grist integration.
    """

    # Constructor for ForecastSolar class.
    def __init__(
        self, hass: HomeAssistant) -> None:
        """Initialize ForecastSolar with Home Assistant instance and update hour.

        Args:
            hass: The Home Assistant instance.

        """
        # General info
        self.hass = hass
        self.timezone: str = hass.config.time_zone
        self._forecast: dict[
            str, dict[int, int]
        ] = {}  # Dictionary to hold the forecast data
        self._status = Status.NOT_CONFIGURED
        self._unsub_update = None
        self._next_update = dt_util.now() + timedelta(minutes=-1)
        self._panel_configurations = {}
        self._name = "Forecast Solar"

        # Initialize storage
        self._store = Store(hass, STORAGE_VERSION, FORECAST_KEY)

    async def async_initialize(self) -> None:
        """Load forecast data from storage.

        Loads previously saved forecast data and next update time from Home Assistant's
        storage. Converts stored hour keys to integers for internal use.
        """
        stored_data = await self._store.async_load()
        # return
        if stored_data is not None:
            temp = stored_data.get("forecast", {})
            # Convert keys from str to int for each day's forecast data
            self._forecast = {
                date: {int(hour): value for hour, value in day_data.items()}
                for date, day_data in temp.items()
            }
            next_update_str = stored_data.get("next_update")
            if next_update_str:
                dt = datetime.fromisoformat(next_update_str)
                self._next_update = dt_util.as_local(dt)
            else:
                self._next_update = dt_util.now() + timedelta(minutes=-1)
            if self._next_update < dt_util.now():
                await self.update_data()
            forecast_dates = list(self._forecast.keys())
            logger.debug("Loaded forecast data from storage: %s", forecast_dates)
        else:
            logger.debug("No forecast data found in storage, starting fresh")
        self._status = Status.NORMAL

    async def update_data(self) -> None:
        """Fetch and process data from Home Assistant sensors and Forecast.Solar API.

        If the next update time has passed, fetches new forecast data for all configured
        panels, aggregates the results, and saves them to storage. Removes outdated
        forecasts and updates the integration status.
        """
        if self._next_update < dt_util.now():
            await self._get_new_data_from_forecasts_solar_api()

        if self._status == Status.NOT_CONFIGURED:
            return

        self._remove_old_forecasts()

        for date, day_data in self._forecast.items():
            logger.debug(
                "\n%s: %s",
                date,
                ", ".join(
                    f"{hour}:{value}" for hour, value in day_data.items() if value > 0
                ),
            )
        # Save updated forecast data to storage
        if self._forecast and self._next_update:
            self._store.async_delay_save(
                lambda: {
                    "forecast": self._forecast,
                    "next_update": self._next_update.isoformat(),
                }
            )
        self._status = Status.NORMAL
        logger.info(
            "\n%sRetrieved Forecast.Solar forecast data for %d days%s",
            PURPLE,
            len(self._forecast),
            RESET,
        )


    async def _get_new_data_from_forecasts_solar_api(self) -> None:
        """Fetch and sum forecasts for all panels by hour.

        Retrieves the current list of active solar panels, fetches forecast data for each,
        and aggregates the hourly results into the internal forecast dictionary.
        Handles API rate limiting and uses mock data if enabled.
        """
        # First, get the current list of active solar panels
        self._panel_configurations = await self._fetch_active_panel_data()
        if not self._panel_configurations:
            logger.warning("No active panel configurations found for %s", self.name)
            self._status = Status.NOT_CONFIGURED
            return
        logger.debug("We found %s panels: %s", len(self._panel_configurations), self._panel_configurations)

        # Then sum the results from each hour for every panel
        found_data = False
        for panel in self._panel_configurations:
            data = await self._call_api_for_one_panel(panel)
            if not data:
                logger.warning("No data returned for panel %s", panel)
                continue
            result_data = data.get("result", {})
            watt_hours_period = result_data.get("watt_hours_period", {})
            watt_hours_day = result_data.get("watt_hours_day", {})
            day_data: dict[int, int] = dict.fromkeys(range(HRS_PER_DAY), 0)
            forecast_date_str = (
                next(iter(watt_hours_day)).split(" ")[0] if watt_hours_period else None
            )
            if forecast_date_str is None:
                logger.warning("No forecast data found in data for panel %s", panel)
                continue
            found_data = True
            # Run through the watt_hours_day data to get the data for each hour of each day
            for dt_str, value in watt_hours_period.items():
                if not dt_str.startswith(forecast_date_str):
                    self._forecast[forecast_date_str] = day_data
                    day_data = dict.fromkeys(range(HRS_PER_DAY), 0)
                    forecast_date_str = dt_str.split(" ")[0]

                # Parse the dt_str and extract the hour
                hour = int(
                    dt_str[11:13]
                )  # Extract the hour part from the datetime string
                day_data[hour] = int(value)
            # Record the last day's data
            self._forecast[forecast_date_str] = day_data
            logger.debug("Storing forecast data for %s", forecast_date_str)
        if found_data is False:
            self._status = Status.NOT_CONFIGURED
        logger.debug("We found %s forecast data points", len(self._forecast))
        logger.debug("We found forecast info: (T/F) %s", found_data)
        self._next_update = dt_util.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    async def _call_api_for_one_panel(self, panel: dict) -> dict:
        """Fetch forecast data for a single panel from the Forecast.Solar API.

        Args:
            panel: Dictionary containing panel configuration (lat, lon, dec, az, kwp).

        Returns:
            The parsed API response as a dictionary, or mock data if enabled or on error.

        """
        if self.status == Status.RATE_LIMITED:
            # If we are currently rate limited, skip the API call
            logger.warning("Currently rate limited, skipping API call for panel %s", panel)
            return {}

        url = (
            f"{FORECAST_SOLAR_API_URL}{panel['lat']}/{panel['lon']}/"
            f"{panel['dec']}/{panel['az']}/{panel['kwp']}"
        )
        if USE_MOCK_DATA:
            mock_data = await self._generate_mock_data()
            self._next_update = dt_util.now() + timedelta(minutes=1)
            return mock_data

        async with aiohttp.ClientSession() as session, session.get(url) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result.get("result", {})
            if resp.status == 429:
                # If we hit the rate limit, set the next update time to 60 minutes from now
                self._next_update = dt_util.now() + timedelta(minutes=60)
                logger.warning(
                    "\nRate limit hit, setting next update to %s", self._next_update
                )
                self._status = Status.RATE_LIMITED
                # return await self._generate_mock_data()

            return {}

    async def _fetch_active_panel_data(self) -> list:
        """Fetch and return active solar panel configuration data from Home Assistant storage.

        Reads Home Assistant's config and energy storage files to determine which
        forecast_solar panels are active and their configuration.

        Returns:
            Dictionary mapping entry_id to panel configuration.

        """
        # Get all config entries to look for energy sources
        all_entries: list[ConfigEntry] = self.hass.config_entries.async_entries()
        # Look for forecast_solar config entries with state LOADED
        config_entries = [entry.as_dict() for entry in all_entries if entry.domain == "forecast_solar" and entry.state == ConfigEntryState.LOADED]
        if not config_entries:
            logger.warning("No forecast_solar config entries found. Please set up your forecast_solar integration.")
            return []

        # Create and return a list of the required data for the api calls
        return [
            {
                "entry_id": entry["entry_id"],
                "kwp": (entry["options"].get("modules_power") or 0) / 1000.0,
                "lat": entry["data"].get("latitude", 0.0),
                "lon": entry["data"].get("longitude", 0.0),
                "dec": entry["options"].get("declination"),
                "az": entry["options"].get("azimuth"),
            }
            for entry in config_entries
        ]

    async def _generate_mock_data(self) -> dict:
        """Generate mock Forecast.Solar API data for development and testing.

        Uses astral to calculate sunrise and sunset times and generates plausible
        hourly PV data for yesterday, today, and tomorrow.

        Returns:
            Dictionary in the same format as the Forecast.Solar API response.

        """
        # Inform the user that mock data is being used
        logger.warning("\nUsing mock data for Forecast.Solar API.")

        # Get latitude and longitude from zone.home attributes
        state = self.hass.states.get("zone.home")
        if state is None:
            raise ValueError("zone.home entity not found")
        latitude = state.attributes.get("latitude", 0.0)
        longitude = state.attributes.get("longitude", 0.0)

        location = LocationInfo(
            latitude=latitude, longitude=longitude, timezone=self.timezone
        )
        today = dt_util.now().date()
        tomorrow = today + timedelta(days=1)
        yesterday = today - timedelta(days=1)
        # Calculate sunrise and sunset times for today and tomorrow
        sun_today = sun(location.observer, date=today)
        sun_tomorrow = sun(location.observer, date=tomorrow)
        sun_yesterday = sun(location.observer, date=yesterday)

        sunrise = sun_today["sunrise"].astimezone(ZoneInfo(self.timezone))
        sunset = sun_today["sunset"].astimezone(ZoneInfo(self.timezone))
        sunrise_tomorrow = sun_tomorrow["sunrise"].astimezone(ZoneInfo(self.timezone))
        sunset_tomorrow = sun_tomorrow["sunset"].astimezone(ZoneInfo(self.timezone))
        sunrise_yesterday = sun_yesterday["sunrise"].astimezone(ZoneInfo(self.timezone))
        sunset_yesterday = sun_yesterday["sunset"].astimezone(ZoneInfo(self.timezone))

        watt_hours_period = {
            **generate_day_data(sunrise_yesterday, sunset_yesterday),
            **generate_day_data(sunrise, sunset),
            **generate_day_data(sunrise_tomorrow, sunset_tomorrow),
        }

        watt_hours_day = {
            yesterday.strftime(DATE_FORMAT): sum(
                value
                for time, value in watt_hours_period.items()
                if time.startswith(yesterday.strftime(DATE_FORMAT))
            ),
            today.strftime(DATE_FORMAT): sum(
                value
                for time, value in watt_hours_period.items()
                if time.startswith(today.strftime(DATE_FORMAT))
            ),
            tomorrow.strftime(DATE_FORMAT): sum(
                value
                for time, value in watt_hours_period.items()
                if time.startswith(tomorrow.strftime(DATE_FORMAT))
            ),
        }

        return {
            "result": {
                "watt_hours_period": watt_hours_period,
                "watt_hours_day": watt_hours_day,
            },
            "message": {
                "code": 0,
                "type": "success",
                "text": "",
                "info": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "distance": 0,
                    "place": "Mock Location",
                    "timezone": self.timezone,
                    "time": dt_util.now().isoformat(),
                    "time_utc": dt_util.now(ZoneInfo("UTC")).isoformat(),
                },
                "ratelimit": {
                    "period": 3600,
                    "limit": 12,
                    "remaining": 10,
                },
            },
        }

    def _remove_old_forecasts(self) -> None:
        """Remove old forecast data from the forecast history.

        Keeps only forecasts within the configured retention period (DEFAULT_PV_MAX_DAYS).
        """
        cutoff = dt_util.now().date() + timedelta(days=-DEFAULT_PV_MAX_DAYS)
        self._forecast = {
            date: data
            for date, data in self._forecast.items()
            if (parsed_date := dt_util.parse_date(date)) is not None
            and parsed_date >= cutoff
        }

    async def async_unload_entry(self) -> None:
        """Clean up resources and listeners for ForecastSolar."""
        if self._unsub_update:
            self._unsub_update()
            self._unsub_update = None
        logger.debug("Unloaded Forecast_Solar")

    def forecast_for_date(self, date: str) -> dict[int, int]:
        """Return the forecast for a specific date.

        Args:
            date: Date string in YYYY-MM-DD format.

        Returns:
            Dictionary mapping hour to forecasted PV for the given date.

        """
        return self._forecast.get(date, {})

    @property
    def forecast(self) -> dict[str, dict[int, int]]:
        """Return PV forecasts for today and future dates only."""
        cutoff = dt_util.now().date()
        return {
            date: data
            for date, data in self._forecast.items()
            if (parsed_date := dt_util.parse_date(date)) is not None
            and parsed_date >= cutoff
        }

    @property
    def all_forecasts(self) -> dict[str, dict[int, int]]:
        """Return all PV forecasts, including past dates."""
        return self._forecast

    @property
    def next_update(self) -> datetime | None:
        """Return the next scheduled update time."""
        return self._next_update

    @property
    def status(self) -> Status:
        """Return the current status of the ForecastSolar integration."""
        return self._status

    @property
    def name(self) -> str:
        """Return the name of the ForecastSolar integration."""
        return self._name


def generate_day_data(sunrise, sunset) -> dict:
    """Generate mock hourly PV data for a given day.

    Simulates PV generation for each hour between sunrise and sunset, with a
    bell-shaped curve peaking at midday. Used for mock data and testing.

    Args:
        sunrise: Sunrise datetime for the day.
        sunset: Sunset datetime for the day.

    Returns:
        Dictionary mapping datetime strings to simulated watt-hour values.

    """
    MOCK_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    data: dict[str, int] = {}
    pre_sunrise = sunrise - timedelta(minutes=1)
    current_time = sunrise
    # Add the pre-sunrise data
    data[pre_sunrise.strftime(MOCK_DATE_FORMAT)] = 0
    # Add the first hour partial data
    next_hour = current_time.replace(minute=0, second=0, microsecond=0) + timedelta(
        minutes=60
    )
    minutes = ((next_hour - sunrise).seconds) // 60
    middle_hour: int = (sunset.hour - sunrise.hour - 2) / 2
    start_hour = sunrise.hour + 1
    watt_hours: int = int(750 * minutes / 60)
    data[current_time.strftime(MOCK_DATE_FORMAT)] = watt_hours
    current_time = current_time.replace(
        hour=start_hour, minute=0, second=0, microsecond=0
    )
    while current_time + timedelta(minutes=60) <= sunset:
        watt_hours: int = int(
            (middle_hour + 1) * 750
            - abs((current_time.hour - start_hour) - middle_hour) * 750
        )
        data[current_time.strftime(MOCK_DATE_FORMAT)] = watt_hours
        current_time += timedelta(minutes=60)  # Increment time in 30-minute intervals
    # Add the last value at sunset
    minutes = (sunset - current_time).seconds // 60
    watt_hours: int = int(750 * minutes / 60)
    data[sunset.strftime(MOCK_DATE_FORMAT)] = watt_hours
    return data
