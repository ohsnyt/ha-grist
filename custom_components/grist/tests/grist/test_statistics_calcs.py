"""Tests for GRIST statistics calculations."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from custom_components.grist.const import HRS_PER_DAY, Status
from custom_components.grist.statistics_calcs import (
    DailyStats,
    performance_ratios,
    start_and_end_utc,
)
import pytest

from homeassistant.core import HomeAssistant


@pytest.fixture
def hass() -> MagicMock:
    """Return a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.config = MagicMock()
    return hass


def test_start_and_end_utc_returns_correct_range() -> None:
    """Test that start_and_end_utc returns correct UTC datetimes."""
    start, end = start_and_end_utc(3)
    assert isinstance(start, datetime)
    assert isinstance(end, datetime)
    assert (end + timedelta(seconds=1) - start).days == 3


def test_performance_ratios_defaults_to_1() -> None:
    """Test that performance_ratios returns 1.0 for missing data."""
    ratios = performance_ratios({}, {}, {})
    assert isinstance(ratios, dict)
    assert all(ratio == 1.0 for ratio in ratios.values())


def test_performance_ratios_computes_ratios() -> None:
    """Test that performance_ratios computes correct ratios. SoC must be above 98%."""
    day = (datetime.now() + timedelta(days=-2)).strftime("%Y-%m-%d")
    day2 = (datetime.now() + timedelta(days=-3)).strftime("%Y-%m-%d")
    # Note: The forecasted PV assumes the first day's data (day 0) is for tomorrow, so should not be used.
    forecasted_pv = {
        day: dict.fromkeys(range(24), 0),
        day2: dict.fromkeys(range(24), 0),
    }
    forecasted_pv[day][8] = 100
    forecasted_pv[day][9] = 100
    forecasted_pv[day][10] = 50
    forecasted_pv[day2][8] = 100
    forecasted_pv[day2][9] = 100
    forecasted_pv[day2][10] = 50
    soc = {day: dict.fromkeys(range(24), 99), day2: dict.fromkeys(range(24), 99)}
    actual_pv = {day: dict.fromkeys(range(24), 0), day2: dict.fromkeys(range(24), 0)}
    actual_pv[day][8] = 100
    actual_pv[day][9] = 120
    actual_pv[day][10] = 25
    actual_pv[day2][8] = 100
    actual_pv[day2][9] = 120
    actual_pv[day2][10] = 25
    ratios = performance_ratios(forecasted_pv, soc, actual_pv)
    assert ratios[8] == 1.0
    assert ratios[9] == 1.2
    assert ratios[10] == 0.5


@pytest.mark.asyncio
async def test_daily_stats_initialization(hass: HomeAssistant) -> None:
    """Test DailyStats initialization and default values."""
    stats = DailyStats(hass)
    assert stats.status == Status.NOT_CONFIGURED
    assert isinstance(stats.average_hourly_load, dict)
    assert isinstance(stats.pv_performance_ratios, dict)
    assert isinstance(stats.forecast_today_adjusted, dict)
    assert isinstance(stats.forecast_tomorrow_adjusted, dict)
    assert isinstance(stats.forecast_yesterday_adjusted, dict)


@pytest.mark.asyncio
async def test_daily_stats_update_data_no_forecaster(hass: HomeAssistant) -> None:
    """Test update_data sets status to FAULT if no forecaster."""
    stats = DailyStats(hass)
    await stats.update_data(None)
    assert stats.status == Status.FAULT


def test_daily_stats_totals() -> None:
    """Test forecast total properties."""
    stats = DailyStats(MagicMock())
    stats._forecast_yesterday_adjusted = dict.fromkeys(range(HRS_PER_DAY), 10)
    stats._forecast_today_adjusted = dict.fromkeys(range(HRS_PER_DAY), 20)
    stats._forecast_tomorrow_adjusted = dict.fromkeys(range(HRS_PER_DAY), 30)
    assert stats.forecast_yesterday_adjusted_total == 10 * HRS_PER_DAY
    assert stats.forecast_today_adjusted_total == 20 * HRS_PER_DAY
    assert stats.forecast_tomorrow_adjusted_total == 30 * HRS_PER_DAY
