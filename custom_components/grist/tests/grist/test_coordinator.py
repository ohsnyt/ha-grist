"""Tests for the GRIST coordinator."""

from unittest.mock import AsyncMock

from custom_components.grist.coordinator import GristUpdateCoordinator
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed


@pytest.fixture
def mock_update_method():
    """Return a mock async update method."""
    return AsyncMock(return_value={"key": "value"})


@pytest.mark.asyncio
async def test_async_update_data_success(
    hass: HomeAssistant, mock_update_method
) -> None:
    """Test successful async update data."""
    coordinator = GristUpdateCoordinator(hass, 10, mock_update_method)
    result = await coordinator._async_update_data()
    assert result == {"key": "value"}


@pytest.mark.asyncio
async def test_async_update_data_failure(hass: HomeAssistant) -> None:
    """Test async update data raises UpdateFailed on exception."""

    async def failing_update():
        raise RuntimeError("fail")

    coordinator = GristUpdateCoordinator(hass, 10, failing_update)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_async_unload_entry(hass: HomeAssistant, mock_update_method) -> None:
    """Test async_unload_entry sets update_method to None."""
    coordinator = GristUpdateCoordinator(hass, 10, mock_update_method)
    await coordinator.async_unload_entry()
    assert coordinator.update_method is None


@pytest.mark.asyncio
async def test_coordinator_initialization(hass: HomeAssistant) -> None:
    """Test initialization of the GRIST update coordinator."""

    async def async_update_method() -> dict:
        """Return a dummy dict for testing."""
        return {}

    coordinator = GristUpdateCoordinator(
        hass=hass,
        update_method=async_update_method,
        update_interval=10,
    )
    assert coordinator.hass is hass
