"""Forecast Solar integration utilities for Home Assistant."""

from datetime import datetime, timedelta
import json
import logging
from zoneinfo import ZoneInfo

import aiohttp
import anyio
from astral import LocationInfo
from astral.sun import sun

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CORE_CONFIG_STORAGE,
    CORE_ENERGY_STORAGE,
    CORE_FORECAST_FILTER,
    DATE_FORMAT,
    DEBUGGING,
    DEFAULT_PV_MAX_DAYS,
    DEFAULT_UPDATE_HOUR,
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

    Forecast.solar allows for multiple solar panel configurations, each with its own latitude, longitude, declination, azimuth, and kilowatt peak (kwp) rating. We have to account for this as well as the user's location and the current weather conditions when generating forecasts.
    """

    # Constructor for ForecastSolar class.
    def __init__(
        self, hass: HomeAssistant, update_hour: int = DEFAULT_UPDATE_HOUR
    ) -> None:
        """Initialize ForecastSolar with Home Assistant instance and update hour."""
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
        self.update_hour = update_hour

        # Initialize storage
        self._store = Store(hass, STORAGE_VERSION, FORECAST_KEY)

    async def async_initialize(self) -> None:
        """Load forecast data from storage."""
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
            forecast_dates = list(self._forecast.keys())
            logger.debug("Loaded forecast data from storage: %s", forecast_dates)
        else:
            logger.debug("No forecast data found in storage, starting fresh")

    async def update_data(self) -> None:
        """Fetch and process data from Home Assistant sensors."""
        if self._next_update < dt_util.now():
            await self._get_new_data_from_forecasts_solar_api()

        self._remove_old_forecasts()

        logger.info(
            "\n{%s}Retrieved Forecast.Solar forecast data for %d days%s",
            PURPLE,
            len(self._forecast),RESET
        )
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

    async def _get_sum_sensors(self, sensor_prefix: str) -> float:
        """Sum and return sensor values."""
        # Sum the values from all sensors starting with sensor_prefix
        sensor_value = 0.0
        for state in self.hass.states.async_all("sensor"):
            match state:
                case _ if state.entity_id.startswith(sensor_prefix):
                    try:
                        sensor_value += (
                            float(state.state) if state.state is not None else 0.0
                        )
                    except (TypeError, ValueError):
                        logger.debug(
                            "Non-numeric state for %s: %s", state.entity_id, state.state
                        )
                        continue
        return sensor_value

    async def _get_new_data_from_forecasts_solar_api(self) -> None:
        """Fetch and sum forecasts for all panels by hour."""
        # First, get the current list of active solar panels
        self._panel_configurations = await self._fetch_active_panel_data()

        # Then sum the results from each hour for every panel
        for panel in self._panel_configurations.values():
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
                logger.warning("No forecast date found in data for panel %s", panel)
                continue
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
        self._next_update = dt_util.now() + timedelta(hours=1)

    async def _call_api_for_one_panel(self, panel: dict) -> dict:
        """Fetch forecast data for a single panel."""
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
                return await self._generate_mock_data()

            return {}

    async def _fetch_active_panel_data(self) -> dict:
        """Fetch and return active solar panel configuration data from Home Assistant storage."""
        # First, get the config entries for forecast_solar from the Home Assistant config_entries json file
        # (This defines the panel characteristics)
        async with await anyio.open_file(
            CORE_CONFIG_STORAGE,
            "r",
            encoding="utf-8",
        ) as f:
            config_data = json.loads(await f.read())
            config_entries = config_data["data"]["entries"]
        # Then, get the solar forecast config entries from the energy storage file
        # (This defines which panels are active)
        async with await anyio.open_file(
            CORE_ENERGY_STORAGE, "r", encoding="utf-8"
        ) as f:
            energy_data = json.loads(await f.read())
            energy_sources = energy_data["data"]["energy_sources"]
        # Filter the config entries to get only those that are solar forecast entries
        solar_forecast_id_lists = [
            source.get(CORE_FORECAST_FILTER, [])
            for source in energy_sources
            if source["type"] == "solar"
        ]
        if not solar_forecast_id_lists:
            logger.warning("No solar sources found in energy configuration.")
            return {}

        # Flatten the list of lists to a single list of solar forecast IDs
        solar_forecast_ids = solar_forecast_id_lists[0]
        # Get the lat and lon from the zone.home entity, since it is not available in the config entries
        lat = 0.0
        lon = 0.0
        state = self.hass.states.get("zone.home")
        if state is not None:
            lat = state.attributes.get("latitude", 0.0)
            lon = state.attributes.get("longitude", 0.0)

        # Create and return a list of the required data for the api calls
        forecast_solar_entries = [
            {
                "entry_id": entry["entry_id"],
                "kwp": (entry["options"].get("modules_power") or 0) / 1000.0,
                "lat": lat,
                "lon": lon,
                "dec": entry["options"].get("declination"),
                "az": entry["options"].get("azimuth"),
            }
            for entry in config_entries
            if entry["domain"] == "forecast_solar"
            and entry["entry_id"] in solar_forecast_ids
        ]
        return {entry["entry_id"]: entry for entry in forecast_solar_entries}

    async def _generate_mock_data(self) -> dict:
        """Generate mock forecast.solar API data."""
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
        """Remove old forecast data from the forecast history."""
        cutoff = dt_util.now().date() + timedelta(days=-DEFAULT_PV_MAX_DAYS)
        self._forecast = {
            date: data
            for date, data in self._forecast.items()
            if (parsed_date := dt_util.parse_date(date)) is not None
            and parsed_date >= cutoff
        }

    async def async_unload(self) -> None:
        """Clean up resources."""
        if self._unsub_update:
            self._unsub_update()
            self._unsub_update = None
        logger.debug("Unscheduled periodic updates")

    def forecast_for_date(self, date: str) -> dict[int, int]:
        """Return the forecast for a specific date."""
        return self._forecast.get(date, {})

    @property
    def forecast(self) -> dict[str, dict[int, int]]:
        """Return PV for the future."""
        cutoff = dt_util.now().date()
        return {
            date: data
            for date, data in self._forecast.items()
            if (parsed_date := dt_util.parse_date(date)) is not None
            and parsed_date >= cutoff
        }

    @property
    def all_forecasts(self) -> dict[str, dict[int, int]]:
        """Return all PV forecasts."""
        return self._forecast

    @property
    def next_update(self) -> datetime | None:
        """Return the next update time."""
        return self._next_update

    @property
    def status(self) -> Status:
        """Return the current status of the Solcast integration."""
        return self._status


def generate_day_data(sunrise, sunset) -> dict:
    """Generate mock data for a given day."""
    DATE_FORMAT_MOCK = "%Y-%m-%d %H:%M:%S"
    data: dict[str, int] = {}
    pre_sunrise = sunrise - timedelta(minutes=1)
    current_time = sunrise
    # Add the pre-sunrise data
    data[pre_sunrise.strftime(DATE_FORMAT_MOCK)] = 0
    # Add the first hour partial data
    next_hour = current_time.replace(minute=0, second=0, microsecond=0) + timedelta(
        minutes=60
    )
    minutes = ((next_hour - sunrise).seconds) // 60
    middle_hour: int = (sunset.hour - sunrise.hour - 2) / 2
    start_hour = sunrise.hour + 1
    watt_hours: int = int(750 * minutes / 60)
    data[current_time.strftime(DATE_FORMAT_MOCK)] = watt_hours
    current_time = current_time.replace(
        hour=start_hour, minute=0, second=0, microsecond=0
    )
    while current_time + timedelta(minutes=60) <= sunset:
        watt_hours: int = int(
            (middle_hour + 1) * 750
            - abs((current_time.hour - start_hour) - middle_hour) * 750
        )
        data[current_time.strftime(DATE_FORMAT_MOCK)] = watt_hours
        current_time += timedelta(minutes=60)  # Increment time in 30-minute intervals
    # Add the last value at sunset
    minutes = (sunset - current_time).seconds // 60
    watt_hours: int = int(750 * minutes / 60)
    data[sunset.strftime(DATE_FORMAT_MOCK)] = watt_hours
    return data
