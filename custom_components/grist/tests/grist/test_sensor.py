"""Tests for GRIST sensor entities."""

from custom_components.grist.sensor import GRID_BOOST_SENSOR_ENTITIES


def test_grid_boost_sensor_entities_keys() -> None:
    """Test that all sensor entity descriptions have required keys and types."""
    for key, desc in GRID_BOOST_SENSOR_ENTITIES.items():
        assert hasattr(desc, "key")
        assert desc.key == key
        assert hasattr(desc, "name")
        assert desc.name is not None
        assert hasattr(desc, "device_class")
        assert desc.device_class is not None
