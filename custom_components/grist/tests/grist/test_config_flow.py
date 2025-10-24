"""Tests for the GRIST config flow."""

from custom_components.grist.config_flow import (
    BoostMode,
    GristConfigFlow,
    GristOptionsFlow,
)
from custom_components.grist.const import DOMAIN
import pytest

from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry


@pytest.fixture
def config_flow() -> GristConfigFlow:
    """Return a new instance of the GRIST config flow."""
    return GristConfigFlow()


@pytest.fixture
def options_flow() -> GristOptionsFlow:
    """Return a new instance of the GRIST options flow."""
    return GristOptionsFlow()


async def test_user_step_creates_entry(hass: HomeAssistant) -> None:
    """Test that the user step creates a config entry."""
    flow = GristConfigFlow()
    user_input = {"boost_mode": BoostMode.AUTOMATIC}
    result = await flow.async_step_user(user_input)
    assert result.get("type") == "create_entry"
    assert result.get("title") == DOMAIN.upper()
    assert result.get("data", {}).get("boost_mode") == BoostMode.AUTOMATIC


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    """Test that the user step shows the form if no input is provided."""
    flow = GristConfigFlow()
    result = await flow.async_step_user(None)
    assert result.get("type") == "form"
    assert result.get("step_id") == flow.STEP_USER


# Removed DummyConfigEntry, use MockConfigEntry instead


async def test_options_flow_init_requires_confirmation(hass: HomeAssistant) -> None:
    """Test that disabling boost mode requires confirmation."""
    flow = GristOptionsFlow()
    flow.config_entry = MockConfigEntry(options={})
    user_input = {"boost_mode": BoostMode.OFF}
    result = await flow.async_step_init(user_input)
    flow.config_entry = MockConfigEntry(options={})
    user_input = {"boost_mode": BoostMode.OFF}
    result = await flow.async_step_init(user_input)
    assert result.get("type") == "form"
    assert result.get("step_id") == "confirm"

    flow.config_entry = MockConfigEntry(options={})
    flow._pending_user_options = {"boost_mode": BoostMode.OFF}
    user_input = {"confirm": True}
    result = await flow.async_step_confirm(user_input)
    assert result.get("type") in ("form", "create_entry")
    user_input = {"confirm": True}
    result = await flow.async_step_confirm(user_input)
    assert result.get("type") in ("form", "create_entry")
    flow = GristOptionsFlow()
    flow.config_entry = MockConfigEntry(options={})
    flow._pending_user_options = {}
    user_input = {
        "grist_start": 6,
        "grist_end": 18,
        "update_hour": 3,
        "history_days": 3,
        "minimum_soc": 20,
        "grist_manual": 50,
    }
    result = await flow.async_step_details(user_input)
    assert result.get("type") == "create_entry"
    assert result.get("data", {}).get("grist_start") == 6
    assert result.get("data", {}).get("grist_end") == 18


async def test_options_flow_details_step_invalid(hass: HomeAssistant) -> None:
    """Test that details step returns error if start >= end."""
    flow = GristOptionsFlow()
    flow.config_entry = MockConfigEntry(options={})
    flow._pending_user_options = {}
    user_input = {
        "grist_start": 18,
        "grist_end": 6,
        "update_hour": 3,
        "history_days": 3,
        "minimum_soc": 20,
        "grist_manual": 50,
    }
    result = await flow.async_step_details(user_input)
    assert result.get("type") == "form"
    errors = result.get("errors")
    assert isinstance(errors, dict) and "grist_start" in errors
