"""Solcast integration for GRIST Scheduler.

Provides the Solcast class for interfacing with the Solcast HACS integration to supply
hourly photovoltaic (PV) forecast data to the GRIST Scheduler. This module loads,
parses, and maintains forecast data from Home Assistant sensors, supporting both
storage and live updates. It also exposes the integration status and next update time.

Key Features:
- Loads and stores hourly PV forecast data for multiple days from Home Assistant sensors.
- Parses detailed hourly forecast data from Solcast sensor attributes, supporting percentile selection.
- Removes outdated forecast data based on a configurable retention period.
- Exposes forecast data for specific dates and all available data.
- Tracks integration status and next scheduled update time.
- Designed for async operation and compatibility with Home Assistant's async patterns.

Classes:
    Solcast: Manages Solcast PV forecast data, storage, and access for GRIST Scheduler.

Functions:
    forecast_for_date: Returns the forecast for a specific date.
    async_initialize: Loads forecast data from storage.
    update_data: Updates forecast data from Home Assistant sensors.
    async_unload_entry: Cleans up resources and listeners.
    status: Returns the current status of the Solcast integration.

Usage:
    Instantiate Solcast with a Home Assistant instance and call async_initialize()
    to load stored data. Use update_data() to refresh forecasts from sensors.
    Access forecasts via the forecast or all_forecasts properties.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ..const import (  # noqa: TID252
    DEBUGGING,
    DEFAULT_PV_MAX_DAYS,
    DEFAULT_SOLCAST_PERCENTILE,
    FORECAST_KEY,
    PURPLE,
    RESET,
    SENSOR_FORECAST_SOLAR_TODAY,
    SENSOR_FORECAST_SOLAR_TOMORROW,
    STORAGE_VERSION,
    Status,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUGGING else logging.INFO)


@dataclass
class HourlyForecast:
    """Dataclass to represent hourly forecast data.

    Attributes:
        hour: The hour of the day (0-23).
        pv_estimate: The main PV estimate for this hour.
        pv_estimate10: The 10th percentile PV estimate for this hour.
        pv_estimate90: The 90th percentile PV estimate for this hour.

    """

    hour: int
    pv_estimate: int
    pv_estimate10: int
    pv_estimate90: int


class Solcast:
    """Interface between the GRIST Scheduler and the Solcast integration.

    Handles loading, updating, and parsing of hourly PV forecast data from Solcast sensors.
    Maintains forecast data for multiple days and exposes integration status and next update time.

    Args:
        hass: The Home Assistant instance.
        percentile: The desired percentile for the forecast (default is 20).

    """

    def __init__(
        self, hass: HomeAssistant, percentile: int = DEFAULT_SOLCAST_PERCENTILE
    ) -> None:
        """Initialize key variables and storage."""
        self.hass = hass
        self._status = Status.NOT_CONFIGURED
        self._percentile = percentile
        self._next_update = dt_util.now() + timedelta(minutes=-1)
        self._forecast: dict[str, dict[int, int]] = {}
        self._unsub_update = None
        self._store = Store(hass, STORAGE_VERSION, FORECAST_KEY)
        self._name = "Solcast Solar Forecast"

    async def async_initialize(self) -> None:
        """Load forecast data from storage.

        Loads previously saved forecast data and next update time from Home Assistant's
        storage. Converts stored hour keys to integers for internal use. If no data is
        found, starts with an empty forecast.
        """
        stored_data = await self._store.async_load()
        if stored_data is not None:
            temp = stored_data.get("forecast", {})
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
            logger.debug(
                "The data for today is: %s",
                self._forecast.get(dt_util.now().date().strftime("%Y-%m-%d"), {}),
            )
        else:
            logger.debug("No forecast data found in storage, starting fresh")
        self._status = Status.NORMAL

    async def update_data(self) -> None:
        """Fetch and process data from Home Assistant sensors.

        Finds all Solcast forecast sensors, processes each one concurrently to extract
        hourly forecast data, and updates the internal forecast dictionary. Removes
        outdated forecasts and updates the integration status. Saves updated data to storage.
        """

        entities = []
        sensor_list = [
            SENSOR_FORECAST_SOLAR_TODAY,
            SENSOR_FORECAST_SOLAR_TOMORROW,
        ]
        all_entities = self.hass.states.async_all("sensor")
        for prefix in sensor_list:
            entities.extend(
                state.entity_id
                for state in all_entities
                if state.entity_id.startswith(prefix)
            )
        if not entities:
            logger.warning("No entities found with prefix %s", sensor_list)

        if not entities:
            logger.error("No Solcast forecast found")
            self._status = Status.FAULT
            return

        results = await asyncio.gather(
            *(self._process_forecast_day(day) for day in entities),
            return_exceptions=True,
        )
        if not all(results):
            logger.error("Failed to process one or more forecast days")
            self._status = Status.FAULT
            return

        self._remove_old_forecasts()

        logger.info(
            "\n%sUpdated Solcast forecast data for %d days%s",
            PURPLE,
            len(self._forecast),
            RESET,
        )
        if self._forecast:
            self._store.async_delay_save(
                lambda: {
                    "forecast": self._forecast,
                    "next_update": self._next_update.isoformat(),
                }
            )

        self._status = Status.NORMAL

    async def _process_forecast_day(self, entity_id: str) -> bool:
        """Process a single forecast day sensor.

        Args:
            entity_id: The entity ID of the Solcast forecast sensor.

        Returns:
            True if processing was successful, False otherwise.

        """
        result = self.hass.states.get(entity_id)
        if not result:
            logger.error("No Solcast forecast data found for %s", entity_id)
            return False

        attributes = result.attributes
        if not attributes:
            logger.error("No forecast attributes found for %s", entity_id)
            return False

        detailed_hourly = attributes.get("detailedHourly")
        if not detailed_hourly:
            logger.error("No detailed forecast data found for %s", entity_id)
            return False

        next_day_date, hourly_forecast = await self._parse_detailed_hourly(
            detailed_hourly
        )
        if not next_day_date:
            logger.error("No date found for forecast data in %s", entity_id)
            return False

        self._forecast[next_day_date] = hourly_forecast
        return True

    async def _parse_detailed_hourly(
        self, detailed_hourly: list[dict]
    ) -> tuple[str | None, dict[int, int]]:
        """Parse detailed hourly forecast data from Solcast sensor attributes.

        Args:
            detailed_hourly: List of dicts, each representing an hour's forecast.

        Returns:
            Tuple of (date as 'YYYY-MM-DD', {hour: value}) or (None, {}) if input is empty.
        """
        hourly_forecast = {}
        next_day_date = None

        for idx, next_data in enumerate(detailed_hourly):
            if not next_data:
                continue

            period_start_date = next_data.get("period_start")
            if idx == 0 and period_start_date:
                next_day_date = period_start_date.strftime("%Y-%m-%d")

            hour = period_start_date.hour if period_start_date else 0
            pv_est10 = next_data.get("pv_estimate10", 0)
            pv_est = next_data.get("pv_estimate", 0)
            pv_est90 = next_data.get("pv_estimate90", 0)

            # Interpolate between percentiles based on self._percentile
            target_pv = (
                (pv_est10 + (self._percentile - 10) / 40 * (pv_est - pv_est10))
                if self._percentile <= 50
                else (pv_est + (self._percentile - 50) / 40 * (pv_est90 - pv_est))
            ) * 1000

            hourly_forecast[hour] = int(target_pv)

        return next_day_date, hourly_forecast

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
        """Clean up resources and listeners for the Solcast integration."""
        if self._unsub_update:
            self._unsub_update()
            self._unsub_update = None
        logger.debug("Unloaded Solcast")

    def forecast_for_date(self, date: str) -> dict[int, int]:
        """Return the forecast for a specific date.

        Args:
            date: Date string in 'YYYY-MM-DD' format.

        Returns:
            Dictionary mapping hour to forecasted PV for the given date.

        """
        return self._forecast.get(date, {})

    @property
    def forecast(self) -> dict[str, dict[int, int]]:
        """Return PV forecasts for future dates only."""
        cutoff = dt_util.now().date()
        return {
            date: data
            for date, data in self._forecast.items()
            if (parsed_date := dt_util.parse_date(date)) is not None
            and parsed_date > cutoff
        }

    @property
    def all_forecasts(self) -> dict[str, dict[int, int]]:
        """Return all PV forecasts, including past dates."""
        return self._forecast

    @property
    def next_update(self) -> datetime:
        """Return the next scheduled update time."""
        return self._next_update

    @property
    def status(self) -> Status:
        """Return the current status of the Solcast integration."""
        return self._status

    @property
    def name(self) -> str:
        """Return the name of the integration."""
        return self._name
