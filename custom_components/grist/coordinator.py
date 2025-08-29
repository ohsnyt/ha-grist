"""For the GRIST Scheduler integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import Any

from .const import DEBUGGING, DOMAIN

_LOGGER = logging.getLogger(__name__)
if DEBUGGING:
    _LOGGER.setLevel(logging.DEBUG)
else:
    _LOGGER.setLevel(logging.INFO)


class GristUpdateCoordinator(DataUpdateCoordinator):
    """Get the current data to update the sensors."""

    def __init__(
        self,
        hass: HomeAssistant,
        update_interval: int,
        update_method: Callable[[], Awaitable[dict[str, Any]]],
    ) -> None:
        """Initialize the GristUpdateCoordinator."""
        _LOGGER.debug("Initializing GristUpdateCoordinator to update via %s every %s seconds", update_method, update_interval)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.update_method = update_method

    async def _async_update_data(self):
        """Fetch all data for your sensors here."""
        if self.update_method:
            try:
                return await self.update_method()
            except Exception as e:
                _LOGGER.error("Update method failed to update sensors: %s", e)
                raise UpdateFailed(f"UpdateMethod Failed to update sensors: {e}") from e
        return None

    async def async_unload_entry(self) -> None:
        """Unload the config entry."""
        _LOGGER.debug("Unloading entry: %s", self.name)
        self.update_method = None
