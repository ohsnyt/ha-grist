"""Grid Boost integration for Home Assistant.

Handles Time-of-Use battery and grid boost management, including scheduling, storage, and forecast calculations.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import traceback
from typing import Any, Self

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.util import dt as dt_util

from .battery import Battery
from .boost_calc import calculate_required_boost
from .const import (
    DEBUGGING,
    DEFAULT_BATTERY_MIN_SOC,
    DEFAULT_GRIST_END,
    DEFAULT_GRIST_MODE,
    DEFAULT_GRIST_START,
    DEFAULT_GRIST_STARTING_SOC,
    DEFAULT_INVERTER_EFFICIENCY,
    DEFAULT_LOAD_AVERAGE_DAYS,
    DEFAULT_UPDATE_HOUR,
    NUMBER_CAPACITY_POINT_1,
    PURPLE,
    RESET,
    SWITCH_TOU_STATE,
    BoostMode,
    Status,
)
from .daily_calcs import DailyStats
from .forecast_solar import ForecastSolar
from .hass_utilities import get_state, get_switch, set_number, set_switch
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


def to_hour(hour: int) -> str:
    """Convert an integer hour (0-23) to a string representation."""
    if hour == 0:
        return "midnight"
    if 1 <= hour < 12:
        return f"{hour}am"
    if hour == 12:
        return "noon"
    if 13 <= hour < 24:
        return f"{hour - 12}pm"
    raise ValueError("Invalid hour")


class GristScheduler:
    """GRIST Scheduler for battery and grid boost management.

    Handles loading and saving of boost settings, calculation of required battery boost,
    and provides methods for updating and retrieving scheduling data.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        options: dict[str, Any],
    ) -> None:
        """Initialize the GristScheduler with Home Assistant context and configuration.

        Args:
            hass: The Home Assistant instance.
            options: The configuration options for this integration.
            coordinator: The update coordinator, if available.
            boost_mode: The current boost mode (e.g., auto, manual, off).
            grist_manual: The manually set SOC for grid boost.
            grist_start: The time to start grid boost (as a string, e.g., "00:00").
            grist_end: The time to end grid boost (as a string, e.g., "06:00").
            update_hour: The hour of the day to perform updates.
            minimum_soc: The minimum allowed battery state of charge.
            history_days: The number of days to use for load average calculations.

        """
        self.hass = hass
        self.boost_mode = options.get("boost_mode", DEFAULT_GRIST_MODE)
        self.grist_manual = options.get("grist_manual", DEFAULT_GRIST_STARTING_SOC)
        self.grist_start = options.get("grist_start", DEFAULT_GRIST_START)
        self.grist_end = options.get("grist_end", DEFAULT_GRIST_END)
        self.update_hour = options.get("update_hour", DEFAULT_UPDATE_HOUR)
        self.minimum_soc = options.get("minimum_soc", DEFAULT_BATTERY_MIN_SOC)
        self.days_of_load_history = options.get(
            "history_days", DEFAULT_LOAD_AVERAGE_DAYS
        )

        # Reserve space for the forecaster, battery and calculation objects
        self.forecaster = None
        self.battery = None
        self.daily = None

        self.status = Status.STARTING
        self._refresh_boost_next_start = dt_util.now()
        self._daily_task_next_start = dt_util.now()

        # Grid Boost settings
        self.grist_actual: int = DEFAULT_GRIST_STARTING_SOC
        self.grist_calculated: int = DEFAULT_GRIST_STARTING_SOC
        self.pv_adjusted_estimates_history: dict[str, dict[int, int]] = {}

    async def async_setup(self) -> None:
        """Set up the GRIST Scheduler."""
        logger.debug("Setting up GRIST Scheduler. First, select a forecaster.")
        self.status = Status.STARTING

        if not self.hass.is_running:
            logger.debug(
                "Home Assistant not running, deferring forecaster selection until started"
            )
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._async_on_hass_started
            )
            return
        # Hass is running, so continue now
        await self._post_hass_started_setup()

    async def _async_on_hass_started(self, event):
        """Handle Home Assistant started event."""

        logger.debug("Home Assistant started event received, continuing setup")
        await self._post_hass_started_setup()

    async def _post_hass_started_setup(self):
        """Continue setup after Home Assistant is running."""
        await self._select_forecaster()
        if not self.forecaster:
            logger.error("No forecaster available, cannot proceed with setup")
            raise ConfigEntryError(
                "No forecaster available. Checked integrations: solcast_solar, forecast_solar, open_meteo. "
                "Please ensure at least one of these integrations is installed, configured, and running."
            )

        self.battery = Battery(self.hass)
        await self.battery.async_initialize()

        self.daily = DailyStats(self.hass, self.days_of_load_history)
        await self.daily.async_initialize(self.forecaster)

        self.status = Status.NORMAL

        msg = (
            f"{PURPLE}\n-------------------GRIST initialized successfully with the following settings-------------------"
            f"\n   Boost_mode: {self.boost_mode} - Manual SoC: {self.grist_manual}%% - Minimum SoC: {self.minimum_soc}%%"
            f"\n   Boost from: {to_hour(self.grist_start)} - {to_hour(self.grist_end)}, fetching forecast at: {to_hour(self.update_hour)} using {self.days_of_load_history} days of load history"
            f"\n-------------------------------------------------------------------------------------------------{RESET}"
        )
        logger.debug(msg)

    async def _select_forecaster(self) -> bool:
        """Select the forecaster based on which one is in NORMAL status."""
        # Get all config entries for the Forecast.solar domain
        integration_list = ["solcast_solar", "forecast_solar", "open_meteo"]
        # Check if any entry is in the LOADED state
        integration = await self._is_integration_running(integration_list)

        if integration:
            logger.info("%sSelected forecaster: %s%s", PURPLE, integration, RESET)
            if integration == "solcast_solar":
                self.forecaster = Solcast(self.hass)
            elif integration == "forecast_solar":
                self.forecaster = ForecastSolar(self.hass)
                # Could also add a percentile if needed
            elif integration == "open_meteo":
                self.forecaster = Meteo(self.hass)
            if self.forecaster is not None:
                await self.forecaster.async_initialize()
            return True
        logger.info("%s\nNo forecast integration found%s", PURPLE, RESET)
        return False

    async def async_unload_entry(self) -> None:
        """Unload all sub-objects."""
        logger.debug("Unloading Grid Boost sub-objects")
        if self.battery:
            await self.battery.async_unload_entry()
        if self.forecaster:
            await self.forecaster.async_unload_entry()
        if self.daily:
            await self.daily.async_unload_entry()

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
        """Update forecaster, daily and battery data as needed."""
        if self._daily_task_next_start > dt_util.now():
            return

        if self.forecaster and self.daily and self.battery:
            await self.forecaster.update_data()
            await self.daily.update_data(self.forecaster)
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

        logger.debug(
            "\n%s--------------------------------------------------------\nStarting grist._refresh_boost.\n--------------------------------------------------------%s",
            # "\n%s--------------------------------------------------------\nStarting grist._refresh_boost.\nCalled from:%s\n--------------------------------------------------------%s",
            PURPLE,
            # "".join(traceback.format_stack()),
            RESET,
        )

        if self.daily is None or self.battery is None:
            if self.daily is None:
                logger.warning("DailyStats not initialized, cannot refresh boost.")
            if self.battery is None:
                logger.warning("Battery not initialized, cannot refresh boost.")
            return
        adjusted_pv = self.daily.forecast_tomorrow_adjusted
            # Debugging, check adjusted_pv to see if it is all zeros
        if not adjusted_pv or all(value == 0 for value in adjusted_pv.values()):
            logger.warning(
            "HEY! Adjusted PV data is empty or all zeros, skipping boost calculation"
            )
            return

        boost = calculate_required_boost(
            battery_max_wh=self.battery.capacity_wh,
            efficiency=DEFAULT_INVERTER_EFFICIENCY,
            minimum_soc=self.minimum_soc,
            adjusted_pv=self.daily.forecast_tomorrow_adjusted,
            average_hourly_load=self.daily.average_hourly_load,
        )
        # If we could not yet calculate the boost, try again a bit later. Probably because we don't have forecast data yet.
        if boost is None:
            logger.debug("*****Boost could not be calculated yet.*****")
            return

        self.grist_calculated = int(boost) if boost else int(self.grist_manual)
        # Write the boost to the inverter if we are in automatic or manual mode, making sure ToU is on
        tou = await get_switch(self.hass, entity_id=SWITCH_TOU_STATE)
        logger.debug(
            "\n%sHey there. ToU switch state is %s and grist boost_mode is : %s%s",
            PURPLE,
            tou,
            self.boost_mode,
            RESET,
        )
        if self.boost_mode in [BoostMode.AUTOMATIC, BoostMode.MANUAL, "manual"]:
            while tou is False:
                await set_switch(self.hass, entity_id=SWITCH_TOU_STATE, value=True)
                await asyncio.sleep(5)
                tou = await get_switch(self.hass, entity_id=SWITCH_TOU_STATE)
                logger.debug(
                    "\n%sWhile ToU is False loop: Now ToU is %s and grist boost_mode is : %s%s",
                    PURPLE,
                    tou,
                    self.boost_mode,
                    RESET,
                )

        if self.boost_mode == BoostMode.OFF:
            while tou is True:
                await set_switch(self.hass, entity_id=SWITCH_TOU_STATE, value=False)
                await asyncio.sleep(5)
                tou = await get_switch(self.hass, entity_id=SWITCH_TOU_STATE)
                logger.debug(
                    "\n%sWhile ToU is True loop: Now ToU is %s and grist boost_mode is : %s%s",
                    PURPLE,
                    tou,
                    self.boost_mode,
                    RESET,
                )

        if self.boost_mode == BoostMode.AUTOMATIC:
            await set_number(self.hass, NUMBER_CAPACITY_POINT_1, self.grist_calculated)
        elif self.boost_mode == BoostMode.MANUAL:
            await set_number(self.hass, NUMBER_CAPACITY_POINT_1, self.grist_manual)

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

    async def to_dict(self,) -> dict[str, Any]:
        """Return calculated data as a dictionary."""

        # First, check if hass is fully started. If not, return starting status.
        if self.hass.is_running is False:
            logger.debug("Home Assistant is still starting...")
            return {"status": Status.STARTING}

        # Check if the daily tasks need to be run.
        await self._daily_tasks()

        # Check if the refresh boost task needs to be run.
        await self._refresh_boost()

        # Refresh battery statistics on every call so we can calculate remaining battery time.
        await self.battery.update_data() if self.battery else None

        # Initialize key data to send to sensors
        now = dt_util.now()

        # Make sure we have a valid live boost state from the inverter
        boost_actual_state = await get_state(self.hass, NUMBER_CAPACITY_POINT_1)
        if boost_actual_state is not None:
            try:
                boost_actual = int(round(float(boost_actual_state), 0))
            except (ValueError, TypeError):
                logger.warning(
                    "Grid boost actual value is invalid, using default value."
                )
                boost_actual = DEFAULT_GRIST_STARTING_SOC
        else:
            logger.warning("Grid boost actual value is None, using default value.")
            boost_actual = DEFAULT_GRIST_STARTING_SOC

        remaining_battery_time: int = await self._calculate_remaining_battery_time()

        # Return the dictionary with all the calculated data
        return {
            "status": self.status,
            "battery_exhausted": (
                now + timedelta(minutes=remaining_battery_time)
            ).strftime("%a %-I:%M %p"),
            "battery_time_remaining": round(remaining_battery_time / 60, 1),
            "grist_actual": boost_actual if boost_actual is not None else "Unknown",
            "grist_manual": self.grist_manual,
            "grist_mode": self.boost_mode,
            "grist_calculated": self.grist_calculated,
            "grist_day": f"{(now + timedelta(days=1)).strftime('%A')} the {ordinal((now + timedelta(days=1)).day)}",
            # "grist_start": self.grist_start,
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
