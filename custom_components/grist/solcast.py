"""Classes for integration with Solcast HACS to supply forecast info to Grid Boost Schedule.

This module contains three public properties:
    1) forecast: Returns a dictionary with the PV forecast as dict[str, dict[int, int]]. Times are local
    2) next_update: Returns the next time the Solcast API will be polled for updates.
    3) status: Returns the current status of the Solcast integration.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
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
from .hass_utilities import find_entities_by_prefixes, get_entity

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUGGING else logging.INFO)


@dataclass
class HourlyForecast:
    """Dataclass to represent hourly forecast data."""

    hour: int
    pv_estimate: int
    pv_estimate10: int
    pv_estimate90: int


class Solcast:
    """Class to interface between the Grid Boost Scheduler and the Solcast integration."""

    def __init__(
        self, hass: HomeAssistant, percentile: int = DEFAULT_SOLCAST_PERCENTILE
    ) -> None:
        """Initialize key variables.

        Args:
            hass: The Home Assistant instance.
            percentile: The desired percentile for the forecast (default is 20).

        """
        self.hass = hass
        self._status = Status.NOT_CONFIGURED
        self._percentile = percentile
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
                self._next_update = dt_util.now() + timedelta(
                    minutes=-1
                )
            forecast_dates = list(self._forecast.keys())
            logger.debug("Loaded forecast data from storage: %s", forecast_dates)
            logger.debug("The data for today is: %s", self._forecast.get(dt_util.now().date().strftime("%Y-%m-%d"), {}))
        else:
            logger.debug("No forecast data found in storage, starting fresh")

    async def update_data(self) -> None:
        """Fetch and process data from Home Assistant sensors."""
        forecast_prefixes = [SENSOR_FORECAST_SOLAR_TODAY, SENSOR_FORECAST_SOLAR_TOMORROW]

        forecast_days_ids = await find_entities_by_prefixes(
            self.hass, forecast_prefixes
        )
        if not forecast_days_ids:
            logger.error("No Solcast forecast found")
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
            "\n%sUpdated Solcast forecast data for %d days%s",
            PURPLE,
            len(self._forecast),
            RESET
        )
        # Save updated forecast data to storage
        if self._forecast:
            self._store.async_delay_save(
                lambda: {
                    "forecast": self._forecast,
                    "next_update": self._next_update.isoformat(),
                }
            )

        self._status = Status.NORMAL

    async def _process_forecast_day(self, entity_id: str) -> bool:
        """Process a single forecast day."""
        result = await get_entity(hass=self.hass, entity_id=entity_id)
        if not result:
            logger.error("No Solcast forecast data found for %s", entity_id)
            return False

        attributes = result.get("attributes")
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
        """Parse detailed hourly forecast data."""
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

            target_pv = (
                (pv_est10 + (self._percentile - 10) / 40 * (pv_est - pv_est10))
                if self._percentile <= 50
                else (pv_est + (self._percentile - 50) / 40 * (pv_est90 - pv_est))
            ) * 1000

            hourly_forecast[hour] = int(target_pv)

        return next_day_date, hourly_forecast

    def _remove_old_forecasts(self) -> None:
        """Remove old forecast data from the forecast history."""
        cutoff = dt_util.now().date() + timedelta(days=-DEFAULT_PV_MAX_DAYS)
        self._forecast = {
            date: data
            for date, data in self._forecast.items()
            if (parsed_date := dt_util.parse_date(date)) is not None and parsed_date >= cutoff
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
            if (parsed_date := dt_util.parse_date(date)) is not None and parsed_date > cutoff
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
