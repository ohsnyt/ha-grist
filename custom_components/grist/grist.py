"""GRIST Scheduler integration for Home Assistant.

Handles Time-of-Use battery and grid boost management, including scheduling, storage, and forecast calculations.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
import homeassistant.helpers.entity_registry as er
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
    FORECASTER_INTEGRATIONS,
    NUMBER_CAPACITY_POINT_1,
    PURPLE,
    RESET,
    SWITCH_TOU_STATE,
    UPDATE_INTERVAL,
    BoostMode,
    Status,
)
from .forecasters.forecast_solar import ForecastSolar
from .forecasters.meteo import Meteo
from .forecasters.solcast import Solcast
from .statistics_calcs import DailyStats

logger: logging.Logger = logging.getLogger(__name__)
if DEBUGGING:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)

FORECASTER_CLASS_MAP = {
    "solcast_solar": Solcast,
    "forecast_solar": ForecastSolar,
    "open_meteo_solar_forecast": Meteo,
}

class MQTTFailures:
    """Track MQTT failures for the GRIST Scheduler."""

    def __init__(self) -> None:
        """Initialize MQTT failure tracking."""
        self._faults: int = 0
        self._errors: int = 0
        self._repeating: int = 0

    def log_failure(self, topic: Status) -> None:
        """Log a failure for a specific MQTT topic."""
        if topic == Status.MQTT_OFF:
            self._faults += 1
        else:
            self._errors += 1
            self._repeating += 1
        logger.debug(
            "\n%sMQTT failure logged. Current faults: %s, errors: %s, repeating: %s%s",
            PURPLE,
            self._faults,
            self._errors,
            self._repeating,
            RESET
        )

    def log_normal(self) -> None:
        """Log a normal (successful) state for the MQTT topic."""
        self._repeating = 0

    @property
    def faults(self) -> int:
        """Get the number of faults (MQTT_OFF) for the GRIST Scheduler."""
        return self._faults

    @property
    def errors(self) -> int:
        """Get the number of errors (MQTT_ON) for the GRIST Scheduler."""
        return self._errors

    @property
    def repeating(self) -> int:
        """Get the number of repeating errors (MQTT_REPEATING) for the GRIST Scheduler."""
        return self._repeating


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
        self.days_of_load_history = options.get("history_days", DEFAULT_LOAD_AVERAGE_DAYS)

        # Reserve space for the forecaster, battery and calculation objects
        self.forecaster = None
        self.forecaster_tag = None
        self.battery = None
        self.calculated_stats = None

        self.status = Status.STARTING
        self._refresh_boost_next_start = dt_util.now()
        self._update_task_next_start = dt_util.now()
        self._mqtt_failures = MQTTFailures()

        # GRIST settings
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
        # Update will ensure we have forecaster, battery, and daily stats objects initialized.
        await self._update()

        msg = (
            f"{PURPLE}\n-------------------GRIST initialized successfully with the following settings-------------------"
            f"\n   Boost_mode: {self.boost_mode} - Manual SoC: {self.grist_manual}% - Minimum SoC: {self.minimum_soc}%"
            f"\n   Boost from: {to_hour(self.grist_start)} - {to_hour(self.grist_end)}, fetching forecast at: {to_hour(self.update_hour)} using {self.days_of_load_history} days of load history"
            f"\n-------------------------------------------------------------------------------------------------{RESET}"
        )
        logger.debug(msg)

    async def _select_forecaster(self):
        """Select the forecaster based on which one is in NORMAL status."""
        # Check which forecaster integrations are available and running
        integration = await self._is_integration_running(FORECASTER_INTEGRATIONS)
        # If we found a running integration, select it and initialize it.
        if integration:
            klass = FORECASTER_CLASS_MAP[integration]
            self.forecaster = klass(self.hass)
            self.forecaster_tag = integration
        if self.forecaster is not None:
            logger.info(
                "Selected forecaster: %s", getattr(self.forecaster, "name", integration)
            )
            await self.forecaster.async_initialize()
            # Set the status to NORMAL and return
            self.status = Status.NORMAL
            return
        # If we didn't find a running integration, log a warning
        logger.warning("No forecast integration found")
        self.status = Status.NOT_CONFIGURED

    async def async_unload_entry(self) -> None:
        """Unload all sub-objects."""
        logger.debug("Unloading GRIST sub-objects")
        if self.battery:
            await self.battery.async_unload_entry()
        if self.forecaster:
            await self.forecaster.async_unload_entry()
        if self.calculated_stats:
            await self.calculated_stats.async_unload_entry()

    async def _is_integration_running(self, integration_list: list) -> str | None:
        """Check if any integration domain in the provided list is currently running (i.e., in the LOADED state).

        Args:
            integration_list (list): List of integration domain names to check.

        Returns:
            str | None: The domain name of the first integration found in the LOADED state, or None if none are loaded.

        """
        # Get all config entries for the integration domain
        all_entries: list[ConfigEntry] = self.hass.config_entries.async_entries()
        # Filter entries for the specific integration
        if not all_entries:
            logger.warning(
                "No forecaster entries found in your system! Looked for %s",
                integration_list,
            )
            self.forecaster = None
            self.status = Status.NOT_CONFIGURED
            return None

        # Build a mapping from domain to entries for efficient lookup
        domain_to_entries = {}
        for entry in all_entries:
            domain_to_entries.setdefault(entry.domain, []).append(entry)

        for integration in integration_list:
            entries = domain_to_entries.get(integration, [])
            if any(entry.state == ConfigEntryState.LOADED for entry in entries):
                return integration

        # No running integration found, set status and forecaster once here
        self.forecaster = None
        self.status = Status.NOT_CONFIGURED
        logger.warning("No running integration found in %s", integration_list)
        return None

    async def _update(self) -> None:
        """Update forecaster, daily and battery data as needed."""
        if DEBUGGING and self._update_task_next_start > dt_util.now():
            logger.debug("Next update in %s hours and %s minutes", (self._update_task_next_start - dt_util.now()).seconds // 3600, (self._update_task_next_start - dt_util.now()).seconds // 60 % 60)
            return

        # Verify that the forecaster is still loaded
        if self.forecaster_tag and await self._is_integration_running([self.forecaster_tag]):
            pass
        else:
            self.status = Status.NOT_CONFIGURED
            # If not, try to load one
            logger.warning(
                "%s\n%s... Trying to find and start a forecaster.%s",
                PURPLE,
                f"{self.forecaster_tag} is not currently running" if self.forecaster_tag else 'No forecaster is currently running',
                RESET,
            )
            await self._select_forecaster()

            if self.status != Status.NORMAL:
                logger.warning(
                    "No suitable forecaster found. Will retry in %s seconds",
                    UPDATE_INTERVAL,
                )
                return

            # Got a new forecaster. Make sure we also have battery and daily statistics objects
            self.battery = Battery(self.hass) if not self.battery else self.battery
            self.calculated_stats = (
                DailyStats(self.hass, self.days_of_load_history)
                if not self.calculated_stats
                else self.calculated_stats
            )

        # We have a forecaster, daily stats, and battery objects so update them.
        if self.forecaster and self.calculated_stats and self.battery:
            await self.forecaster.update_data()
            await self.calculated_stats.update_data(self.forecaster)
            await self.battery.update_data()
            if self.battery is not None:
                if self.battery is not None:
                    self._mqtt_failures.log_failure(self.battery.status) if self.battery.status != Status.NORMAL else self._mqtt_failures.log_normal()

            if self.forecaster.status == Status.NORMAL and self.calculated_stats.status == Status.NORMAL and self.battery.status == Status.NORMAL:
                self.status = Status.NORMAL
        else:
            # Just in case something is missing. We should never get here.
            if not self.forecaster:
                logger.warning("Forecaster system not configured")
            if not self.calculated_stats:
                logger.warning("Calculated Stats system not configured")
            if not self.battery:
                logger.warning("Battery system not configured")
            self.status = Status.NOT_CONFIGURED
            return

        # Reset daily task next start time.
        # If the current time is before the update hour, schedule the next update to the user's update hour.
        # This will gather the latest forecast data to accurately calculate boost levels for the upcoming day.
        if dt_util.now().hour < self.update_hour:
            self._update_task_next_start = dt_util.now().replace(
                hour=self.update_hour, minute=0, second=0, microsecond=0
            )
        else:
            # If the current time is after the update hour, schedule the next update for the next day.
            # This early morning run will update load and PV ratios based on the previous day's data.
            self._update_task_next_start = dt_util.now().replace(
                hour=0, minute=2, second=0, microsecond=0
            ) + timedelta(days=1)

    async def _refresh_boost(self) -> None:
        """Recalculate statistics once an hour."""
        if self._refresh_boost_next_start > dt_util.now():
            return
        next_update = self.forecaster.next_update if self.forecaster else None
        logger.debug(
            "\n%s%s\nStarting grist._refresh_boost with forecast from %s. Next update at %s.\n%s%s",
            PURPLE,
            "-" * 80,
            self.forecaster.name if self.forecaster else "Unknown",
            next_update.strftime("%a %I:%M %p") if next_update else "Unknown",
            "-" * 80,
            RESET,
        )

        if self.calculated_stats is None or self.battery is None:
            if self.calculated_stats is None:
                logger.warning("DailyStats not initialized, cannot refresh boost.")
            if self.battery is None:
                logger.warning("Battery not initialized, cannot refresh boost.")
            return
        adjusted_pv: dict[int, int] = self.calculated_stats.forecast_tomorrow_adjusted
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
            adjusted_pv=self.calculated_stats.forecast_tomorrow_adjusted,
            average_hourly_load=self.calculated_stats.average_hourly_load,
        )
        # If we could not yet calculate the boost, try again a bit later. Probably because we don't have forecast data yet.
        if boost is None:
            logger.debug("*****Boost could not be calculated yet.*****")
            return

        self.grist_calculated = int(boost) if boost else int(self.grist_manual)
        # Make sure MQTT is on
        if "mqtt" not in self.hass.config.components:
            logger.error("MQTT system is not running")
            self.status = Status.MQTT_OFF
            return

        # Make sure ToU is on before we write
        tou = False
        state = self.hass.states.get(SWITCH_TOU_STATE)
        if not state:
            logger.error("MQTT entity %s could not be accessed", SWITCH_TOU_STATE)
            self.status = Status.FAULT
            return
        if state.state == "on":
            tou = True
        logger.debug(
            "\n%sHey there. ToU switch state is %s and grist boost_mode is : %s%s",
            PURPLE,
            tou,
            self.boost_mode,
            RESET,
        )

        # If boost mode is automatic or manual, we need to try to turn on the ToU switch.
        # Since this is a critical operation, we need to ensure it succeeds.
        counter = 0
        if self.boost_mode in [BoostMode.AUTOMATIC, BoostMode.MANUAL]:
            while tou is False:
                await self.hass.services.async_call(
                    "switch", "turn_on", {"entity_id": SWITCH_TOU_STATE}
                )
                await asyncio.sleep(5)
                state = self.hass.states.get(SWITCH_TOU_STATE)
                if not state:
                    logger.error("MQTT entity %s could not be accessed", SWITCH_TOU_STATE)
                    self.status = Status.FAULT
                    return
                logger.debug(
                    "\n%sWhile ToU is False loop: Now ToU is %s and grist boost_mode is : %s%s",
                    PURPLE,
                    tou,
                    self.boost_mode,
                    RESET,
                )
                if state == "on":
                    tou = True
                counter += 1
                if counter > 5:
                    logger.error("Could not turn on ToU switch after 5 attempts")
                    self.status = Status.FAULT
                    return

        if self.boost_mode == BoostMode.OFF:
            while tou is True:
                await self.hass.services.async_call(
                    "switch", "turn_off", {"entity_id": SWITCH_TOU_STATE}
                )
                await asyncio.sleep(5)
                state = self.hass.states.get(SWITCH_TOU_STATE)
                if not state:
                    logger.error("MQTT entity %s could not be accessed", SWITCH_TOU_STATE)
                    self.status = Status.FAULT
                    return
                logger.debug(
                    "\n%sTrying to turn off ToU mode: Now ToU is %s and grist boost_mode is : %s%s",
                    PURPLE,
                    tou,
                    self.boost_mode,
                    RESET,
                )
                if state == "off":
                    tou = False
                counter += 1
                if counter > 5:
                    logger.error("Could not turn off ToU switch after 5 attempts")
                    self.status = Status.FAULT
                    return

        # If the switch setting worked, we should have no problems here. We won't doublecheck the setting.
        if self.boost_mode == BoostMode.AUTOMATIC:
            await self.hass.services.async_call(
                "number", "set_value", {"entity_id": NUMBER_CAPACITY_POINT_1, "value": self.grist_calculated}
            )
        elif self.boost_mode == BoostMode.MANUAL:
            await self.hass.services.async_call(
                "number", "set_value", {"entity_id": NUMBER_CAPACITY_POINT_1, "value": self.grist_manual}
            )

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

        if not self.calculated_stats:
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
        loads = self.calculated_stats.average_hourly_load if self.calculated_stats else {}
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
            hour: pv.get(hour, 0) * self.calculated_stats.pv_performance_ratios.get(hour, 1.0)
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
                    * self.calculated_stats.pv_performance_ratios.get(hour, 1.0)
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

        # First, check if hass is fully started. If not, return starting status.
        if self.hass.is_running is False:
            logger.debug("Home Assistant is still starting...")
            return {"status": Status.STARTING}

        # Check if the major data update tasks need to be run.
        await self._update()

        # If daily tasks triggered a fault, report that. We can't continue.
        if not self.forecaster or self.forecaster.status != Status.NORMAL:
            return {"status": Status.FAULT}

        # Check if the refresh boost task needs to be run.
        await self._refresh_boost()

        # Refresh battery statistics on every call so we can calculate remaining battery time.
        await self.battery.update_data() if self.battery else None
        self._mqtt_failures.log_failure(self.battery.status) if self.battery.status != Status.NORMAL else self._mqtt_failures.log_normal()


        # Initialize key data to send to sensors
        now = dt_util.now()

        # Make sure we have a valid live boost state from the inverter
        state = self.hass.states.get(NUMBER_CAPACITY_POINT_1)
        if not state:
            logger.error("MQTT entity %s could not be accessed", NUMBER_CAPACITY_POINT_1)
            self._mqtt_failures.log_failure(Status.MQTT_OFF)
            return {"status": Status.FAULT}
        try:
            boost_actual = float(state.state) / 100
        except (ValueError, TypeError):
            logger.warning("Invalid state for entity %s: %s", NUMBER_CAPACITY_POINT_1, state.state)
            self.status = Status.FAULT
            self._mqtt_failures.log_failure(Status.MQTT_OFF)
            return {"status": Status.FAULT}

        remaining_battery_time: int = await self._calculate_remaining_battery_time()

        calculated_pv_now: int = (
            self.calculated_stats.forecast_today_adjusted.get(now.hour, 0) if self.calculated_stats else 0
        )

        if self.battery is not None and self.battery.status == Status.NORMAL:
            self._mqtt_failures.log_normal()

        # Return the dictionary with all the calculated data
        return {
            "status": self.status.name
            if hasattr(self.status, "name")
            else str(self.status),
            "forecaster_status": (
                self.forecaster.status.name
                if self.forecaster and hasattr(self.forecaster.status, "name")
                else str(self.forecaster.status)
                if self.forecaster
                else "None"
            ),
            "battery_exhausted": (
                now + timedelta(minutes=remaining_battery_time)
            ).strftime("%a %-I:%M %p"),
            "battery_time_remaining": round(remaining_battery_time / 60, 1),
            "actual": boost_actual,
            "manual": self.grist_manual,
            "mode": str(self.boost_mode).title() if self.boost_mode else None,
            "calculated": self.grist_calculated,
            "calculated_pv_now": calculated_pv_now,
            "day": f"{(now + timedelta(days=1)).strftime('%A')} the {ordinal((now + timedelta(days=1)).day)}",
            "load_days": self.days_of_load_history,
            "load_averages": self.calculated_stats.average_hourly_load if self.calculated_stats else {},
            "pv_ratios": self.calculated_stats.pv_performance_ratios if self.calculated_stats else {},
            "pv_calculated_today": self.calculated_stats.forecast_today_adjusted
            if self.calculated_stats
            else {},
            "pv_calculated_today_total": self.calculated_stats.forecast_today_adjusted_total
            if self.calculated_stats
            else 0,
            "pv_calculated_today_day": f"{now.strftime('%A')} the {ordinal(now.day)}",
            "pv_calculated_tomorrow": self.calculated_stats.forecast_tomorrow_adjusted
            if self.calculated_stats
            else {},
            "pv_calculated_tomorrow_total": self.calculated_stats.forecast_tomorrow_adjusted_total
            if self.calculated_stats
            else 0,
            "pv_calculated_tomorrow_day": f"{(now + timedelta(days=1)).strftime('%A')} the {ordinal((now + timedelta(days=1)).day)}",
            "update_hour": self.update_hour,
            "min_soc": self.minimum_soc,
            "start": self.grist_start,
            "end": self.grist_end,
        }
