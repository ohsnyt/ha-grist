"""Mock config entry for testing."""

from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant


class MockConfigEntry(ConfigEntry):
    """A minimal mock config entry for testing."""

    EMPTY_DICT: MappingProxyType[str, tuple] = MappingProxyType({})

    def __init__(
        self,
        *,
        domain: str,
        data: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        entry_id: str | None = None,
        version: int = 1,
        title: str = "Test Entry",
        state: ConfigEntryState = ConfigEntryState.NOT_LOADED,
    ) -> None:
        """Initialize the mock config entry."""
        super().__init__(
            version=version,
            minor_version=0,
            domain=domain,
            title=title,
            data=data or {},
            options=options or {},
            source="test",
            discovery_keys=type(self).EMPTY_DICT,
            entry_id=entry_id or "mock_entry_id",
            unique_id=None,
            subentries_data=None,
        )
        self.state = state

    def add_to_hass(self, hass: HomeAssistant) -> None:
        """Add this entry to hass."""
        hass.config_entries._entries[self.entry_id] = self
