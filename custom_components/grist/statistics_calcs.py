"""Calculated statistics for the GRIST integration.

Provides the DailyStats class for managing and calculating photovoltaic (PV) and load
statistics used by the GRIST integration. This includes calculating average hourly
load, PV performance ratios, and adjusted PV forecasts for yesterday, today, and tomorrow.

All calculations are performed asynchronously and use Home Assistant's async patterns.

Classes:
    DailyStats: Manages and calculates PV and load statistics for GRIST.

Functions:
    performance_ratios: Calculates hourly PV performance ratios based on historical data.

Dependencies:
    - homeassistant.core.HomeAssistant: Home Assistant core instance.
    - .const: Integration constants and defaults.
    - .forecast_solar, .hass_utilities, .meteo, .solcast: Forecast and utility modules.

Usage:
    Instantiate DailyStats with a Home Assistant instance and call async_initialize()
    with a forecaster to populate statistics. Use properties to access calculated values.
"""

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    DEBUGGING,
    DEFAULT_LOAD_AVERAGE_DAYS,
    DEFAULT_LOAD_ESTIMATE,
    DEFAULT_PV_MAX_DAYS,
    HRS_PER_DAY,
    SENSOR_BATTERY_SOC,
    SENSOR_LOAD_POWER,
    SENSOR_PV_POWER,
    Status,
)
from .forecasters.forecast_solar import ForecastSolar
from .forecasters.meteo import Meteo
from .forecasters.solcast import Solcast
from .hass_utilities import get_historical_hourly_states, get_multiday_hourly_states

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUGGING else logging.INFO)


class DailyStats:
    """Manages and calculates PV and load statistics for GRIST.

    This class interfaces with Home Assistant sensors and forecast services to
    provide calculated statistics such as average hourly load, PV performance ratios,
    and adjusted PV forecasts for use in GRIST scheduling.

    Attributes:
        hass: The Home Assistant instance.
        days_load_history: Number of days to use for calculating average load.
        _average_hourly_load: Average hourly load for the configured period.
        _battery_hourly_soc: Hourly battery state of charge.
        _pv_performance_ratios: Hourly PV performance ratios.
        _forecast_yesterday_adjusted: Adjusted PV forecast for yesterday.
        _forecast_today_adjusted: Adjusted PV forecast for today.
        _forecast_tomorrow_adjusted: Adjusted PV forecast for tomorrow.
        _status: Status of the statistics calculation.
        _last_update: Timestamp of the last update.

    """

    def __init__(
        self,
        hass: HomeAssistant,
        load_history_days: int = DEFAULT_LOAD_AVERAGE_DAYS,
    ) -> None:
        """Initialize DailyStats with default values.

        Args:
            hass: The Home Assistant instance.
            load_history_days: Number of days to use for calculating average load history.

        """
        self.hass = hass
        self.days_load_history: int = load_history_days
        self._average_hourly_load: dict[int, int] = dict.fromkeys(
            range(HRS_PER_DAY), DEFAULT_LOAD_ESTIMATE
        )
        self._battery_hourly_soc: dict[int, float] = dict.fromkeys(
            range(HRS_PER_DAY), 0
        )
        self._pv_performance_ratios: dict[int, float] = dict.fromkeys(
            range(HRS_PER_DAY), 1.0
        )
        self._forecast_yesterday_adjusted: dict[int, int] = dict.fromkeys(
            range(HRS_PER_DAY), 0
        )
        self._forecast_today_adjusted: dict[int, int] = dict.fromkeys(
            range(HRS_PER_DAY), 0
        )
        self._forecast_tomorrow_adjusted: dict[int, int] = dict.fromkeys(
            range(HRS_PER_DAY), 0
        )
        self._status = Status.NOT_CONFIGURED
        self._last_update = dt_util.now() - timedelta(days=1)

    async def async_initialize(
        self, forecaster: Solcast | Meteo | ForecastSolar
    ) -> None:
        """Initialize statistics by fetching data from Home Assistant sensors.

        Args:
            forecaster: The forecasting service instance (Solcast, Meteo, or ForecastSolar).

        """
        await self.update_data(forecaster)

    async def async_unload_entry(self) -> None:
        """Unload resources held by DailyStats and reset status."""
        self._status = Status.NOT_CONFIGURED
        logger.debug("Unloaded DailyStats entry")

    async def update_data(self, forecaster: Solcast | Meteo | ForecastSolar) -> None:
        """Fetch and process daily statistics from Home Assistant and forecast services.

        Updates PV performance ratios, average hourly load, and adjusted PV forecasts
        for yesterday, today, and tomorrow.

        Args:
            forecaster: The forecasting service instance (Solcast, Meteo, or ForecastSolar).

        """
        if not forecaster:
            logger.warning("No forecaster available for CalculatedStats")
            self._status = Status.FAULT
            return

        # Only update once per day
        if dt_util.now().date() > self._last_update.date():
            forecasted_pv: dict[str, dict[int, int]] = forecaster.all_forecasts
            soc: dict[str, dict[int, int]] = await get_historical_hourly_states(
                self.hass, SENSOR_BATTERY_SOC, days=DEFAULT_PV_MAX_DAYS, default=0
            )
            actual_pv = await get_historical_hourly_states(
                self.hass, SENSOR_PV_POWER, days=DEFAULT_PV_MAX_DAYS, default=0
            )
            self._pv_performance_ratios = performance_ratios(
                forecasted_pv,
                soc,
                actual_pv,
            )

            self._average_hourly_load = await get_multiday_hourly_states(
                self.hass,
                SENSOR_LOAD_POWER,
                days=self.days_load_history,
                default=DEFAULT_LOAD_ESTIMATE,
            )
            logger.debug("Average hourly load: %s", self._average_hourly_load)

            now = dt_util.now()
            today_str: str = now.strftime("%Y-%m-%d")
            tomorrow_str: str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            yesterday_str: str = (now + timedelta(days=-1)).strftime("%Y-%m-%d")

            forecast_today = forecasted_pv.get(today_str, {})
            forecast_tomorrow = forecasted_pv.get(tomorrow_str, {})
            forecast_yesterday = forecasted_pv.get(yesterday_str, {})

            self._forecast_today_adjusted = {
                hour: int(
                    forecast_today.get(hour, 0) * self._pv_performance_ratios[hour]
                )
                for hour in range(HRS_PER_DAY)
            }
            self._forecast_tomorrow_adjusted = {
                hour: int(
                    forecast_tomorrow.get(hour, 0) * self._pv_performance_ratios[hour]
                )
                for hour in range(HRS_PER_DAY)
            }
            self._forecast_yesterday_adjusted = {
                hour: int(
                    forecast_yesterday.get(hour, 0) * self._pv_performance_ratios[hour]
                )
                for hour in range(HRS_PER_DAY)
            }

            self._status = Status.NORMAL
            self._last_update = dt_util.now()

    @property
    def pv_performance_ratios(self) -> dict[int, float]:
        """Return the PV performance ratios for each hour."""
        return self._pv_performance_ratios

    @property
    def average_hourly_load(self) -> dict[int, int]:
        """Return the average hourly load for each hour."""
        return self._average_hourly_load

    @property
    def forecast_yesterday_adjusted(self) -> dict[int, int]:
        """Return the adjusted PV forecast for yesterday."""
        return self._forecast_yesterday_adjusted

    @property
    def forecast_today_adjusted(self) -> dict[int, int]:
        """Return the adjusted PV forecast for today."""
        return self._forecast_today_adjusted

    @property
    def forecast_tomorrow_adjusted(self) -> dict[int, int]:
        """Return the adjusted PV forecast for tomorrow."""
        return self._forecast_tomorrow_adjusted

    @property
    def forecast_yesterday_adjusted_total(self) -> int:
        """Return the total adjusted PV forecast for yesterday."""
        return sum(self._forecast_yesterday_adjusted.values())

    @property
    def forecast_today_adjusted_total(self) -> int:
        """Return the total adjusted PV forecast for today."""
        return sum(self._forecast_today_adjusted.values())

    @property
    def forecast_tomorrow_adjusted_total(self) -> int:
        """Return the total adjusted PV forecast for tomorrow."""
        return sum(self._forecast_tomorrow_adjusted.values())

    @property
    def status(self) -> Status:
        """Return the current status of the statistics calculations."""
        return self._status


def performance_ratios(
    forecasted_pv: dict[str, dict[int, int]],
    soc: dict[str, dict[int, int]],
    actual_pv: dict[str, dict[int, int]],
) -> dict[int, float]:
    """Calculate hourly PV performance ratios.

    Ratios are based on DEFAULT_PV_MAX_DAYS, (21 days) of estimated PV, SoC, and historical data.

    For each day with available data, calculate the ratio of actual PV to estimated PV
    generation for each hour when the state of charge is less than 98%. If there is no
    forecasted PV or the state of charge is 97% or more, default the ratio to 1.0.

    Args:
        forecasted_pv: Mapping of date string to hourly forecasted PV values.
        soc: Mapping of date string to hourly state of charge values.
        actual_pv: Mapping of date string to hourly actual PV values.

    Returns:
        Dictionary mapping each hour to its average performance ratio.

    """
    daily_ratios: dict[str, dict[int, float]] = {}
    hourly_ratios: dict[int, float] = dict.fromkeys(range(HRS_PER_DAY), 1.0)
    average_ratios = dict.fromkeys(range(HRS_PER_DAY), 0.0)

    for day in range(1, HRS_PER_DAY):
        this_day = dt_util.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=-day)
        this_day_str = this_day.strftime("%Y-%m-%d")
        if (
            forecasted_pv.get(this_day_str) is None
            or soc.get(this_day_str) is None
            or actual_pv.get(this_day_str) is None
        ):
            # No forecast details available for this day, go to the next day
            continue
        hourly_ratios = dict.fromkeys(range(HRS_PER_DAY), 1.0)
        for hour in range(HRS_PER_DAY):
            forecasted_pv_hour = forecasted_pv[this_day_str].get(hour)
            soc_hour = soc[this_day_str].get(hour)
            actual_pv_hour = actual_pv[this_day_str].get(hour)
            if forecasted_pv_hour is None or soc_hour is None or actual_pv_hour is None:
                continue
            if forecasted_pv_hour > 0 and soc_hour < 98:
                hourly_ratios[hour] = actual_pv_hour / forecasted_pv_hour
            else:
                hourly_ratios[hour] = 1.0
        daily_ratios[this_day_str] = hourly_ratios

    for hour in range(HRS_PER_DAY):
        if len(daily_ratios) == 0:
            average_ratios[hour] = 1.0
        else:
            total = sum(ratios.get(hour, 1.0) for _, ratios in daily_ratios.items())
            average_ratios[hour] = total / len(daily_ratios)
    logger.debug(
        "Unusual hourly ratios: %s",
        {
            hour: f"{ratio:.1f}"
            for hour, ratio in average_ratios.items()
            if ratio != 1.0
        },
    )
    return average_ratios
