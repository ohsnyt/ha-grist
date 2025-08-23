"""Grid Boost integration for Home Assistant.

Handles Time-of-Use battery and grid boost management, including scheduling, storage, and forecast calculations.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.util import dt as dt_util

from .battery import Battery
from .boost_calc import calculate_required_boost
from .const import (
    DEBUGGING,
    DEFAULT_BATTERY_MIN_SOC,
    DEFAULT_GRID_BOOST_MODE,
    DEFAULT_GRID_BOOST_START,
    DEFAULT_GRID_BOOST_STARTING_SOC,
    DEFAULT_INVERTER_EFFICIENCY,
    DEFAULT_LOAD_AVERAGE_DAYS,
    DEFAULT_UPDATE_HOUR,
    NUMBER_CAPACITY_POINT_1,
    PURPLE,
    RESET,
    BoostMode,
    Status,
)
from .coordinator import GridBoostUpdateCoordinator
from .daily_calcs import DailyStats
from .forecast_solar import ForecastSolar
from .hass_utilities import get_state, set_number
from .meteo import Meteo
from .solcast import Solcast

logger: logging.Logger = logging.getLogger(__name__)
if DEBUGGING:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)


# Utility function to convert an integer to its ordinal representation, used for sensors
def ordinal(n: int) -> str:
    """Return the ordinal suffix for a given integer (1st, 2nd, 3rd, etc)."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    match n % 10:
        case 1:
            return f"{n}st"
        case 2:
            return f"{n}nd"
        case 3:
            return f"{n}rd"
        case _:
            return f"{n}th"


class GridBoostScheduler:
    """Scheduler for Grid Boost battery and grid boost management.

    Handles loading and saving of boost settings, calculation of required battery boost,
    and provides methods for updating and retrieving scheduling data.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        coordinator: GridBoostUpdateCoordinator | None,
        boost_mode: str = DEFAULT_GRID_BOOST_MODE,
        grid_boost_manual: int = DEFAULT_GRID_BOOST_STARTING_SOC,
        grid_boost_start: str = DEFAULT_GRID_BOOST_START,
        update_hour: int = DEFAULT_UPDATE_HOUR,
        minimum_soc: int = DEFAULT_BATTERY_MIN_SOC,
        history_days: int = DEFAULT_LOAD_AVERAGE_DAYS,
    ) -> None:
        """Initialize the GridBoostScheduler with Home Assistant context and configuration.

        Args:
            hass: The Home Assistant instance.
            config_entry: The configuration entry for this integration.
            coordinator: The update coordinator, if available.
            boost_mode: The current boost mode (e.g., auto, manual, off).
            grid_boost_manual: The manually set SOC for grid boost.
            grid_boost_start: The time to start grid boost (as a string, e.g., "00:30").
            update_hour: The hour of the day to perform updates.
            minimum_soc: The minimum allowed battery state of charge.
            history_days: The number of days to use for load average calculations.

        """
        self.hass = hass
        self.config_entry = config_entry
        self.coordinator = coordinator
        self.boost_mode = boost_mode
        self.grid_boost_manual = grid_boost_manual
        self.grid_boost_start = grid_boost_start
        self.update_hour = update_hour
        self.minimum_soc = minimum_soc
        self.days_of_load_history: int = history_days

        # Reserve space for the forecaster, battery and calculation objects
        self.forecaster = None
        self.battery = None
        self.daily = None

        self.status = Status.STARTING
        self._refresh_boost_next_start = dt_util.now()
        self._daily_task_next_start = dt_util.now()

        # Grid Boost settings
        self.grid_boost_actual: int = DEFAULT_GRID_BOOST_STARTING_SOC
        self.grid_boost_calculated: int = DEFAULT_GRID_BOOST_STARTING_SOC
        self.pv_adjusted_estimates_history: dict[str, dict[int, int]] = {}

    async def _select_forecaster(self) -> bool:
        """Select the forecaster based on which one is in NORMAL status."""
        logger.debug("Setting up Grid Boost")
        self.status = Status.NOT_CONFIGURED
        # Get all config entries for the Forecast.solar domain
        integration_list = ["solcast_solar", "forecast_solar", "open_meteo"]
        # Check if any entry is in the LOADED state
        integration = await self._is_integration_running(integration_list)
        if integration:
            logger.info("\n%sSelected forecaster: %s%s", PURPLE, integration, RESET)
            if integration == "solcast_solar":
                self.forecaster = Solcast(self.hass)
                logger.info("Solcast")
            elif integration == "forecast_solar":
                self.forecaster = ForecastSolar(self.hass)
                logger.info("Forecast Solar")
                # Could also add a percentile if needed
            elif integration == "open_meteo":
                self.forecaster = Meteo(self.hass)
                logger.info("Open Meteo Solar Forecast")
            if self.forecaster is not None:
                await self.forecaster.async_initialize()
            return True
        return False

    async def _is_integration_running(self, integration_list: list) -> str | None:
        """Check if any (forecaster) integration in the provided list is currently running (i.e., in the LOADED state).

        Args:
            integration_list (list): List of integration domain names to check.

        Returns:
            str | None: The domain name of the first integration found in the LOADED state, or None if none are loaded.

        """
        # Get all config entries for the integration domain
        all_entries: list[ConfigEntry[Any]] = self.hass.config_entries.async_entries()
        # Filter entries for the specific integration
        if not all_entries:
            logger.debug("No config entries found for %s", integration_list)
            return None

        for integration in integration_list:
            entries = [entry for entry in all_entries if entry.domain == integration]
            logger.debug("Entries for %s: %s", integration, entries)
            if any(entry.state == ConfigEntryState.LOADED for entry in entries):
                logger.debug("Integration %s is loaded", integration)
                return integration

        logger.debug("No running integration found in %s", integration_list)
        return None

    async def _daily_tasks(self) -> None:
        """Update forecaster, daily and battery data at the start of each day."""

        if self.forecaster and self.daily and self.battery:
            await self.forecaster.update_data()
            await self.daily.update_data()
            await self.battery.update_data()
            self.status = Status.NORMAL
        else:
            self.status = Status.NOT_CONFIGURED
            if not self.forecaster:
                logger.warning("Forecaster not configured")
            if not self.daily:
                logger.warning("DailyStats not configured")
            if not self.battery:
                logger.warning("Battery not configured")
            return

        # Reset daily task next start time. We will run twice a day, once just after midnight and once at 10 pm.
        if dt_util.now().hour < 22:
            self._daily_task_next_start = dt_util.now().replace(
                hour=22, minute=0, second=0, microsecond=0
            )
        else:
            self._daily_task_next_start = dt_util.now().replace(
                hour=0, minute=1, second=0, microsecond=0
            ) + timedelta(days=1)

    async def _refresh_boost(self) -> None:
        """Recalculate statistics once an hour."""

        if self._refresh_boost_next_start > dt_util.now():
            return

        if self.daily is None or self.battery is None:
            if self.daily is None:
                logger.warning("DailyStats not initialized, cannot refresh boost.")
            if self.battery is None:
                logger.warning("Battery not initialized, cannot refresh boost.")
            return

        boost = calculate_required_boost(
            battery_max_wh=self.battery.capacity_wh,
            efficiency=DEFAULT_INVERTER_EFFICIENCY,
            minimum_soc=self.minimum_soc,
            adjusted_pv=self.daily.forecast_tomorrow_adjusted,
            average_hourly_load=self.daily.average_hourly_load,
        )
        self.grid_boost_calculated = (
            int(boost) if boost else int(self.grid_boost_manual)
        )
        # Write the boost to the inverter if we are in automatic or manual mode
        if self.boost_mode == BoostMode.AUTOMATIC:
            await set_number(
                self.hass, NUMBER_CAPACITY_POINT_1, self.grid_boost_calculated
            )
        elif self.boost_mode == BoostMode.MANUAL:
            await set_number(self.hass, NUMBER_CAPACITY_POINT_1, self.grid_boost_manual)

        # Reset next start time to either the start of the next day or the desired refresh hour.
        if dt_util.now().hour < self.update_hour:
            self._refresh_boost_next_start = dt_util.now().replace(
                hour=self.update_hour, minute=0, second=0, microsecond=0
            )
        else:
            self._refresh_boost_next_start = dt_util.now().replace(
                hour=self.update_hour, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)

    async def _calculate_remaining_battery_time(self) -> int:
        """Calculate the remaining battery time based on the current state of charge and load.

        Assumes hourly granularity for load and PV data; if data is missing for any hour, the calculation may overestimate the remaining time.

        Returns:
            int: Remaining battery time in minutes.

        """
        if not self.battery:
            logger.warning(
                "Battery is not initialized, cannot calculate remaining time."
            )
            return 0

        if not self.daily:
            logger.warning(
                "Calculations not complete, cannot calculate remaining battery time."
            )
            return 0

        if not self.forecaster:
            logger.warning(
                "Forecaster is not initialized, cannot calculate remaining time."
            )
            return 0

        # Get the current state of charge (SOC) and calculate remaining watt-hours
        soc = self.battery.state_of_charge
        loads = self.daily.average_hourly_load if self.daily else {}
        remaining_wh = soc * self.battery.capacity_wh

        # Initialize remaining time
        remaining_time = 0

        # Get the current time and calculate the partial hour
        current_time = dt_util.now()
        next_hour = current_time.replace(minute=0, second=0, microsecond=0) + timedelta(
            hours=1
        )
        part_hour = (next_hour - current_time).seconds / 3600.0

        # Handle the current partial hour
        this_hour = current_time.hour
        this_day = current_time.date().strftime("%Y-%m-%d")
        pv = self.forecaster.forecast_for_date(this_day)
        adjusted_pv = {
            hour: pv.get(hour, 0) * self.daily.pv_performance_ratios.get(hour, 1.0)
            for hour in range(24)
        }
        net_change = adjusted_pv.get(this_hour, 0) - loads.get(this_hour, 1000)
        remaining_wh = min(
            remaining_wh + net_change * part_hour, self.battery.capacity_wh
        )
        remaining_time += int(part_hour * 60)

        # Iterate over future hours until the battery is depleted
        while remaining_wh > 0:
            # Move to the next hour
            this_hour = next_hour.hour
            if this_day != next_hour.date().strftime("%Y-%m-%d"):
                this_day = next_hour.date().strftime("%Y-%m-%d")
                pv = self.forecaster.forecast_for_date(this_day)
                adjusted_pv = {
                    hour: pv.get(hour, 0)
                    * self.daily.pv_performance_ratios.get(hour, 1.0)
                    for hour in range(24)
                }

            next_hour += timedelta(hours=1)

            # Get the net energy change for the hour
            net_change = adjusted_pv.get(this_hour, 0) - loads.get(this_hour, 0)

            # Update remaining watt-hours, allowing for increase if net charging (e.g., from PV) occurs.
            # This is intentional to account for periods when PV generation exceeds load.
            remaining_wh = min(remaining_wh + net_change, self.battery.capacity_wh)
            remaining_time += 60  # Add a full hour

            # If the battery is depleted, remove the excess time
            if remaining_wh <= 0:
                wh_partial = remaining_wh / net_change
                excess_time = int(round(60 * wh_partial))
                remaining_time -= excess_time
                break

        # logger.debug("Remaining battery time calculated: %d minutes", remaining_time)
        return remaining_time

    async def to_dict(
        self,
    ) -> dict[str, Any]:
        """Return calculated data as a dictionary."""

        # First, check if hass is running. If not, return starting status.
        if self.hass.is_running is False:
            logger.debug("Grid Boost is starting...")
            return {"status": Status.STARTING}

        # --- STARTUP ---
        # Once hass is running, initialize forecaster, battery, and calculations. This happens only once.
        if self.forecaster is None:
            if not await self._select_forecaster():
                logger.error("No forecaster available, cannot proceed with setup")
                raise ConfigEntryError("No forecaster available")
            if not self.battery:
                self.battery = Battery(self.hass)
                await self.battery.async_initialize()
            if not self.daily and self.forecaster is not None:
                self.daily = DailyStats(self.hass, self.forecaster)
                await self.daily.async_initialize()
                await self._refresh_boost()
            if self.status == Status.STARTING:
                # Set the status to NORMAL once everything is initialized
                self.status = Status.NORMAL
                logger.debug("Grid Boost initialized successfully")
        # --- END STARTUP ---

        # Check if the daily tasks need to be run.
        if self._daily_task_next_start <= dt_util.now():
            logger.debug("Running daily tasks.")
            await self._daily_tasks()

        # Check if the refresh boost task needs to be run.
        await self._refresh_boost()

        # Refresh battery statistics on every call so we can calculate remaining battery time.
        await self.battery.update_data() if self.battery else None

        # Initialize key data to send to sensors
        now = dt_util.now()
        # hour = now.hour
        boost_actual_state = await get_state(self.hass, NUMBER_CAPACITY_POINT_1)
        if boost_actual_state is not None:
            try:
                boost_actual = int(round(float(boost_actual_state), 0))
            except (ValueError, TypeError):
                logger.warning(
                    "Grid boost actual value is invalid, using default value."
                )
                boost_actual = DEFAULT_GRID_BOOST_STARTING_SOC
        else:
            logger.warning("Grid boost actual value is None, using default value.")
            boost_actual = DEFAULT_GRID_BOOST_STARTING_SOC

        remaining_battery_time: int = await self._calculate_remaining_battery_time()

        # Return the dictionary with all the calculated data
        return {
            "status": self.status,
            "battery_exhausted": (
                now + timedelta(minutes=remaining_battery_time)
            ).strftime("%a %-I:%M %p"),
            "battery_time_remaining": round(remaining_battery_time / 60, 1),
            "grid_boost_actual": boost_actual
            if boost_actual is not None
            else "Unknown",
            "grid_boost_manual": self.grid_boost_manual,
            "grid_boost_mode": self.boost_mode,
            "grid_boost_calculated": self.grid_boost_calculated,
            "grid_boost_day": f"{(now + timedelta(days=1)).strftime('%A')} the {ordinal((now + timedelta(days=1)).day)}",
            # "grid_boost_start": self.grid_boost_start,
            "load_days": self.days_of_load_history,
            # "update_hour": self.update_hour,
            "load_averages": self.daily.average_hourly_load if self.daily else {},
            "pv_ratios": self.daily.pv_performance_ratios if self.daily else {},
            "pv_calculated_today": self.daily.forecast_today_adjusted
            if self.daily
            else {},
            "pv_calculated_today_total": self.daily.forecast_today_adjusted_total
            if self.daily
            else 0,
            "pv_calculated_today_day": f"{now.strftime('%A')} the {ordinal(now.day)}",
            "pv_calculated_tomorrow": self.daily.forecast_tomorrow_adjusted
            if self.daily
            else {},
            "pv_calculated_tomorrow_total": self.daily.forecast_tomorrow_adjusted_total
            if self.daily
            else 0,
            "pv_calculated_tomorrow_day": f"{(now + timedelta(days=1)).strftime('%A')} the {ordinal((now + timedelta(days=1)).day)}",
        }
