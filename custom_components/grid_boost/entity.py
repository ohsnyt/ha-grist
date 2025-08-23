"""Entity classes for Grid Boost entity.

This module defines various entity classes used in the Grid Boost Scheduler integration.
(These are specialized sensors. They share some similarity with the sensors, notably the use of "im_a" to identify the entity type.)
Each entity class represents a different aspect of the Grid Boost that is of special interest to the user:
    the scheduler,
    the calculated daily shading, and
    the calculated average daily load.
"""

from datetime import datetime, timedelta
import logging
import re
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from .const import DEBUGGING, DOMAIN, Status

logger = logging.getLogger(__name__)
if DEBUGGING:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)


# Helper functions
def printable_hour(hour: int) -> str:
    """Return a printable hour string in 12-hour format with 'am' or 'pm' suffix.

    Args:
        hour: Hour in 24-hour format (0-23).

    Returns:
        Formatted string in 12-hour format with am/pm.

    """
    thehour = hour % 12 if hour > 0 else 12  # Convert 0 to 12 for midnight
    return f"{'\u00a0\u00a0' if thehour < 10 else ''}{thehour} {'am' if hour < 12 else 'pm'}"


def count_data(input_str: str) -> int:
    """Convert a string representation of a dictionary to an actual dictionary.

    Args:
        input_str: String representation of a dictionary.

    Returns:
        A dictionary with integer keys and float values.

    """
    # Remove the curly braces
    input_str = input_str.strip("{}")
    # Split the string into key-value pairs
    pairs = re.split(r",\s*(?![^{}]*\})", input_str)
    result = 0
    if pairs == [""]:
        return result
    for pair in pairs:
        # Split each pair into key and value
        key, value = pair.split(":")
        # Convert key and value to appropriate types and add to the dictionary
        if float(value.strip()) > 0.0:
            result += 1
    return result


def sum_data(input_str: str) -> int:
    """Convert a string representation of a dictionary to an actual dictionary.

    Args:
        input_str: String representation of a dictionary.

    Returns:
        A dictionary with integer keys and float values.

    """
    # Remove the curly braces
    input_str = input_str.strip("{}")
    # Check for empty data
    if input_str == "":
        return 0
    # Split the string into key-value pairs
    pairs = re.split(r",\s*(?![^{}]*\})", input_str)
    result = 0.0
    for pair in pairs:
        # Split each pair into key and value
        key, value = pair.split(":")
        # Convert key and value to appropriate types and add to the dictionary
        result += float(value.strip())
    return int(round(result, 0))


class SchedulerEntity(CoordinatorEntity):
    """Class for Grid Boost entity."""

    def __init__(
        self,
        entry_id: str,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        # parent: str,
    ) -> None:
        """Initialize the sensor."""

        super().__init__(coordinator)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_scheduler"
        self._attr_icon = "mdi:toggle-switch"
        self._attr_name = "GB scheduler"
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=self._attr_name,
        )

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Returns a dictionary of extra state attributes for the entity.

        The attributes include:
            - status: The current status of the coordinator data, or a default status if not configured.
            - manual: The manual grid boost value, defaulting to 30 if not set.
            - calculated: The calculated boost value, defaulting to 20 if not set.
            - min_soc: The minimum state of charge, defaulting to 20 if not set.
            - load_days: The number of load days, defaulting to 3 if not set.
            - update_hour: The hour at which updates occur, defaulting to 3 if not set.
            - forecast_today: A string containing today's day abbreviation and PV calculation for today.
            - forecast_tomorrow: A string containing tomorrow's day abbreviation and PV calculation for tomorrow.

        Returns:
            dict[str, str]: A dictionary mapping attribute names to their string values.

        """
        now = dt_util.now()
        today: str = now.strftime("%a")
        tomorrow: str = (now + timedelta(days=1)).strftime("%a")
        return {
            "status": self.coordinator.data.get("status", Status.NOT_CONFIGURED).state,
            "manual": self.coordinator.data.get("manual_grid_boost", 30),
            "calculated": self.coordinator.data.get("grid_boost_calculated", 20),
            "min_soc": self.coordinator.data.get("min_soc", 20),
            "load_days": self.coordinator.data.get("load_days", 3),
            "update_hour": self.coordinator.data.get("update_hour", 3),
            "forecast_today": f"({today}) {self.coordinator.data.get('pv_calculated_today_day', 0)}",
            "forecast_tomorrow": f"({tomorrow}) {self.coordinator.data.get('pv_calculated_tomorrow_day', 0)}",
        }

    @property
    def name(self) -> str | None:
        """Return the name of the sensor."""
        return self._attr_name

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._attr_unique_id

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        return self.coordinator.data.get("grid_boost_mode", "State unknown")


class RatioEntity(CoordinatorEntity):
    """Representation of a PV Shading Ratio.

    This sensor is used to display the shading ratio for each hour of the day if available. If there is more
    sun than expected, this sensor will display the ratio as a positive number.
    If we are unable to get the shading ratio, the sensor will display "No shading percentages available".
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
        self._attr_unique_id = f"{entry_id}_pv_ratio"
        self._attr_icon = "mdi:toggle-switch"
        self._attr_name = "GB PV ratio"
        self._count: int = 0
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
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the hourly pv ratio values as dict[str,str]."""
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
        """Return the count of hours with ratios > 0."""
        if not self._coordinator.data or "pv_ratios" not in self._coordinator.data:
            return "No shading percentages available"
        # Count hours with ratios < 0
        count = 0
        all_hours = self._coordinator.data.get("pv_ratios", {})
        for ratio in all_hours.values():
            if ratio < 0:
                count += 1
        if count == 1:
            return "1 hour with shading"
        if count > 0:
            return f"{count} hours with shading"
        return "No shading found"


class LoadEntity(CoordinatorEntity):
    """Representation of the average daily load.

    This sensor is used to display the average daily load for each hour of the day if available.
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
        self._attr_unique_id = f"{entry_id}_load"
        self._attr_icon = "mdi:toggle-switch"
        self._attr_name = "GB load"
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
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the hourly load values as dict[str,str]."""
        hours: dict[int, int] = self._coordinator.data.get("load_averages", {})
        # Use a Unicode "figure space" (\u2007) for padding, which matches digit width
        converted_hours: dict[str, str] = {
            printable_hour(
                hour
            ): f"{'\u2007\u2007' if watts > 999 else ''}{watts:,.0f}".replace(
                ",", " ,"
            ).rjust(7, "\u2007")
            + "w"
            for hour, watts in hours.items()
        }
        if not converted_hours:
            day = dt_util.now().strftime("%a")
            return {"No load averages found": day}
        # Convert the values to a more readable format
        printable_hours: dict[str, str] = converted_hours
        return printable_hours

    @property
    def state(self) -> str | int | float | None:
        """Return the state of the sensor."""
        data: dict[int, int] = self._coordinator.data.get("load_averages", {})
        total_load = round(sum(data.values()) / 1000, 1)
        return f"{total_load} kWh"


class PVEntity_today(CoordinatorEntity):
    """Representation of the calculated PV generation for today.

    This sensor is used to display the calculated PV generation for each hour of the day if available.
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
        self._attr_unique_id = f"{entry_id}_pv_generation_today"
        self._attr_icon = "mdi:toggle-switch"
        self._attr_name = "GB PV Today"
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=self._attr_name,
        )

    @property
    def name(self) -> str | None:
        """Return the name of the sensor."""
        return f"PV for {self._coordinator.data.get('pv_calculated_today_day', '')}"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self._device_info

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the hourly pv generation values as dict[str,str]."""
        hours: dict[int, float] = self._coordinator.data.get("pv_calculated_today", {})
        converted_hours: dict[str, str] = {
            printable_hour(
                hour
            ): f"{'\u2007\u2007' if watts > 999 else ''}{watts:,.0f}".replace(
                ",", " ,"
            ).rjust(7, "\u2007")
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
    """Representation of the calculated PV generation for tomorrow.

    This sensor is used to display the calculated PV generation for each hour of the day if available.
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
        self._attr_unique_id = f"{entry_id}_pv_generation_tomorrow"
        self._attr_icon = "mdi:toggle-switch"
        self._attr_name = "GB PV Tomorrow"
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=self._attr_name,
        )

    @property
    def name(self) -> str | None:
        """Return the name of the sensor."""
        return f"PV for {self._coordinator.data.get('pv_calculated_tomorrow_day', '')}"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return self._device_info

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the hourly pv generation values as dict[str,str]."""
        hours: dict[int, float] = self._coordinator.data.get(
            "pv_calculated_tomorrow", 0
        )
        if not hours:
            day: str = self._coordinator.data.get("pv_calculated_tomorrow_day", "")
            return {"No pv generation found": day}
        converted_hours: dict[str, str] = {
            printable_hour(
                hour
            ): f"{'\u2007\u2007' if watts > 999 else ''}{watts:,.0f}".replace(
                ",", " ,"
            ).rjust(7, "\u2007")
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


class BoostEntity(CoordinatorEntity):
    """Class for Grid Boost entity."""

    def __init__(
        self,
        entry_id: str,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        # parent: str,
    ) -> None:
        """Initialize the sensor."""

        super().__init__(coordinator)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_boost"
        self._attr_icon = "mdi:toggle-switch"
        self._attr_name = "Grid Boost"
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=self._attr_name,
        )

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the extra state attributes."""
        return {
            "mode": self.coordinator.data.get("grid_boost_mode", 20),
            "calculated": self.coordinator.data.get("grid_boost_calculated", 20),
            "manual": self.coordinator.data.get("grid_boost_manual", 20),
            "actual": self.coordinator.data.get("grid_boost_actual", 20),
            "min_soc": self.coordinator.data.get("min_soc", 20),
            "load_days": self.coordinator.data.get("load_days", 3),
            "update_hour": self.coordinator.data.get("update_hour", 23),
        }

    @property
    def name(self) -> str | None:
        """Return the name of the sensor."""
        return self._attr_name

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._attr_unique_id

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        return self.coordinator.data.get("grid_boost_actual", 30)


class ApexChartEntity(CoordinatorEntity):
    """Class for Grid Boost Apex Chart entity."""

    def __init__(
        self,
        entry_id: str,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        # parent: str,
    ) -> None:
        """Initialize the sensor."""

        super().__init__(coordinator)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_apex_chart"
        self._attr_icon = "mdi:chart-line"
        self._attr_name = "Forecast Chart"
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=self._attr_name,
        )

    @property
    def name(self) -> str | None:
        """Return the name of the sensor."""
        return (
            f"{self._coordinator.data.get('forecast_chart_day', '')} {self._attr_name}"
        )

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._attr_unique_id

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        return (
            "working"
            if self._coordinator.data.get("forecast_chart_load", {})
            else "idle"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the extra state attributes."""
        my_load: dict[datetime, int] = self._coordinator.data.get(
            "forecast_chart_load", {}
        )
        my_pv: dict[datetime, int] = self._coordinator.data.get(
            "forecast_chart_pv", {}
        )
        my_soc: dict[datetime, int] = self._coordinator.data.get(
            "forecast_chart_soc", {}
        )
        return {
            "load": my_load,
            "pv": my_pv,
            "soc": my_soc,
            "test": 100,  # Placeholder for test data
        }
