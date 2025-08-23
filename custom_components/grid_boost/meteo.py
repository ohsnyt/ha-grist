"""Classes for integration with Meteo HACS to supply forecast info to Grid Boost Scheduler.

Placeholder - to be developed.


This module contains two public properties:
    1) forecast: This will return a dictionary with the PV forecast as dict[str, dict[int, int]] where the key is the time in the form of YYYY-MM-DD, the forecast data is a dict of hour, value containing the predicted energy in watt-hours for each hour of the day.
    3) status: This will return the current status of the Meteo integration, which can be one of the following:
        - Status.NOT_CONFIGURED: The integration is not configured.
        - Status.FAULT: There was an error retrieving the forecast data.
        - Status.NORMAL: The integration is configured and working correctly.

To call the module, you need to create an instance of the Meteo class with the Home Assistant object as the argument. For example:
    forecaster = Meteo(hass)

NOTE: Key sensors with Meteo integration:
    sensor.meteo_pv_forecast_forecast_tomorrow: This sensor provides the forecast for tomorrow in kWh.
    sensor.meteo_pv_forecast_api_last_polled.next_auto_update: This sensor provides
        the next time the Meteo API will be polled for updates.

"""

import asyncio
from datetime import datetime, timedelta
import logging
from re import S
from typing import Never

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEBUGGING,
    DEFAULT_PV_MAX_DAYS,
    FORECAST_KEY,
    PURPLE,
    RESET,
    SENSOR_METEO_BASE,
    STORAGE_VERSION,
    Status,
)
from .hass_utilities import find_entities_by_prefixes, get_entity

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUGGING else logging.INFO)


class Meteo:
    """Class to interface between the Grid Boost Scheduler and the Meteo integration."""

    # Constructor
    def __init__(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Initialize key variables."""

        # General info
        self.hass = hass
        self._status = Status.NOT_CONFIGURED
        self._next_update = dt_util.now() + timedelta(minutes=-1)
        self._forecast: dict[str, dict[int, int]] = {}
        self._unsub_update = None
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
        """Update the Meteo data."""
        forecast_prefixes = [SENSOR_METEO_BASE]

        forecast_days_ids = await find_entities_by_prefixes(
            self.hass, forecast_prefixes
        )
        if not forecast_days_ids:
            logger.error("No Meteo forecast found")
            self._status = Status.FAULT
            return

        # Process each forecast day concurrently
        results = await asyncio.gather(
            *(self._process_forecast_day(day) for day in forecast_days_ids),
            return_exceptions=True,
        )
        if not all(results):
            logger.error("Failed to process one or more forecast days")
            self._status = Status.FAULT
            return

        self._remove_old_forecasts()

        logger.info(
            "\n%sUpdated Meteo forecast data for %d days%s",
            PURPLE,
            len(self._forecast),
            RESET,
        )

    async def _process_forecast_day(self, entity_id: str) -> bool:
        """Process a single forecast day."""
        result = await get_entity(hass=self.hass, entity_id=entity_id)
        if not result:
            logger.error("No Meteo forecast data found for %s", entity_id)
            return False

        attributes = result.get("attributes")
        if not attributes:
            logger.warning("No attributes found for %s. Probably a daily total.", entity_id)
            return True

        detailed_hourly = attributes.get("wh_period")
        if not detailed_hourly:
            logger.warning("No forecast wh_period attribute found for %s. Probably a daily total.", entity_id)
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
        """Parse detailed hourly forecast data.

        Args:
            detailed_hourly: A dict with ISO datetime strings as keys and float values for each hour.

        Returns:
            A tuple of (date as 'YYYY-MM-DD', {hour: value}) or (None, {}) if input is empty.

        """
        if not detailed_hourly:
            return None, {}

        # Get the date string from the first key
        first_key = next(iter(detailed_hourly))
        date_str = first_key[:10]

        # Build the hourly forecast dict
        hourly_forecast = {
            int(key[11:13]): int(value) for key, value in detailed_hourly.items()
        }

        return date_str, hourly_forecast

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
            and parsed_date > cutoff
        }

    @property
    def all_forecasts(self) -> dict[str, dict[int, int]]:
        """Return all PV forecasts."""
        return self._forecast

    @property
    def next_update(self) -> datetime:
        """Return the next update time."""
        return self._next_update

    @property
    def status(self) -> Status:
        """Return the current status of the Solcast integration."""
        return self._status
