"""Sensor platform for the GRIST integration.

Defines sensor entities for the GRIST Scheduler integration in Home Assistant.
This module sets up both custom entity classes (for scheduler state, PV ratios, load, etc.)
and standard sensors (for PV forecasts, grid boost settings, and battery statistics).
All sensors use the update coordinator pattern for efficient polling and state updates.

Key Features:
- Registers custom entities for scheduler status, PV ratios, load, battery life, and chart data.
- Registers standard sensors for PV forecasts, grid boost settings, and battery time remaining.
- Ensures unique IDs for all sensors using the config entry ID.
- All sensors expose extra state attributes and device info for Home Assistant dashboards.
- Follows Home Assistant async setup and teardown patterns.

Classes:
    OhSnytSensorEntityDescription: Describes a GRIST sensor entity.
    OhSnytSensor: Standard sensor entity for GRIST Scheduler.

Functions:
    async_setup_entry: Set up all GRIST sensors for a config entry.
    async_unload_entry: Unload all GRIST sensors for a config entry.

All I/O is asynchronous and compatible with Home Assistant's async patterns.
"""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEBUGGING, DOMAIN
from .coordinator import GristUpdateCoordinator
from .entity import (
    ApexChartEntity,
    BatteryLifeEntity,
    LoadEntity,
    PVEntity_today,
    PVEntity_tomorrow,
    RatioEntity,
    SchedulerEntity,
)

logger = logging.getLogger(__name__)
if DEBUGGING:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)


class OhSnytSensorEntityDescription(SensorEntityDescription):
    """Describes a GRIST sensor entity."""


GRID_BOOST_SENSOR_ENTITIES: dict[str, OhSnytSensorEntityDescription] = {
    "pv_today_total": OhSnytSensorEntityDescription(
        key="pv_today_total",
        icon="mdi:flash",
        name="Estimated PV power for today",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    "pv_tomorrow_total": OhSnytSensorEntityDescription(
        key="pv_tomorrow_total",
        icon="mdi:flash",
        name="Estimated PV power for tomorrow",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    "calculated_boost": OhSnytSensorEntityDescription(
        key="calculated_boost",
        icon="mdi:battery",
        name="Calculated Grid Boost SoC",
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    "current_boost_setting": OhSnytSensorEntityDescription(
        key="current_boost_setting",
        icon="mdi:battery",
        name="Current inverter Grid Boost setting",
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    "manual_boost": OhSnytSensorEntityDescription(
        key="manual_boost",
        icon="mdi:battery",
        name="Manual Grid Boost SoC",
        native_unit_of_measurement="%",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    "battery_time_remaining": OhSnytSensorEntityDescription(
        key="battery_time_remaining",
        icon="mdi:timer-outline",
        name="Battery Time Remaining",
        native_unit_of_measurement="h",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GRIST sensors for a config entry.

    Registers both custom entity classes (for scheduler, PV, load, etc.)
    and standard sensors (for PV forecasts, grid boost, battery) with Home Assistant.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    if coordinator is None:
        logger.error("Coordinator is missing from hass.data")
        return

    unique_prefix = entry.entry_id

    # Add custom entity sensors from entity.py
    entity_list = [
        SchedulerEntity,
        ApexChartEntity,
        BatteryLifeEntity,
        LoadEntity,
        PVEntity_today,
        PVEntity_tomorrow,
        RatioEntity,
    ]
    entities = [
        entity(entry_id=unique_prefix, coordinator=coordinator)
        for entity in entity_list
    ]
    async_add_entities(entities)

    # Add standard sensors defined in this file
    sensors = [
        OhSnytSensor(
            entry_id=unique_prefix,
            coordinator=coordinator,
            description=entity_description,
        )
        for entity_description in GRID_BOOST_SENSOR_ENTITIES.values()
    ]
    async_add_entities(sensors)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload sensor platform for GRIST Scheduler."""
    logger.debug("Unloaded GRIST sensors for entry: %s", entry.entry_id)
    return True


class OhSnytSensor(CoordinatorEntity[GristUpdateCoordinator], SensorEntity):
    """Representation of a standard GRIST sensor."""

    def __init__(
        self,
        *,
        entry_id: str,
        coordinator: GristUpdateCoordinator,
        description: OhSnytSensorEntityDescription,
    ) -> None:
        """Initialize the sensor entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._key = description.key
        self._attr_unique_id = f"{DOMAIN}_{description.key}"
        self.entity_id = generate_entity_id(
            "sensor.{}", self._attr_unique_id, hass=coordinator.hass
        )
        icon = description.icon if isinstance(description.icon, str) else "mdi:flash"
        self._attr_icon = icon
        name = description.name if isinstance(description.name, str) else "Unknown"
        self._attr_name = name
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": self._attr_name,
        }

    @property
    def name(self) -> str | None:
        """Return the name of the sensor."""
        if self.entity_description.key == "grist_calculated":
            day = self.coordinator.data.get("grist_day")
            if day:
                return f"{self._attr_name or ''} ({day})"
        return self._attr_name

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID for the sensor."""
        return self._attr_unique_id

    @property
    def native_value(self) -> str | int | float | None:
        """Return the state of the sensor."""
        value = self.coordinator.data.get(self.entity_description.key)
        if not isinstance(value, (int, float, type(None))):
            logger.error("Invalid type for native_value: %s (%s)", value, type(value))
            return None
        return value

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device info for the sensor."""
        return self._attr_device_info

    @property
    def state(self) -> str | int | float | None:
        """Return the state of the sensor (legacy property)."""
        value = self.coordinator.data.get(self.entity_description.key)
        if not isinstance(value, (int, float, type(None))):
            logger.error("Invalid type for state: %s (%s)", value, type(value))
            return None
        return value
