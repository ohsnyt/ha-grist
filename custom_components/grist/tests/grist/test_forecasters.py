"""Tests for GRIST ForecastSolar forecaster."""

from unittest.mock import MagicMock

from custom_components.grist.const import Status
from custom_components.grist.forecasters.forecast_solar import ForecastSolar
from custom_components.grist.forecasters.meteo import Meteo
from custom_components.grist.forecasters.solcast import Solcast
import pytest

from homeassistant.core import HomeAssistant


@pytest.fixture
def hass() -> MagicMock:
    """Return a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.config = MagicMock()
    return hass


def test_forecast_solar_initialization(hass: HomeAssistant) -> None:
    """Test initialization of ForecastSolar."""
    forecast = ForecastSolar(hass)
    assert forecast.status == Status.NOT_CONFIGURED


def test_meteo_initialization(hass: HomeAssistant) -> None:
    """Test initialization of Meteo."""
    forecaster = Meteo(hass)
    assert forecaster.status == Status.NOT_CONFIGURED


def test_solcast_initialization(hass: HomeAssistant) -> None:
    """Test initialization of Solcast."""
    forecaster = Solcast(hass)
    assert forecaster.status == Status.NOT_CONFIGURED
