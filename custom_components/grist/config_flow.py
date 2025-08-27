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
    DEFAULT_GRIST_END,
    DEFAULT_GRIST_MODE,
    DEFAULT_GRIST_START,
    DEFAULT_LOAD_AVERAGE_DAYS,
    DEFAULT_MANUAL_GRIST,
    DEFAULT_UPDATE_HOUR,
    DOMAIN,
    DOMAIN_STR,
    GRIST_MAX_SOC,
    GRIST_MIN_SOC,
    HISTORY_MAX,
    HISTORY_MIN,
    HOUR_MAX,
    HOUR_MIN,
    BoostMode,
)

_LOGGER = logging.getLogger(__name__)

def boost_schema(options: dict[str, Any]) -> vol.Schema:
    """Return the options schema for Grist."""
    return vol.Schema({
        vol.Required(
            "boost_mode", default=str(options.get("boost_mode", DEFAULT_GRIST_MODE))
        ): vol.In(BOOST_MODE_OPTIONS),
    })

def confirm_schema(options: dict[str, Any]) -> vol.Schema:
    """Return a schema requiring explicit user confirmation to disable boost mode.

    The 'confirm' field is a safety confirmation for disabling boost mode, with a default of False.
    """
    return vol.Schema({
        vol.Required("confirm", default=False): bool
    })

def details_schema(options: dict[str, Any]) -> vol.Schema:
    """Return the options schema for Grist."""
    return vol.Schema({
        vol.Required("grist_start", default=DEFAULT_GRIST_START): vol.All(
            vol.Coerce(int), vol.Range(min=HOUR_MIN, max=HOUR_MAX)
        ),
        vol.Required("grist_end", default=DEFAULT_GRIST_END): vol.All(
            vol.Coerce(int), vol.Range(min=HOUR_MIN, max=HOUR_MAX)
        ),
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
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=GRIST_MIN_SOC, max=GRIST_MAX_SOC),
        ),
        vol.Required(
            "grist_manual",
            default=options.get("grist_manual", DEFAULT_MANUAL_GRIST),
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=GRIST_MIN_SOC, max=GRIST_MAX_SOC),
        ),
})


class GristConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Grist."""

    VERSION = 1
    STEP_USER = "user"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step of the config flow."""
        if user_input is not None:
            return self.async_create_entry(title=DOMAIN_STR, data=user_input)
        return self.async_show_form(
            step_id=self.STEP_USER,
            data_schema=boost_schema({}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return GristOptionsFlow()

class GristOptionsFlow(config_entries.OptionsFlow):
    """Handle the options flow for Grid Boost."""

    def __init__(self) -> None:
        """Initialize temporary user input during optional confirmation process."""
        self._pending_user_mode = {}

    @property
    def options(self) -> dict[str, Any]:
        """Return the current options from the config entry."""
        if hasattr(self, "config_entry") and self.config_entry is not None:
            return dict(self.config_entry.options)
        return {}


    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Start the options flow by asking for the boost mode."""
        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=boost_schema(dict(self.options))
            )

        self._pending_user_mode = user_input
        if user_input.get("boost_mode") == BoostMode.OFF and not user_input.get("confirm"):
            return await self.async_step_confirm(None)
        return await self.async_step_details()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Handle the confirmation of turning off the boost mode."""
        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                data_schema=confirm_schema(dict(self._pending_user_mode)),
            )
        # If the user confirms, go to the next step. If not, restart the process. (This is recursive, but is
        #   very unlikely to go deep.)
        if user_input.get("confirm"):
            return await self.async_step_details(None)
        return await self.async_step_init(None)

    async def async_step_details(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Handle the details step."""
        if user_input is None:
            return self.async_show_form(
                step_id="details",
                data_schema=details_schema(dict(self.options)),
            )
        options = dict(self.options)
        if self._pending_user_mode:
            options.update(self._pending_user_mode)
        options.update(user_input)
        return self.async_create_entry(title=DOMAIN, data=options)
