"""Battery statistics for GRIST Scheduler.

Provides the Battery class for interfacing with Home Assistant sensors to supply
battery statistics such as capacity, voltage, and state of charge (SoC) for the
GRIST Scheduler integration.

All I/O is async and compatible with Home Assistant's async patterns.

Classes:
    Battery: Interfaces with Home Assistant sensors to provide battery statistics.

Constants:
    DEFAULT_BATTERY_CAPACITY_AH (int): Default battery capacity in ampere-hours (Ah).
    DEFAULT_BATTERY_FLOAT_VOLTAGE (float): Default full charge voltage for the battery.
    DEFAULT_BATTERY_MIN_SOC (int): Default minimum state of charge (SOC) percentage.

Dependencies:
    - homeassistant.core.HomeAssistant: Home Assistant core instance.
    - .const.Status: Enum for battery status.
    - .hass_utilities.mqtt_get_number: Utility to fetch a number entity from Home Assistant.
    - .hass_utilities.mqtt_get_state_as_float: Utility to fetch a sensor state as float.
    - .hass_utilities.mqtt_sum_states_starting_with: Utility to sum sensor states with a given prefix.

Usage:
    Instantiate the Battery class with a Home Assistant instance to access battery
    statistics and update them asynchronously from Home Assistant sensors.

"""

import logging

from homeassistant.core import HomeAssistant, State

from .const import (
    DEBUGGING,
    DEFAULT_BATTERY_CAPACITY_AH,
    DEFAULT_BATTERY_FLOAT_VOLTAGE,
    DEFAULT_BATTERY_MIN_SOC,
    SENSOR_BATTERY_CAPACITY,
    SENSOR_BATTERY_FLOAT_VOLTAGE,
    SENSOR_BATTERY_SOC,
    Status,
)

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUGGING else logging.INFO)


class Battery:
    """Interface between the GRIST Scheduler and battery statistics."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize battery statistics."""
        self.hass = hass
        self._capacity_ah: int = DEFAULT_BATTERY_CAPACITY_AH
        self._full_voltage: float = DEFAULT_BATTERY_FLOAT_VOLTAGE
        self._battery_soc: float = DEFAULT_BATTERY_MIN_SOC
        self._status = Status.NOT_CONFIGURED
        self._unsub_update = None

    async def async_initialize(self) -> None:
        """Load battery data from Home Assistant sensors."""
        await self.update_data()

    async def async_unload_entry(self) -> None:
        """Unload the battery entry and clean up listeners."""
        if self._unsub_update:
            self._unsub_update()
            self._unsub_update = None
        logger.debug("Unloaded battery entry")

    async def update_data(self) -> None:
        """Fetch and process data from Home Assistant sensors.

        Updates battery capacity, voltage, and SoC from Home Assistant sensor states.
        """
        if "mqtt" not in self.hass.config.components:
            logger.error("MQTT system is not running")
            self._status = Status.MQTT_OFF
            return

        battery_capacity_sensors = [
            state.entity_id
            for state in self.hass.states.async_all("sensor")
            if state.entity_id.startswith(SENSOR_BATTERY_CAPACITY)
        ]
        if not battery_capacity_sensors:
            logger.warning("No battery capacity sensors found.")
            self._status = Status.NOT_CONFIGURED
            return

        temp_cap = 0.0
        for entity in battery_capacity_sensors:
            state: State | None = self.hass.states.get(entity)
            if not state:
                logger.error("MQTT entity %s could not be accessed", entity)
                self._status = Status.FAULT
                return
            try:
                temp_cap += float(state.state)
            except (ValueError, TypeError):
                logger.warning("Invalid state for entity %s: %s", entity, state.state)
                self._status = Status.FAULT
                return
        self._capacity_ah = int(temp_cap)

        state = self.hass.states.get(SENSOR_BATTERY_FLOAT_VOLTAGE)
        if not state:
            logger.error("MQTT entity %s could not be accessed", SENSOR_BATTERY_FLOAT_VOLTAGE)
            self._status = Status.FAULT
            return
        try:
            self._full_voltage = float(state.state)
        except (ValueError, TypeError):
            logger.warning("Invalid state for entity %s: %s", SENSOR_BATTERY_FLOAT_VOLTAGE, state.state)
            self._status = Status.FAULT
            return

        state = self.hass.states.get(SENSOR_BATTERY_SOC)
        if not state:
            logger.error("MQTT entity %s could not be accessed", SENSOR_BATTERY_SOC)
            self._status = Status.FAULT
            return
        try:
            self._battery_soc = float(state.state) / 100
        except (ValueError, TypeError):
            logger.warning("Invalid state for entity %s: %s", SENSOR_BATTERY_SOC, state.state)
            self._status = Status.FAULT
            return

        self._status = Status.NORMAL

    @property
    def capacity_ah(self) -> int:
        """Return the battery capacity in ampere-hours (Ah)."""
        return self._capacity_ah

    @property
    def capacity_wh(self) -> int:
        """Return the battery capacity in watt-hours (Wh)."""
        return int(self._capacity_ah * self._full_voltage)

    @property
    def current_wh(self) -> float:
        """Return the current battery capacity in watt-hours (Wh)."""
        return self._battery_soc * self.capacity_wh

    @property
    def state_of_charge(self) -> float:
        """Return the battery state of charge as a fraction (0.0–1.0)."""
        return self._battery_soc

    @property
    def status(self) -> Status:
        """Return the current status of the battery."""
        return self._status
