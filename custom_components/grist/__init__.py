"""Integration for Time of Use Scheduler."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS, UPDATE_INTERVAL
from .coordinator import GristUpdateCoordinator
from .grist import GristScheduler

PURPLE = "\033[0;35m"
RESET = "\033[0m"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GRIST from a config entry."""
    _LOGGER.info("%sStarting GRIST Scheduler%s", PURPLE, RESET)

    # Initialize GRIST Scheduler
    grist = GristScheduler(
        hass=hass,
        options=dict(entry.options),
    )
    await grist.async_setup()

    # Initialize Coordinator
    _LOGGER.debug("Setting up coordinator for entry: %s", entry.entry_id)
    coordinator = GristUpdateCoordinator(
        hass=hass,
        update_interval=UPDATE_INTERVAL,
        update_method=grist.to_dict,
    )

    # Get first data
    _LOGGER.debug("Performing first refresh for entry: %s", entry.entry_id)
    await coordinator.async_config_entry_first_refresh()
    # Store coordinator in hass.data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "grist": grist,
    }

    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Registering update listener for entry: %s", entry.entry_id)

    async def handle_entry_update(
        hass: HomeAssistant, updated_entry: ConfigEntry
    ) -> None:
        _LOGGER.debug(
            "Config entry %s updated with options: %s",
            updated_entry.entry_id,
            updated_entry.options,
        )

        # Reload the config entry to apply updated options and avoid duplicate setups
        await hass.config_entries.async_reload(updated_entry.entry_id)
        _LOGGER.debug("Reloaded entry: %s after update", updated_entry.entry_id)

    # Register the update listener
    entry.async_on_unload(entry.add_update_listener(handle_entry_update))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    _LOGGER.debug("Unloading entry: %s, state: %s", entry.entry_id, entry.state)
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        _LOGGER.debug(
            "Platform unload result for entry %s: %s", entry.entry_id, unload_ok
        )
        if unload_ok:
            entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
            coordinator = entry_data.get("coordinator")
            if coordinator and hasattr(coordinator, "async_unload_entry"):
                await coordinator.async_unload_entry()
            grist = entry_data.get("grist")
            if grist and hasattr(grist, "async_unload_entry"):
                await grist.async_unload_entry()
            if not hass.data[DOMAIN]:
                hass.data.pop(DOMAIN)
            _LOGGER.debug("Unloaded entry: %s", entry.entry_id)
        else:
            _LOGGER.error(
                "Failed to unload %s for entry: %s", PLATFORMS, entry.entry_id
            )
    except Exception as e:
        _LOGGER.error("Error unloading entry %s: %s", entry.entry_id, e)
        return False
    else:
        return unload_ok
