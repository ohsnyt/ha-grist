"""Config flow for GRIST integration.

This module defines the configuration and options flow for the GRIST integration.
It guides the user through a multi-step setup and options process, using forms and
confirmation dialogs. User-facing strings (titles, descriptions, field names) are
defined in the translation file `translations/en.json` and referenced by Home Assistant
for localization and UI display.

Steps in the flow:
- User step: Select the boost mode (see "init" in en.json)
- Confirm step: If disabling boost mode, require explicit confirmation (see "confirm" in en.json)
- Details step: Configure advanced options (see "details" in en.json)
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import OptionsFlow
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
    PURPLE,
    RESET,
    BoostMode,
)

_LOGGER = logging.getLogger(__name__)


def boost_schema(options: dict[str, Any]) -> vol.Schema:
    """Return the schema for selecting boost mode.

    UI text is defined in translations/en.json under:
      - config.step.init.data.boost_mode
      - config.step.init.data_description.boost_mode
    """
    return vol.Schema(
        {
            vol.Required(
                "boost_mode", default=str(options.get("boost_mode", DEFAULT_GRIST_MODE))
            ): vol.In(BOOST_MODE_OPTIONS),
        }
    )


def confirm_schema(options: dict[str, Any]) -> vol.Schema:
    """Return a schema requiring explicit user confirmation to disable boost mode.

    UI text is defined in translations/en.json under:
      - config.step.confirm.title
      - config.step.confirm.description
      - config.step.confirm.data.confirm
      - config.step.confirm.data_description.confirm
    The 'confirm' field is a safety confirmation for disabling boost mode, with a default of False.
    """
    return vol.Schema({vol.Required("confirm", default=False): bool})


def details_schema(options: dict[str, Any]) -> vol.Schema:
    """Return the schema for advanced GRIST options.

    UI text is defined in translations/en.json under:
      - config.step.details.title
      - config.step.details.description
      - config.step.details.data.*
      - config.step.details.data_description.*
    """
    return vol.Schema(
        {
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
        }
    )


def to_hour(hour: int | None) -> str:
    """Convert an integer hour (0-23) to a string representation for logging/debug.

    Not used in the UI; for developer logs only.
    """
    if hour is None:
        return "oops"
    if hour == 0:
        return "midnight"
    if 1 <= hour < 12:
        return f"{hour}am"
    if hour == 12:
        return "noon"
    if 13 <= hour < 24:
        return f"{hour - 12}pm"
    raise ValueError("Invalid hour")


class GristConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for GRIST.

    The flow consists of a single step where the user selects the boost mode.
    The form fields and descriptions are defined in translations/en.json under config.step.init.
    """

    VERSION = 1
    STEP_USER = "user"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step of the config flow.

        If user_input is provided, create the entry. Otherwise, show the form.
        """
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
        """Return the options flow handler for this config entry."""
        return GristOptionsFlow()


class GristOptionsFlow(OptionsFlow):
    """Handle the options flow for GRIST.

    This flow allows the user to:
      1. Select boost mode (init step, see options.step.init in en.json)
      2. Confirm disabling boost mode (confirm step, see options.step.confirm)
      3. Set advanced options (details step, see options.step.details)
    """

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._pending_user_options: dict[str, Any] = {}

    @property
    def options(self) -> dict[str, Any]:
        """Return the current options from the config entry."""
        return dict(self.config_entry.options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Start the options flow by asking for the boost mode.

        If boost_mode is set to 'off', require confirmation before proceeding.
        """
        if user_input is None:
            return self.async_show_form(
                step_id="init", data_schema=boost_schema(self.options)
            )

        options = dict(self.options)
        options.update(user_input)
        self._pending_user_options = options
        if user_input.get("boost_mode") == BoostMode.OFF and not user_input.get(
            "confirm"
        ):
            return await self.async_step_confirm(user_input=None)
        return await self.async_step_details(user_input=None)

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the confirmation of turning off the boost mode.

        This step uses the schema and UI text from options.step.confirm in en.json.
        """
        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                data_schema=confirm_schema(self._pending_user_options),
            )
        if user_input.get("confirm"):
            return await self.async_step_details(user_input=None)
        return await self.async_step_init(None)

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the details step for advanced options.

        This step uses the schema and UI text from options.step.details in en.json.
        """
        errors = {}
        if user_input is not None:
            grist_start = user_input.get("grist_start")
            grist_end = user_input.get("grist_end")
            if (
                grist_start is not None
                and grist_end is not None
                and grist_start >= grist_end
            ):
                errors["grist_start"] = "start_must_be_before_end"
            else:
                self._pending_user_options.update(user_input)
                _LOGGER.debug(
                    "GRIST options updated with %s", self._pending_user_options
                )
                return self.async_create_entry(data=self._pending_user_options)

        return self.async_show_form(
            step_id="details",
            data_schema=details_schema(self._pending_user_options),
            errors=errors,
        )
