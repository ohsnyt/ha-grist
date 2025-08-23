"""Config flow for Grid Boost integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    BOOST_MODE_OPTIONS,
    DEFAULT_BATTERY_MIN_SOC,
    DEFAULT_GRID_BOOST_MODE,
    DEFAULT_GRID_BOOST_START,
    DEFAULT_LOAD_AVERAGE_DAYS,
    DEFAULT_MANUAL_GRID_BOOST,
    DEFAULT_UPDATE_HOUR,
    DOMAIN,
    DOMAIN_STR,
    GRID_BOOST_MAX_SOC,
    GRID_BOOST_MIN_SOC,
    HISTORY_MAX,
    HISTORY_MIN,
    HOUR_MAX,
    HOUR_MIN,
)

_LOGGER = logging.getLogger(__name__)


def get_options_schema(options: dict[str, Any]) -> vol.Schema:
    """Return the options schema for Grid Boost."""
    return vol.Schema(
        {
            vol.Required(
                "boost_mode", default=options.get("boost_mode", DEFAULT_GRID_BOOST_MODE)
            ): vol.In(BOOST_MODE_OPTIONS),
            vol.Required(
                "grid_boost_manual",
                default=options.get("grid_boost_manual", DEFAULT_MANUAL_GRID_BOOST),
            ): vol.All(vol.Coerce(int), vol.Range(min=GRID_BOOST_MIN_SOC, max=GRID_BOOST_MAX_SOC)),
            vol.Required(
                "grid_boost_start",
                default=options.get("grid_boost_start", DEFAULT_GRID_BOOST_START),
            ): str,
            vol.Required(
                "update_hour",
                default=options.get("update_hour", DEFAULT_UPDATE_HOUR),
            ): vol.All(vol.Coerce(int), vol.Range(min=HOUR_MIN, max=HOUR_MAX)),
            vol.Required(
                "history_days",
                default=options.get("history_days", DEFAULT_LOAD_AVERAGE_DAYS),
            ): vol.All(vol.Coerce(int), vol.Range(min=HISTORY_MIN, max=HISTORY_MAX)),
            vol.Required(
                "minimum_soc",
                default=options.get("minimum_soc", DEFAULT_BATTERY_MIN_SOC),
            ): vol.All(vol.Coerce(int), vol.Range(min=GRID_BOOST_MIN_SOC, max=GRID_BOOST_MAX_SOC)),
        }
    )


class GridBoostConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Grid Boost."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step of the config flow."""
        if user_input is not None:
            # Create the config entry with the user input
            return self.async_create_entry(title=DOMAIN_STR, data=user_input)

        # Show the form for the user to input configuration
        return self.async_show_form(
            step_id="user",
            data_schema=get_options_schema({}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return GridBoostOptionsFlow()


class GridBoostOptionsFlow(config_entries.OptionsFlow):
    """Handle the options flow for Grid Boost."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the options flow."""
        if user_input is not None:
            # Merge user input with existing options and defaults
            options = dict(self.config_entry.options)
            options.update(user_input)
            # Update the config entry with new options
            worked =  self.hass.config_entries.async_update_entry(
                self.config_entry, options=options
            )
            _LOGGER.debug(
                "Updated Grid Boost options: %s, saved: %s", options, worked
            )
            # Schedule a reload of the config entry to apply the changes
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
            _LOGGER.info(
                "Scheduled reload for Grid Boost. Now going to do async_abort"
            )
            # Return without creating a new entry, as options are already updated
            return self.async_abort(reason="configuration_updated")

        return self.async_show_form(
            step_id="init",
            data_schema=get_options_schema(dict(self.config_entry.options)),
        )