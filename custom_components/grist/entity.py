"""Entities for the GRIST Scheduler integration.

Defines entity classes for representing the state and statistics of the GRIST Scheduler
in Home Assistant. These entities expose calculated and forecasted data such as
scheduler status, PV performance ratios, average hourly load, PV forecasts, battery
life estimates, and chart data for dashboards.

All entities use the update coordinator pattern for efficient polling and state updates.
Each entity exposes extra state attributes for use in dashboards and automations.

Classes:
    SchedulerEntity: Represents the overall scheduler state and configuration.
    RatioEntity: Exposes hourly PV performance ratios.
    LoadEntity: Exposes average hourly load.
    PVEntityToday: Exposes calculated PV generation for today.
    PVEntityTomorrow: Exposes calculated PV generation for tomorrow.
    BatteryLifeEntity: Estimates the time when the battery will be exhausted.
    ApexChartEntity: Provides data for Apex Chart dashboard cards.

Helper Functions:
    format_hourly_data: Formats hourly data for display or charting.
    summarize_hourly_data: Summarizes hourly data for quick statistics.

All I/O is asynchronous and compatible with Home Assistant's async patterns.
"""

import logging
import re
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from .const import DEBUGGING, DOMAIN, NBSP

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUGGING else logging.INFO)


def printable_hour(hour: int | str) -> str:
    """Return an easily readable hour.

    Args:
        hour: Hour in 24-hour format (0-23).

    Returns:
        Formatted string with midnight # am, noon, # pm

    """
    if hour == 'n/a':
        return "n/a"
    if type(hour) is str:
        return hour
    if hour == 0:
        return "midnight"
    if isinstance(hour, int):
        if hour < 12:
            return f"{hour} am"
        if hour == 12:
            return "noon"
        if hour < 24:
            return f"{hour} pm"
        return str(hour)
    return str(hour)


def count_data(input_str: str) -> int:
    """Count the number of dictionary values greater than zero in a string representation.

    Args:
        input_str: String representation of a dictionary.

    Returns:
        The count of values greater than zero.

    """
    input_str = input_str.strip("{}")
    pairs = re.split(r",\s*(?![^{}]*\})", input_str)
    result = 0
    if pairs == [""]:
        return result
    for pair in pairs:
        _, value = pair.split(":")
        if float(value.strip()) > 0.0:
            result += 1
    return result


def sum_data(input_str: str) -> int:
    """Sum the values in a string representation of a dictionary.

    Args:
        input_str: String representation of a dictionary.

    Returns:
        The sum of all values, rounded to the nearest integer.

    """
    input_str = input_str.strip("{}")
    if input_str == "":
        return 0
    pairs = re.split(r",\s*(?![^{}]*\})", input_str)
    result = 0.0
    for pair in pairs:
        _, value = pair.split(":")
        result += float(value.strip())
    return int(round(result, 0))


class SchedulerEntity(CoordinatorEntity):
    """Entity representing the GRIST scheduler overview and configuration."""

    def __init__(
        self,
        entry_id: str,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
    ) -> None:
        """Initialize the scheduler entity."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_GRIST_scheduler"
        self._attr_icon = "mdi:toggle-switch"
        self._attr_name = "GRIST scheduler"
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=self._attr_name,
        )

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return extra state attributes for the scheduler entity.

        Includes status, manual and calculated boost, minimum SoC, load days,
        update hour, and PV forecasts for today and tomorrow.
        """
        days = self.coordinator.data.get('load_days', 'n/a')
        if days == 'n/a':
            days = "n/a"
        elif days == '1':
            days = '1 day'
        else:
            days = f"{days} days"

        return {
            "status": self.coordinator.data.get("status", "n/a"),
            "forecaster_status": self.coordinator.data.get("forecaster_status", "n/a"),
            "mode": self.coordinator.data.get("mode", "n/a"),
            "calculated": f"{self.coordinator.data.get('calculated', 'n/a')}%" if self.coordinator.data.get("calculated") is not None else "n/a",
            "manual": f"{self.coordinator.data.get('manual', 'n/a')}%" if self.coordinator.data.get("manual") is not None else "n/a",
            "actual": f"{self.coordinator.data.get('actual', 'n/a')}%" if self.coordinator.data.get("actual") is not None else "n/a",
            "minimum_soc": f"{self.coordinator.data.get('min_soc', 'n/a')}%" if self.coordinator.data.get("min_soc") is not None else "n/a",
            "load_days": days,
            "start": printable_hour(self.coordinator.data.get("start", "n/a")),
            "end": printable_hour(self.coordinator.data.get("end", "n/a")),
            "update_hour": printable_hour(self.coordinator.data.get("update_hour", "n/a")),
        }

    @property
    def name(self) -> str | None:
        """Return the name of the scheduler entity."""
        return self._attr_name

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID for the scheduler entity."""
        return self._attr_unique_id

    @property
    def state(self) -> str:
        """Return the current mode of the scheduler."""
        return f"{self.coordinator.data.get('status', 'Status n/a')}: {self.coordinator.data.get('mode', 'Mode n/a')}"


class RatioEntity(CoordinatorEntity):
    """Entity representing hourly PV performance ratios."""

    def __init__(
        self,
        entry_id: str,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
    ) -> None:
        """Initialize the PV ratio entity."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_pv_ratio"
        self._attr_icon = "mdi:toggle-switch"
        self._attr_name = "GRIST PV ratio"
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=self._attr_name,
        )

    @property
    def name(self) -> str | None:
        """Return the name of the PV ratio entity."""
        return self._attr_name

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID for the PV ratio entity."""
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info for the PV ratio entity."""
        return self._device_info

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return hourly PV ratio values as state attributes."""
        hours: dict[int, float] = self._coordinator.data.get("pv_ratios", {})
        converted_hours: dict[str, str] = {
            printable_hour(hour): f"{ratio:>3.1f}" for hour, ratio in hours.items()
        }
        if not converted_hours:
            day = dt_util.now().strftime("%a")
            return {"No pv ratios found": day}
        return converted_hours

    @property
    def state(self) -> str | int | float | None:
        """Return a summary of hours with unique PV ratios."""
        if not self._coordinator.data or "pv_ratios" not in self._coordinator.data:
            return "No PV ratios available"
        count = sum(
            1
            for ratio in self._coordinator.data.get("pv_ratios", {}).values()
            if ratio != 1.0
        )
        if count == 1:
            return "1 hour with a unique ratio"
        if count > 0:
            return f"{count} hours with unique ratios"
        return "No unique ratios found"


class LoadEntity(CoordinatorEntity):
    """Entity representing the average hourly load."""

    def __init__(
        self,
        entry_id: str,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
    ) -> None:
        """Initialize the load entity."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_load"
        self._attr_icon = "mdi:toggle-switch"
        self._attr_name = "GRIST load"
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=self._attr_name,
        )

    @property
    def name(self) -> str | None:
        """Return the name of the load entity."""
        return self._attr_name

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID for the load entity."""
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info for the load entity."""
        return self._device_info

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return hourly load values as state attributes."""
        hours: dict[int, int] = self._coordinator.data.get("load_averages", {})
        converted_hours: dict[str, str] = {
            printable_hour(
                hour
            ): f"{NBSP * 2 if watts > 999 else ''}{watts:,.0f}".replace(
                ",", " ,"
            ).rjust(7, NBSP)
            + "w"
            for hour, watts in hours.items()
        }
        if not converted_hours:
            day = dt_util.now().strftime("%a")
            return {"No load averages found": day}
        return converted_hours

    @property
    def state(self) -> str | int | float | None:
        """Return the total average daily load in kWh."""
        data: dict[int, int] = self._coordinator.data.get("load_averages", {})
        total_load = round(sum(data.values()) / 1000, 1)
        return f"{total_load} kWh"


class PVEntity_today(CoordinatorEntity):
    """Entity representing calculated PV generation for today."""

    def __init__(
        self,
        entry_id: str,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
    ) -> None:
        """Initialize the PV today entity."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_pv_generation_today"
        self._attr_icon = "mdi:toggle-switch"
        self._attr_name = "GRIST PV Today"
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=self._attr_name,
        )

    @property
    def name(self) -> str | None:
        """Return the name of the PV today entity."""
        return f"PV for {self._coordinator.data.get('pv_calculated_today_day', '')}"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID for the PV today entity."""
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info for the PV today entity."""
        return self._device_info

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the hourly PV generation values as state attributes."""
        hours: dict[int, float] = self._coordinator.data.get("pv_calculated_today", {})
        converted_hours: dict[str, str] = {
            printable_hour(
                hour
            ): f"{NBSP * 2 if watts > 999 else ''}{watts:,.0f}".replace(
                ",", " ,"
            ).rjust(7, NBSP)
            + "w"
            for hour, watts in hours.items()
        }
        if not converted_hours:
            day: str = self._coordinator.data.get("pv_calculated_today_day", "")
            return {"No pv generation found": day}
        return converted_hours

    @property
    def state(self) -> str | int | float | None:
        """Return the state of the sensor."""
        return f"{self._coordinator.data.get('pv_calculated_today_total', 0) / 1000:.1f} kWh"


class PVEntity_tomorrow(CoordinatorEntity):
    """Entity representing calculated PV generation for tomorrow."""

    def __init__(
        self,
        entry_id: str,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
    ) -> None:
        """Initialize the PV tomorrow entity."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_pv_generation_tomorrow"
        self._attr_icon = "mdi:toggle-switch"
        self._attr_name = "GRIST PV Tomorrow"
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=self._attr_name,
        )

    @property
    def name(self) -> str | None:
        """Return the name of the PV tomorrow entity."""
        return f"PV for {self._coordinator.data.get('pv_calculated_tomorrow_day', '')}"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID for the PV tomorrow entity."""
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info for the PV tomorrow entity."""
        return self._device_info

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the hourly PV generation values as state attributes."""
        hours: dict[int, float] = self._coordinator.data.get(
            "pv_calculated_tomorrow", 0
        )
        if not hours:
            day: str = self._coordinator.data.get("pv_calculated_tomorrow_day", "")
            return {"No pv generation found": day}
        converted_hours: dict[str, str] = {
            printable_hour(hour): f"{NBSP if watts > 999 else ''}{watts:,.0f}".replace(
                ",", " ,"
            ).rjust(7, NBSP)
            + "w"
            for hour, watts in hours.items()
        }
        return converted_hours

    @property
    def state(self) -> str | int | float | None:
        """Return the state of the sensor."""
        return f"{self._coordinator.data.get('pv_calculated_tomorrow_total', 0) / 1000:.1f} kWh"


class BatteryLifeEntity(CoordinatorEntity):
    """Representation of the battery life.

    This sensor is used to display the battery life for the day if available.
    """

    def __init__(
        self,
        entry_id: str,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        # parent: str,
    ) -> None:
        """Initialize the sensor."""

        super().__init__(coordinator)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_battery_exhausted"
        self._attr_icon = "mdi:clock-alert"
        self._attr_name = "Battery exhausted"
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=self._attr_name,
        )

    @property
    def name(self) -> str | None:
        """Return the name of the sensor."""
        return self._attr_name

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self._device_info

    @property
    def state(self) -> str | int | float | None:
        """Return the state of the sensor."""
        remaining: str = self._coordinator.data.get(
            "battery_exhausted", dt_util.now().strftime("%a %-I:%M %p")
        )
        return remaining

