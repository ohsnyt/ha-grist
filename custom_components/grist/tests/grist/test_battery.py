"""Tests for the GRIST Battery class."""

from unittest.mock import MagicMock

from custom_components.grist.battery import Battery
from custom_components.grist.const import (
    SENSOR_BATTERY_CAPACITY,
    SENSOR_BATTERY_FLOAT_VOLTAGE,
    SENSOR_BATTERY_SOC,
    Status,
)
import pytest

from homeassistant.core import HomeAssistant, State


@pytest.fixture
def hass() -> HomeAssistant:
    """Return a mock HomeAssistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    # Mock hass.config and hass.config.components as a set
    hass.config = MagicMock()
    hass.config.components = {"mqtt"}
    # Mock hass.states as a MagicMock
    hass.states = MagicMock()
    hass.states.async_all.return_value = [
        State(f"{SENSOR_BATTERY_CAPACITY}_1", "100"),
        State(f"{SENSOR_BATTERY_CAPACITY}_2", "150"),
    ]
    hass.states.get.side_effect = lambda eid: (
        State(SENSOR_BATTERY_FLOAT_VOLTAGE, "54.0")
        if eid == SENSOR_BATTERY_FLOAT_VOLTAGE
        else State(SENSOR_BATTERY_SOC, "80")
        if eid == SENSOR_BATTERY_SOC
        else State(f"{SENSOR_BATTERY_CAPACITY}_1", "100")
        if eid == f"{SENSOR_BATTERY_CAPACITY}_1"
        else State(f"{SENSOR_BATTERY_CAPACITY}_2", "150")
        if eid == f"{SENSOR_BATTERY_CAPACITY}_2"
        else None
    )
    return hass


@pytest.mark.asyncio
async def test_battery_update_data_success(hass: HomeAssistant) -> None:
    """Test successful battery data update."""
    battery = Battery(hass)
    await battery.update_data()
    assert battery.capacity_ah == 250
    assert battery.capacity_wh == 13500
    assert battery.state_of_charge == 0.8
    assert battery.current_wh == pytest.approx(10800)
    assert battery.status == Status.NORMAL


@pytest.mark.asyncio
async def test_battery_update_data_no_mqtt(hass: HomeAssistant) -> None:
    """Test update_data when MQTT is not running."""
    hass.config.components.clear()
    battery = Battery(hass)
    await battery.update_data()
    assert battery.status == Status.MQTT_OFF


@pytest.mark.asyncio
async def test_battery_update_data_faulty_sensor(hass: HomeAssistant) -> None:
    """Test update_data with faulty sensor value."""
    hass.states.get = MagicMock(
        side_effect=lambda eid: State(SENSOR_BATTERY_FLOAT_VOLTAGE, "bad")
        if eid == SENSOR_BATTERY_FLOAT_VOLTAGE
        else None
    )
    battery = Battery(hass)
    await battery.update_data()
    assert battery.status == Status.FAULT
