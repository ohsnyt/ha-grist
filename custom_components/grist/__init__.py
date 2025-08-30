"""Integration for Time of Use Scheduler.

This module sets up the GRIST integration for Home Assistant, handling the
lifecycle of config entries, including setup, update, and unload. The integration
uses an update coordinator pattern and supports dynamic option updates via the
config flow. User-facing strings and form schemas are defined in translations/en.json.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS, UPDATE_INTERVAL
from .coordinator import GristUpdateCoordinator
from .grist import GristScheduler

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GRIST from a config entry.

    Initializes the GristScheduler and DataUpdateCoordinator, stores them in hass.data,
    and forwards setup to the sensor platform. Registers an update listener to reload
    the entry when options are changed via the config flow.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry for this integration.

    Returns:
        True if setup was successful, False otherwise.

    """
    _LOGGER.debug("Starting GRIST Scheduler")

    # Initialize GRIST Scheduler
    grist = GristScheduler(
        hass=hass,
        options=dict(entry.options),
    )
    await grist.async_setup()

    # Initialize Coordinator
    coordinator = GristUpdateCoordinator(
        hass=hass,
        update_interval=UPDATE_INTERVAL,
        update_method=grist.to_dict,
    )

    # Get first data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator and grist in hass.data for platform access
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "grist": grist,
    }

    # Forward the setup to the sensor platform(s)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_entry_update(
        hass: HomeAssistant, updated_entry: ConfigEntry
    ) -> None:
        """Handle updates to the config entry options.

        Reloads the config entry to apply updated options and avoid duplicate setups.

        Args:
            hass: The Home Assistant instance.
            updated_entry: The updated config entry.

        """
        await hass.config_entries.async_reload(updated_entry.entry_id)

    # Register the update listener for config entry option changes
    entry.async_on_unload(entry.add_update_listener(handle_entry_update))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Asynchronously unload a config entry for the Grist integration.

    Unloads all platforms, cleans up coordinator and scheduler objects, and
    removes the entry from hass.data.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to unload.

    Returns:
        True if unload was successful, False otherwise.

    """
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
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
    except Exception as e:
        _LOGGER.error("Error unloading entry %s: %s", entry.entry_id, e)
        return False
    else:
        return unload_ok
