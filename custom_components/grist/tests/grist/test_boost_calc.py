"""Tests for GRIST boost calculation."""

from custom_components.grist.boost_calc import calculate_required_boost


def test_calculate_required_boost_basic() -> None:
    """Test basic boost calculation."""
    result = calculate_required_boost(
        battery_max_wh=10000,
        efficiency=0.95,
        minimum_soc=20,
        adjusted_pv={8: 500, 9: 600, 10: 700},
        average_hourly_load=dict.fromkeys(range(24), 400),
    )
    assert isinstance(result, int)
    assert result > 0


def test_calculate_required_boost_zero_pv() -> None:
    """Test boost calculation with zero PV forecast. Should return None."""
    result = calculate_required_boost(
        battery_max_wh=10000,
        efficiency=0.95,
        minimum_soc=20,
        adjusted_pv={},
        average_hourly_load=dict.fromkeys(range(24), 400),
    )
    assert result is None
