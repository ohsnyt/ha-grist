"""Meteo integration for GRIST Scheduler.

Provides the Meteo class for interfacing with the Meteo HACS integration to supply
hourly photovoltaic (PV) forecast data to the GRIST Scheduler. This module loads,
parses, and maintains forecast data from Home Assistant sensors, supporting both
storage and live updates. It also exposes the integration status and next update time.

Key Features:
- Loads and stores hourly PV forecast data for multiple days from Home Assistant sensors.
- Parses detailed hourly forecast data from Meteo sensor attributes.
- Removes outdated forecast data based on a configurable retention period.
- Exposes forecast data for specific dates and all available data.
- Tracks integration status and next scheduled update time.
- Designed for async operation and compatibility with Home Assistant's async patterns.

Classes:
    Meteo: Manages Meteo PV forecast data, storage, and access for GRIST Scheduler.

Functions:
    forecast_for_date: Returns the forecast for a specific date.
    async_initialize: Loads forecast data from storage.
    update_data: Updates forecast data from Home Assistant sensors.
    async_unload_entry: Cleans up resources and listeners.
    status: Returns the current status of the Meteo integration.

Usage:
    Instantiate Meteo with a Home Assistant instance and call async_initialize()
    to load stored data. Use update_data() to refresh forecasts from sensors.
    Access forecasts via the forecast or all_forecasts properties.
"""

import asyncio
from datetime import datetime, timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ..const import (  # noqa: TID252
    DEBUGGING,
    DEFAULT_PV_MAX_DAYS,
    FORECAST_KEY,
    PURPLE,
    RESET,
    SENSOR_METEO_BASE,
    STORAGE_VERSION,
    Status,
)
from ..hass_utilities import find_entities_by_prefixes, get_entity  # noqa: TID252

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUGGING else logging.INFO)


class Meteo:
    """Interface between the GRIST Scheduler and the Meteo HACS integration.

    Handles loading, updating, and parsing of hourly PV forecast data from Meteo sensors.
    Maintains forecast data for multiple days and exposes integration status and next update time.
    """

    def __init__(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Initialize Meteo integration variables and storage.

        Args:
            hass: The Home Assistant instance.

        """
        self.hass = hass
        self._status = Status.NOT_CONFIGURED
        self._next_update = dt_util.now() + timedelta(minutes=-1)
        self._forecast: dict[str, dict[int, int]] = {}
        self._unsub_update = None
        self._store = Store(hass, STORAGE_VERSION, FORECAST_KEY)

    async def async_initialize(self) -> None:
        """Load forecast data from storage.

        Loads previously saved forecast data and next update time from Home Assistant's
        storage. Converts stored hour keys to integers for internal use. If no data is
        found, triggers an initial update from sensors.
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
        else:
            logger.debug("No forecast data found in storage, starting fresh")
            await self.update_data()

    async def async_unload_entry(self) -> None:
        """Clean up resources and listeners for the Meteo integration."""
        if self._unsub_update:
            self._unsub_update()
            self._unsub_update = None
        logger.debug("Unloaded Meteo")

    async def update_data(self) -> None:
        """Update the Meteo forecast data from Home Assistant sensors.

        Finds all Meteo forecast sensors, processes each one concurrently to extract
        hourly forecast data, and updates the internal forecast dictionary. Removes
        outdated forecasts and updates the integration status.
        """
        forecast_prefixes = [SENSOR_METEO_BASE]
        forecast_days_ids = await find_entities_by_prefixes(
            self.hass, forecast_prefixes
        )
        if not forecast_days_ids:
            logger.error("No Meteo forecast found")
            self._status = Status.FAULT
            return

        results = await asyncio.gather(
            *(self._process_forecast_day(day) for day in forecast_days_ids),
            return_exceptions=True,
        )
        if not all(results):
            logger.error("Failed to process one or more forecast days")
            self._status = Status.FAULT
            return

        self._remove_old_forecasts()

        self._status = Status.NORMAL

        logger.info(
            "\n%sUpdated Meteo forecast data for %d days%s",
            PURPLE,
            len(self._forecast),
            RESET,
        )

    async def _process_forecast_day(self, entity_id: str) -> bool:
        """Process a single Meteo forecast day sensor.

        Args:
            entity_id: The entity ID of the Meteo forecast sensor.

        Returns:
            True if processing was successful, False otherwise.

        """
        result = await get_entity(hass=self.hass, entity_id=entity_id)
        if not result:
            logger.error("No Meteo forecast data found for %s", entity_id)
            return False

        attributes = result.get("attributes")
        if not attributes:
            logger.warning(
                "No attributes found for %s. Probably a daily total.", entity_id
            )
            return True

        detailed_hourly = attributes.get("wh_period")
        if not detailed_hourly:
            logger.warning(
                "No forecast wh_period attribute found for %s. Probably a daily total.",
                entity_id,
            )
            return True

        next_day_date, hourly_forecast = await self._parse_detailed_hourly(
            detailed_hourly
        )
        if not next_day_date:
            logger.error("No date found for forecast data in %s", entity_id)
            return False

        self._forecast[next_day_date] = hourly_forecast
        return True

    async def _parse_detailed_hourly(
        self, detailed_hourly: dict[str, float]
    ) -> tuple[str | None, dict[int, int]]:
        """Parse detailed hourly forecast data from Meteo sensor attributes.

        Args:
            detailed_hourly: A dict with ISO datetime strings as keys and float values for each hour.

        Returns:
            A tuple of (date as 'YYYY-MM-DD', {hour: value}) or (None, {}) if input is empty.
        """
        if not detailed_hourly:
            return None, {}

        first_key = next(iter(detailed_hourly))
        date_str = first_key[:10]
        hourly_forecast = {
            int(key[11:13]): int(value) for key, value in detailed_hourly.items()
        }
        return date_str, hourly_forecast

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

    async def async_unload(self) -> None:
        """Clean up resources and unschedule periodic updates."""
        if self._unsub_update:
            self._unsub_update()
            self._unsub_update = None
        logger.debug("Unscheduled periodic updates")

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
        """Return the current status of the Meteo integration."""
        return self._status
