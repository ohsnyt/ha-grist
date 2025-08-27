"""Constants for the Grid Boost integration."""

# Basic integration details.
# NOTE: Will Prouse. the solar diy guy (diysolarforum.com) clearly states that in a solar system, the battery can cycle
#       from 0% to 100% each day with no ill effects.
#       Therefore I allow the battery to discharge to 2% (in extraordinary circumstances).
#       My experience shows that there are some mornings between 6-9am when I use
#       more power than usual. Therefore I set my minimum boost to 20%. This gives me a 15% buffer before the battery becomes seriously low.
#
#       This allows me to maximize how much power I generate by PV, and minimize how much
#       power I require from the grid.
#
#       In my circumstance, off-peak rates are midnight to 6 am. I therefore start off-peak
#       charging at a few minutes past midnight.

from enum import Enum, StrEnum


class Status(Enum):
    """Component Status."""

    NOT_CONFIGURED = 0
    FAULT = 1
    NORMAL = 2
    STARTING = 3

    @property
    def state(self):
        """Return the string representation of the current status."""
        if self == Status.NOT_CONFIGURED:
            return "Not Configured"
        if self == Status.FAULT:
            return "Fault"
        if self == Status.NORMAL:
            return "Normal"
        if self == Status.STARTING:
            return "Starting"
        return "Unknown"


class BoostMode(StrEnum):
    """Grid Boost Modes."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"
    OFF = "off"
    TESTING = "testing"


BOOST_MODE_OPTIONS = (
    BoostMode.AUTOMATIC,
    BoostMode.MANUAL,
    BoostMode.OFF,
    BoostMode.TESTING,
)

# Used for init, config flow, and coordinator
DOMAIN = "grist"
DOMAIN_STR = "GRIST"
PLATFORMS = ["sensor"]
UPDATE_INTERVAL = 10  # Update interval in seconds

# Turn on integration detailed debugging logging (True)
DEBUGGING = True

# Storage keys for the Grid Boost data
FORECAST_KEY = "grist_forecast"
STORAGE_VERSION = 1

# Sensor names used in the integration
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

# Items for Solcast integration
DEFAULT_SOLCAST_PERCENTILE = 25
# URL for the forecast solar API
FORECAST_SOLAR_API_URL = "https://api.forecast.solar/estimate/watts/"
CORE_CONFIG_STORAGE = "/workspaces/core/config/.storage/core.config_entries"
CORE_ENERGY_STORAGE = "/workspaces/core/config/.storage/energy"
CORE_FORECAST_FILTER = "config_entry_solar_forecast"

# Default values for the Grid Boost
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

# Minimum and maximum values for config_flow settings
GRIST_MIN_SOC = 5
GRIST_MAX_SOC = 99
HOUR_MIN = 0
HOUR_MAX = 23
HISTORY_MIN = 1
HISTORY_MAX = 10

# Commonly used constants
HRS_PER_DAY = 24
DATE_FORMAT = "%Y-%m-%d"
DATE_FORMAT_UTC = "%Y-%m-%dT%H:%M:%S.%fZ"
PURPLE = "\033[95m"
RESET = "\033[0m"
