"""Coordinator for the GRIST Scheduler integration.

Defines the GristUpdateCoordinator, which manages periodic data updates for
the GRIST integration using Home Assistant's DataUpdateCoordinator pattern.

This coordinator is responsible for scheduling and executing the update method
that fetches the latest data for sensors and other entities in the integration.
All polling is performed asynchronously at the specified interval.

Classes:
    GristUpdateCoordinator: Coordinates periodic updates for GRIST sensors.

Usage:
    Instantiate GristUpdateCoordinator with a Home Assistant instance, update interval
    (in seconds), and an async update method that returns the latest data as a dict.
    The coordinator will handle scheduling and error handling for updates.

"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import Any

from .const import DEBUGGING, DOMAIN

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG if DEBUGGING else logging.INFO)


class GristUpdateCoordinator(DataUpdateCoordinator):
    """Coordinates periodic data updates for GRIST sensors.

    This coordinator schedules and executes the provided async update method at the
    specified interval, handling errors and making the latest data available to
    GRIST entities.

    Args:
        hass: The Home Assistant instance.
        update_interval: Polling interval in seconds.
        update_method: Async callable returning a dict of updated data.

    Attributes:
        update_method: The async method to call for fetching new data.

    """

    def __init__(
        self,
        hass: HomeAssistant,
        update_interval: int,
        update_method: Callable[[], Awaitable[dict[str, Any]]],
    ) -> None:
        """Initialize the GristUpdateCoordinator."""
        _LOGGER.debug(
            "Initializing GristUpdateCoordinator to update via %s every %s seconds",
            update_method,
            update_interval,
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.update_method = update_method

    async def _async_update_data(self):
        """Fetch all data for GRIST sensors.

        Returns:
            The latest data as a dictionary.

        Raises:
            UpdateFailed: If the update method raises an exception.

        """
        if self.update_method:
            try:
                return await self.update_method()
            except Exception as e:
                _LOGGER.error("Update method failed to update sensors: %s", e)
                raise UpdateFailed(f"UpdateMethod Failed to update sensors: {e}") from e
        return None

    async def async_unload_entry(self) -> None:
        """Unload the config entry and clean up the update method."""
        _LOGGER.debug("Unloading entry: %s", self.name)
        self.update_method = None
