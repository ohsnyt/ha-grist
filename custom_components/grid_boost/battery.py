"""Class for managing battery statistics in the Grid Boost Scheduler.

This module defines the `Battery` class for managing battery statistics within the Grid Boost Scheduler integration for Home Assistant.

Classes:
    Battery: Interfaces with Home Assistant sensors to provide battery statistics such as capacity, voltage, and state of charge.

Constants:
    DEFAULT_BATTERY_CAPACITY_AH (int): Default battery capacity in ampere-hours (Ah).
    DEFAULT_BATTERY_FULL_VOLTAGE (float): Default full charge voltage for the battery.
    DEFAULT_BATTERY_MIN_SOC (int): Default minimum state of charge (SOC) percentage.

Dependencies:
    - homeassistant.core.HomeAssistant: Home Assistant core instance.
    - .const.Status: Enum for battery status.
    - .hass_utilities.get_number: Utility to fetch a number entity from Home Assistant.
    - .hass_utilities.get_state_as_float: Utility to fetch a sensor state as float.
    - .hass_utilities.sum_states_starting_with: Utility to sum sensor states with a given prefix.

Usage:
    Instantiate the `Battery` class with a Home Assistant instance to access battery statistics and update them asynchronously from Home Assistant sensors.

"""

# from config.custom_components.hacs.utils import data
from homeassistant.core import HomeAssistant

from .const import (
    DEFAULT_BATTERY_CAPACITY_AH,
    DEFAULT_BATTERY_FLOAT_VOLTAGE,
    DEFAULT_BATTERY_MIN_SOC,
    SENSOR_BATTERY_CAPACITY,
    SENSOR_BATTERY_FLOAT_VOLTAGE,
    SENSOR_BATTERY_SOC,
    Status,
)
from .hass_utilities import get_number, get_state_as_float, sum_states_starting_with


class Battery:
    """Class to interface between the Grid Boost Scheduler and the battery statistics integration."""

    # Constructor
    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize key variables.

        Args:
            hass: The Home Assistant instance.

        """
        # General info
        self.hass = hass
        self._capacity_ah: int = DEFAULT_BATTERY_CAPACITY_AH
        self._full_voltage: float = DEFAULT_BATTERY_FLOAT_VOLTAGE
        self._battery_soc: float = DEFAULT_BATTERY_MIN_SOC
        self._status = Status.NOT_CONFIGURED
        self._unsub_update = None

    async def async_initialize(self) -> None:
        """Load battery data from Home Assistant sensors."""
        # Run update_data to fetch the latest battery data
        await self.update_data()

    async def update_data(self) -> None:
        """Fetch and process data from Home Assistant sensors."""
        # Get the battery data from the sensors
        self._capacity_ah = int(
            await sum_states_starting_with(
                self.hass,
                [SENSOR_BATTERY_CAPACITY],
                default=DEFAULT_BATTERY_CAPACITY_AH,
            )
        )

        self._full_voltage = await get_number(
            self.hass, SENSOR_BATTERY_FLOAT_VOLTAGE, DEFAULT_BATTERY_FLOAT_VOLTAGE
        )

        self._battery_soc = (
            await get_state_as_float(
                self.hass, SENSOR_BATTERY_SOC, DEFAULT_BATTERY_MIN_SOC
            )
        ) / 100

        self._status = Status.NORMAL

    @property
    def capacity_ah(self) -> int:
        """Return the battery capacity in amp hours."""
        return self._capacity_ah

    @property
    def capacity_wh(self) -> int:
        """Return the battery capacity in watt hours."""
        return int(self._capacity_ah * self._full_voltage)

    @property
    def current_wh(self) -> float:
        """Return the current battery capacity in watt hours."""
        return self._battery_soc * self.capacity_wh

    @property
    def state_of_charge(self) -> float:
        """Return the battery state of charge."""
        return self._battery_soc
