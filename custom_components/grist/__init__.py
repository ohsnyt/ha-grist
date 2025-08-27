"""Integration for Time of Use Scheduler."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

# from homeassistant.helpers.typing import ConfigType
from .const import (
    DEFAULT_BATTERY_MIN_SOC,
    DEFAULT_GRIST_END,
    DEFAULT_GRIST_MODE,
    DEFAULT_GRIST_START,
    DEFAULT_GRIST_STARTING_SOC,
    DEFAULT_LOAD_AVERAGE_DAYS,
    DEFAULT_UPDATE_HOUR,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import GridBoostUpdateCoordinator
from .grist import GridBoostScheduler

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Grid Boost from a config entry."""
    try:
        # Initialize the Grid Boost
        grist = GridBoostScheduler(
            hass=hass,
            config_entry=entry,
            coordinator=None,  # Temporarily set to None
            boost_mode=entry.options.get("boost_mode", DEFAULT_GRIST_MODE),
            grist_manual=entry.options.get("grist_manual", DEFAULT_GRIST_STARTING_SOC),
            grist_start=entry.options.get("grist_start", DEFAULT_GRIST_START),
            grist_end=entry.options.get("grist_end", DEFAULT_GRIST_END),
            update_hour=entry.options.get("update_hour", DEFAULT_UPDATE_HOUR),
            minimum_soc=entry.options.get("minimum_soc", DEFAULT_BATTERY_MIN_SOC),
            history_days=entry.options.get("history_days", DEFAULT_LOAD_AVERAGE_DAYS),
        )
        _LOGGER.debug(
            "\nGrid Boost options at startup:\nBoost: %s, with %s load history days\nStart - End: %s - %s,\nUpdate Hour: %s,\nMinimum SoC: %s%%, Manual SoC: %s%%",
            grist.boost_mode.capitalize(),
            grist.days_of_load_history,
            grist.grist_start,
            grist.grist_end,
            grist.update_hour,
            grist.minimum_soc,
            grist.grist_manual,
        )

        # Create the UpdateCoordinator
        coordinator = GridBoostUpdateCoordinator(
            hass=hass,
            update_method=grist.to_dict,
        )
        await coordinator.async_config_entry_first_refresh()

        # Assign the coordinator to the GridBoostScheduler instance
        grist.coordinator = coordinator

        # Store the Grid Boost instance in hass.data[DOMAIN]
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "coordinator": coordinator,
            "grist": grist,
        }

        # Forward the setup to the sensor platform
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    except Exception as e:  # noqa: BLE001
        _LOGGER.error("Error setting up Grid Boost entry: %s", e)
        return False

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    _LOGGER.debug("Unloading Grid Boost entry: %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok
