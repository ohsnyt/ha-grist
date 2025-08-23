"""Class for managing calculated statistics in the Grid Boost integration.

This class interfaces between the Grid Boost integration and the underlying
Home Assistant data structures to provide calculated statistics for the
Grid Boost functionality.

"""

from datetime import timedelta
import logging
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    DEBUGGING,
    DEFAULT_LOAD_AVERAGE_DAYS,
    DEFAULT_LOAD_ESTIMATE,
    DEFAULT_PV_MAX_DAYS,
    HRS_PER_DAY,
    PURPLE,
    RESET,
    SENSOR_BATTERY_SOC,
    SENSOR_LOAD_POWER,
    SENSOR_PV_POWER,
    Status,
)
from .forecast_solar import ForecastSolar
from .hass_utilities import get_historical_hourly_states, get_multiday_hourly_states
from .meteo import Meteo
from .solcast import Solcast

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUGGING else logging.INFO)


class DailyStats:
    """Class to interface between the Grid Boost Scheduler and the photovoltaic (PV) statistics integration."""

    # Constructor
    def __init__(
        self,
        hass: HomeAssistant,
        forecaster: Solcast | Meteo | ForecastSolar,
        load_history_days: int = DEFAULT_LOAD_AVERAGE_DAYS,
    ) -> None:
        """Initialize key variables.

        Args:
            hass: The Home Assistant instance.
            forecaster: The forecasting service instance (Solcast, Meteo, or ForecastSolar).
            load_history_days: Number of days to use for calculating average load history.

        """
        # General info
        self.hass = hass
        self.forecaster: Solcast | Meteo | ForecastSolar = forecaster
        self.days_load_history: int = load_history_days  # Default days of load history
        self._timezone = ZoneInfo(self.hass.config.time_zone)
        self._average_hourly_load: dict[int, int] = dict.fromkeys(
            range(HRS_PER_DAY), DEFAULT_LOAD_ESTIMATE
        )
        self._battery_hourly_soc: dict[int, float] = dict.fromkeys(range(HRS_PER_DAY), 0)

        self._pv_performance_ratios: dict[int, float] = dict.fromkeys(range(HRS_PER_DAY), 1.0)
        self._forecast_yesterday_adjusted: dict[int, int] = dict.fromkeys(range(HRS_PER_DAY), 0)
        self._forecast_today_adjusted: dict[int, int] = dict.fromkeys(range(HRS_PER_DAY), 0)
        self._forecast_tomorrow_adjusted: dict[int, int] = dict.fromkeys(range(HRS_PER_DAY), 0)
        self._status = Status.NOT_CONFIGURED
        self._last_update = dt_util.now() - timedelta(days=1)

    async def async_initialize(self) -> None:
        """Load battery data from Home Assistant sensors."""
        # Run update_data to fetch the latest battery data
        await self.update_data()

    async def update_data(self) -> None:
        """Daily fetch and process data."""
        if not self.forecaster:
            logger.warning("No forecaster available for CalculatedStats.")
            self._status = Status.FAULT
            return

        # Calculate the performance ratios and load averages once a day
        if dt_util.now().date() > self._last_update.date():
            # Get historical data for the calculations
            forecasted_pv: dict[str, dict[int, int]] = self.forecaster.all_forecasts
            soc: dict[str, dict[int, int]] = await get_historical_hourly_states(
                self.hass, SENSOR_BATTERY_SOC, days=DEFAULT_PV_MAX_DAYS, default=0
            )
            actual_pv = await get_historical_hourly_states(
                self.hass, SENSOR_PV_POWER, days=DEFAULT_PV_MAX_DAYS, default=0
            )
            # Run the performance ratios calculation
            self._pv_performance_ratios = performance_ratios(
                forecasted_pv,
                soc,
                actual_pv,
            )

            # Calculate the average hourly load for default days of load history
            self._average_hourly_load = await get_multiday_hourly_states(
                self.hass,
                SENSOR_LOAD_POWER,
                days=self.days_load_history,
                default=DEFAULT_LOAD_ESTIMATE,
            )
            logger.debug("\nAverage hourly load: %s", self._average_hourly_load)

            # Calculate the adjusted forecast for today and yesterday
            # Get keys
            now = dt_util.now()
            today_str: str = now.strftime("%Y-%m-%d")
            tomorrow_str: str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            yesterday_str: str = (now + timedelta(days=-1)).strftime("%Y-%m-%d")
            # Get data based on keys
            forecast_today = forecasted_pv.get(today_str, {})
            forecast_tomorrow = forecasted_pv.get(tomorrow_str, {})
            forecast_yesterday = forecasted_pv.get(yesterday_str, {})
            # Do calculations
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
        """Return the PV performance ratios."""
        return self._pv_performance_ratios

    @property
    def average_hourly_load(self) -> dict[int, int]:
        """Return the average hourly load."""
        return self._average_hourly_load

    @property
    def forecast_yesterday_adjusted(self) -> dict[int, int]:
        """Return the adjusted forecast for yesterday."""
        return self._forecast_yesterday_adjusted

    @property
    def forecast_today_adjusted(self) -> dict[int, int]:
        """Return the adjusted forecast for today."""
        return self._forecast_today_adjusted

    @property
    def forecast_tomorrow_adjusted(self) -> dict[int, int]:
        """Return the adjusted forecast for tomorrow."""
        return self._forecast_tomorrow_adjusted

    @property
    def forecast_yesterday_adjusted_total(self) -> int:
        """Return the total adjusted forecast for yesterday."""
        return sum(self._forecast_yesterday_adjusted.values())

    @property
    def forecast_today_adjusted_total(self) -> int:
        """Return the total adjusted forecast for today."""
        return sum(self._forecast_today_adjusted.values())

    @property
    def forecast_tomorrow_adjusted_total(self) -> int:
        """Return the total adjusted forecast for tomorrow."""
        return sum(self._forecast_tomorrow_adjusted.values())


def performance_ratios(
    forecasted_pv: dict[str, dict[int, int]],
    soc: dict[str, dict[int, int]],
    actual_pv: dict[str, dict[int, int]],
) -> dict[int, float]:
    """Calculate the performance ratios for each hour based on 21 days of estimated pv, state of charge, and historical data.

    For each day that we have data in all three categories, calculate the ratio of actual PV to estimated PV generation for each hour when the state of charge is less than 98%. If there is no forecasted PV or the state of charge is 97% or more, default the ratio to 1.0.

    """
    # Initialize the dictionaries
    daily_ratios: dict[str, dict[int, float]] = {}
    hourly_ratios: dict[int, float] = dict.fromkeys(range(HRS_PER_DAY), 1.0)
    average_ratios = dict.fromkeys(range(HRS_PER_DAY), 0.0)

    # Starting with yesterday (first full day of data), get ratios for the past 21 days
    for day in range(1, HRS_PER_DAY):
        # Skip over days when we don't have data in all three categories
        this_day = dt_util.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=-day)
        this_day_str = this_day.strftime("%Y-%m-%d")
        if (
            forecasted_pv.get(this_day_str) is None
            or soc.get(this_day_str) is None
            or actual_pv.get(this_day_str) is None
        ):
            logger.debug("Skipping %s due to missing data", this_day_str)
            continue
        hourly_ratios: dict[int, float] = dict.fromkeys(range(HRS_PER_DAY), 1.0)
        for hour in range(HRS_PER_DAY):
            # Get the maximum PV, state of charge, and actual PV for this hour
            forecasted_pv_hour = forecasted_pv[this_day_str].get(hour)
            soc_hour = soc[this_day_str].get(hour)
            actual_pv_hour = actual_pv[this_day_str].get(hour)
            if forecasted_pv_hour is None or soc_hour is None or actual_pv_hour is None:
                continue

            # Calculate the ratio if the state of charge is less than 98%
            if forecasted_pv_hour > 0 and soc_hour < 98:
                hourly_ratios[hour] = actual_pv_hour / forecasted_pv_hour
            else:
                hourly_ratios[hour] = 1.0
        # logger.debug(
        #     "\nCalculated hourly ratios for %s: \n%s", this_day_str, hourly_ratios
        # )
        daily_ratios[this_day_str] = hourly_ratios

    # Calculate the average ratios for each hour
    for hour in range(HRS_PER_DAY):
        if len(daily_ratios) == 0:
            average_ratios[hour] = 1.0
        else:
            total = sum(ratios.get(hour, 1.0) for _, ratios in daily_ratios.items())
            average_ratios[hour] = total / len(daily_ratios)
    logger.debug(
        "\n%sAverage hourly ratios: \n%s%s",
        PURPLE,
        {hour: f"{ratio:.1f}" for hour, ratio in average_ratios.items()},
        RESET
    )
    return average_ratios
