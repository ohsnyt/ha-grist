"""Tests for the GRIST Scheduler."""

from unittest.mock import MagicMock

from custom_components.grist.const import Status
from custom_components.grist.grist import GristScheduler
import pytest

from homeassistant.core import HomeAssistant


@pytest.fixture
def hass() -> HomeAssistant:
    """Return a mock HomeAssistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    # Explicitly mock hass.config and hass.config.components as a set
    hass.config = MagicMock()
    hass.config.components = {"mqtt"}
    hass.states = MagicMock()
    hass.states.async_all.return_value = []
    return hass


def test_grist_scheduler_initialization(hass: HomeAssistant) -> None:
    """Test initialization of GristScheduler."""
    scheduler = GristScheduler(hass, {})
    assert scheduler.status == Status.STARTING


@pytest.mark.asyncio
async def test_grist_scheduler_async_setup(hass: HomeAssistant) -> None:
    """Test async setup of GristScheduler."""
    scheduler = GristScheduler(hass, {})
    await scheduler.async_setup()
    assert scheduler.status == Status.NOT_CONFIGURED
