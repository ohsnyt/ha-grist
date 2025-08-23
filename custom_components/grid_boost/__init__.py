"""Integration for Time of Use Scheduler."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

# from homeassistant.helpers.typing import ConfigType
from .const import (
    DEFAULT_BATTERY_MIN_SOC,
    DEFAULT_GRID_BOOST_MODE,
    DEFAULT_GRID_BOOST_START,
    DEFAULT_GRID_BOOST_STARTING_SOC,
    DEFAULT_LOAD_AVERAGE_DAYS,
    DEFAULT_UPDATE_HOUR,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import GridBoostUpdateCoordinator
from .grid_boost import GridBoostScheduler

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Grid Boost from a config entry."""
    try:
        # Initialize the Grid Boost
        grid_boost = GridBoostScheduler(
            hass=hass,
            config_entry=entry,
            coordinator=None,  # Temporarily set to None
            boost_mode=entry.options.get(
                "boost_mode", entry.data.get("boost_mode", DEFAULT_GRID_BOOST_MODE)
            ),
            grid_boost_manual=entry.options.get(
                "grid_boost_manual", DEFAULT_GRID_BOOST_STARTING_SOC
            ),
            grid_boost_start=entry.options.get(
                "grid_boost_start", DEFAULT_GRID_BOOST_START
            ),
            update_hour=entry.options.get("update_hour", DEFAULT_UPDATE_HOUR),
            minimum_soc=entry.options.get("minimum_soc", DEFAULT_BATTERY_MIN_SOC),
            history_days=entry.options.get("history_days", DEFAULT_LOAD_AVERAGE_DAYS),
        )
        _LOGGER.debug("Grid Boost options at startup:\nBoost: %s,\nManual: %s%%,\nStart: %s,\nUpdate Hour: %s,\nMinimum SoC: %s%%,\nHistory Days: %s",
                     grid_boost.boost_mode.capitalize(),
                     grid_boost.grid_boost_manual,
                     grid_boost.grid_boost_start,
                     grid_boost.update_hour,
                     grid_boost.minimum_soc,
                     grid_boost.days_of_load_history)

        # Create the UpdateCoordinator
        coordinator = GridBoostUpdateCoordinator(
            hass=hass,
            update_method=grid_boost.to_dict,
        )
        await coordinator.async_config_entry_first_refresh()

        # Assign the coordinator to the GridBoostScheduler instance
        grid_boost.coordinator = coordinator

        # Store the Grid Boost instance in hass.data[DOMAIN]
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "coordinator": coordinator,
            "grid_boost": grid_boost,
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
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


