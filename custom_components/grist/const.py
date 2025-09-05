"""Constants for the GRIST integration.

Defines all constants, enums, and default values used throughout the GRIST
integration for Home Assistant. This includes configuration defaults, sensor names,
platform and domain identifiers, and enumerations for component status and boost modes.

All constants are intended to be imported and used by other modules in the integration.
"""

from enum import Enum, StrEnum

from homeassistant.loader import MQTT

FORECASTER_INTEGRATIONS = [
    "solcast_solar",
    "forecast_solar",
    "open_meteo_solar_forecast",
]

class Status(Enum):
    """Component status for the GRIST integration."""

    NOT_CONFIGURED = 0
    FAULT = 1
    NORMAL = 2
    STARTING = 3
    RATE_LIMITED = 4
    MQTT_OFF = 5

class MqttErrors(Enum):
    """MQTT errors for the GRIST integration."""

    ENTITY_NOT_FOUND = "Entity not found"
    MQTT_OFF = "MQTT is off"

    @property
    def state(self) -> str:
        """Return the string representation of the current status."""
        match self:
            case Status.NOT_CONFIGURED:
                return "Not Configured"
            case Status.FAULT:
                return "Fault"
            case Status.NORMAL:
                return "Normal"
            case Status.STARTING:
                return "Starting"
            case _:
                return "Unknown"


class BoostMode(StrEnum):
    """GRIST operating modes."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"
    OFF = "off"
    TESTING = "testing"


BOOST_MODE_OPTIONS: tuple[BoostMode, ...] = (
    BoostMode.AUTOMATIC,
    BoostMode.MANUAL,
    BoostMode.OFF,
    BoostMode.TESTING,
)

# Integration domain and platform configuration
DOMAIN = "grist"
DOMAIN_STR = "GRIST"
PLATFORMS = ["sensor"]
UPDATE_INTERVAL = 10  # Update interval in seconds

# Enable detailed debug logging for the integration
DEBUGGING = True

# Storage keys and versioning
FORECAST_KEY = "grist_forecast"
STORAGE_VERSION = 1

# Home Assistant sensor entity IDs used by the integration
SENSOR_BATTERY_CAPACITY = "sensor.deye_sunsynk_sol_ark_capacity"
SENSOR_BATTERY_SOC = "sensor.deye_sunsynk_sol_ark_battery_state_of_charge"
SENSOR_MIN_BATTERY_SOC = "sensor.deye_sunsynk_sol_ark_battery_stop_discharge_capacity"
SENSOR_LOAD_POWER = "sensor.deye_sunsynk_sol_ark_load_power"
SENSOR_PV_POWER = "sensor.deye_sunsynk_sol_ark_pv_power"
SENSOR_BATTERY_FLOAT_VOLTAGE = (
    "number.deye_sunsynk_sol_ark_battery_float_charge_voltage"
)
SENSOR_FORECAST_SOLAR_TOMORROW = "sensor.solcast_pv_forecast_forecast_tomorrow"
SENSOR_FORECAST_SOLAR_TODAY = "sensor.solcast_pv_forecast_forecast_day"
SENSOR_METEO_BASE = "sensor.energy_production"

NUMBER_CAPACITY_POINT_1 = "number.deye_sunsynk_sol_ark_capacity_point_1"
SWITCH_TOU_STATE = "switch.deye_sunsynk_sol_ark_use_timer"

# Solcast integration and forecast solar API configuration
DEFAULT_SOLCAST_PERCENTILE = 25
FORECAST_SOLAR_API_URL = "https://api.forecast.solar/estimate/watts/"
CORE_CONFIG_STORAGE = "/workspaces/core/config/.storage/core.config_entries"
CORE_ENERGY_STORAGE = "/workspaces/core/config/.storage/energy"
CORE_FORECAST_FILTER = "config_entry_solar_forecast"

# Default configuration values for GRIST
DEFAULT_BATTERY_CAPACITY_AH = 100
DEFAULT_BATTERY_FLOAT_VOLTAGE = 56.2
DEFAULT_BATTERY_MIN_SOC = 20
DEFAULT_GRIST_MODE = BoostMode.TESTING
DEFAULT_GRIST_START = 0
DEFAULT_GRIST_END = 6
DEFAULT_GRIST_STARTING_SOC = 50
DEFAULT_INVERTER_EFFICIENCY = 96.6
DEFAULT_LOAD_AVERAGE_DAYS = 4
DEFAULT_LOAD_ESTIMATE = 1000
DEFAULT_MANUAL_GRIST = 50
DEFAULT_PV_MAX_DAYS = 21
DEFAULT_UPDATE_HOUR = 22
DEFAULT_DONT_BOOST_BEFORE = 6

# Minimum and maximum values for config flow settings
GRIST_MIN_SOC = 5
GRIST_MAX_SOC = 99
HOUR_MIN = 0
HOUR_MAX = 23
HISTORY_MIN = 1
HISTORY_MAX = 10

# Miscellaneous constants
HRS_PER_DAY = 24
DATE_FORMAT = "%Y-%m-%d"
DATE_FORMAT_UTC = "%Y-%m-%dT%H:%M:%S.%fZ"
PURPLE = "\033[95m"
RESET = "\033[0m"
NBSP = "\u2007"
