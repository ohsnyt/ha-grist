"""Calculated statistics for the GRIST integration.

Provides async calculation and management of photovoltaic (PV) and load statistics
for the GRIST integration, including average hourly load, PV performance ratios,
and adjusted PV forecasts for yesterday, today, and tomorrow.

All calculations are performed asynchronously and follow Home Assistant's update
coordinator pattern for efficient polling and state updates.

Classes:
    DailyStats: Manages and calculates PV and load statistics for GRIST.

Functions:
    performance_ratios: Calculates hourly PV performance ratios based on historical data.
    start_and_end_utc: Utility for calculating UTC start/end datetimes for statistics queries.

Dependencies:
    - homeassistant.core.HomeAssistant
    - .const
    - .forecast_solar, .meteo, .solcast

Usage:
    Instantiate DailyStats with a Home Assistant instance and call async_initialize()
    with a forecaster to populate statistics. Use properties to access calculated values.
"""

from datetime import UTC, datetime, timedelta
import logging

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    StatisticsRow,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    # DEBUGGING,
    DEFAULT_LOAD_AVERAGE_DAYS,
    DEFAULT_LOAD_ESTIMATE,
    DEFAULT_PV_MAX_DAYS,
    HRS_PER_DAY,
    SENSOR_BATTERY_POWER,
    SENSOR_BATTERY_SOC,
    SENSOR_GRID_POWER,
    SENSOR_LOAD_POWER,
    SENSOR_PV_POWER,
    Status,
)
from .forecasters.forecast_solar import ForecastSolar
from .forecasters.meteo import Meteo
from .forecasters.solcast import Solcast

logger = logging.getLogger(__name__)
# Set logging to debug for this module.
logger.setLevel(logging.DEBUG)


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
        self._last_update = None
        self._losses = 0.0

    async def async_initialize(
        self, forecaster: Solcast | Meteo | ForecastSolar
    ) -> None:
        """Initialize statistics by fetching data from Home Assistant sensors.

        Args:
            forecaster: The forecasting service instance (Solcast, Meteo, or ForecastSolar).

        """
        logger.debug(">>>Initializing DailyStats. Updating forecaster data.")
        await self.update_data(forecaster)

    async def async_unload_entry(self) -> None:
        """Unload resources held by DailyStats and reset status."""
        self._status = Status.NOT_CONFIGURED
        logger.debug(">>>Unloaded DailyStats entry")

    async def update_data(
        self, forecaster: Solcast | Meteo | ForecastSolar | None
    ) -> None:
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
        logger.debug(">>>Checking if we need to update DailyStats data")
        if self._last_update is None or dt_util.now().date() > self._last_update.date():
            logger.debug(">>>Calculating average loss")
            self._losses = await self.update_losses()
            logger.debug(">>>Getting DailyStats data: forecasted PV")
            forecasted_pv: dict[str, dict[int, int]] = forecaster.all_forecasts
            logger.debug(">>>Getting DailyStats data: historical SOC")
            soc: dict[str, dict[int, int]] = await self.get_historical_hourly_states(
                SENSOR_BATTERY_SOC, days=DEFAULT_PV_MAX_DAYS
            )
            logger.debug(">>>Getting DailyStats data: actual PV")
            actual_pv = await self.get_historical_hourly_states(
                SENSOR_PV_POWER, days=DEFAULT_PV_MAX_DAYS
            )
            logger.debug(">>>Regenerating performance ratios")
            self._pv_performance_ratios = performance_ratios(
                forecasted_pv,
                soc,
                actual_pv,
            )

            self._average_hourly_load = await self.get_multiday_hourly_loads()
            logger.debug(">>>Average hourly load: %s", self._average_hourly_load)

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

    async def update_losses(self) -> float:
        """Fetch and calculate energy losses over multiple days."""
        # Fetch PV and grid generation hourly statistics for the past history days
        pv = await self.get_historical_hourly_states(
            SENSOR_PV_POWER, days=self.days_load_history
        )
        grid = await self.get_historical_hourly_states(
            SENSOR_GRID_POWER, days=self.days_load_history
        )

        # Fetch battery charge/discharge hourly statistics for the past history days
        battery = await self.get_historical_hourly_states(
            SENSOR_BATTERY_POWER, days=self.days_load_history
        )

        # Fetch load hourly statistics for the past history days
        loads = await self.get_historical_hourly_states(
            SENSOR_LOAD_POWER, days=self.days_load_history
        )

        # Calculate losses for each hour across all days
        total_losses = 0.0
        valid_hours = 0

        # Get all unique dates that have any data
        all_dates = (
            set(pv.keys()) | set(grid.keys()) | set(battery.keys()) | set(loads.keys())
        )

        for date_str in all_dates:
            for hour in range(HRS_PER_DAY):
                # Check if all sensors have data for this hour
                if (
                    date_str not in pv
                    or date_str not in grid
                    or date_str not in battery
                    or date_str not in loads
                ):
                    continue

                pv_value = pv[date_str].get(hour)
                grid_value = grid[date_str].get(hour)
                battery_value = battery[date_str].get(hour)
                load_value = loads[date_str].get(hour)

                # Skip if any value is None
                if any(
                    v is None for v in [pv_value, grid_value, battery_value, load_value]
                ):
                    logger.debug(
                        "Day %s hour %d: Missing sensor data - excluding from loss calculation",
                        date_str,
                        hour,
                    )
                    continue

                # Type narrowing: assert values are not None after the check
                assert pv_value is not None
                assert grid_value is not None
                assert battery_value is not None
                assert load_value is not None

                # Calculate generation: PV + grid + battery discharge (negative battery power)
                generation = (
                    pv_value + grid_value + (-battery_value if battery_value < 0 else 0)
                )

                # Calculate consumption: loads + battery charge (positive battery power)
                consumption = load_value + (max(0, battery_value))

                # Losses = generation - consumption
                hourly_loss = generation - consumption
                total_losses += hourly_loss
                valid_hours += 1

                logger.debug(
                    "Day %s hour %d: gen=%d (pv=%d, grid=%d, batt_discharge=%d), "
                    "cons=%d (load=%d, batt_charge=%d), loss=%d",
                    date_str,
                    hour,
                    generation,
                    pv_value,
                    grid_value,
                    -battery_value if battery_value < 0 else 0,
                    consumption,
                    load_value,
                    max(0, battery_value),
                    hourly_loss,
                )

        # Calculate average losses
        if valid_hours > 0:
            self._losses = total_losses / valid_hours
            logger.debug(
                "Calculated average losses: %.2f W (total=%.2f W over %d valid hours)",
                self._losses,
                total_losses,
                valid_hours,
            )
        else:
            self._losses = 0.0
            logger.warning("No valid hours found for loss calculation")

        return self._losses

    async def get_historical_hourly_states(
        self, entity_id: str, days: int
    ) -> dict[str, dict[int, int]]:
        """Fetch and format hourly statistics data for a given entity.

        Args:
            entity_id (str): The entity_id to fetch history for.
            days (int): How many days of history to fetch.

        Returns:
            dict[str, dict[int, int]]: Dictionary mapping date strings to hourly values.

        """
        start, end = start_and_end_utc(days)
        stats: dict[str, list[StatisticsRow]] = await get_instance(
            self.hass
        ).async_add_executor_job(
            statistics_during_period,
            self.hass,
            start,
            end,
            {entity_id},
            "hour",
            None,
            {"mean"},
        )

        data = stats.get(entity_id, [])
        if not data:
            logger.warning(
                "No historical data found for entity %s over the last %d days.",
                entity_id,
                days,
            )
            return {}

        historical_data: dict[str, dict[int, int]] = {}
        for entry in data:
            entry_start_value = entry.get("start")
            if not isinstance(entry_start_value, (int, float)):
                logger.warning(
                    "Invalid start value for %s entry: %s", entity_id, entry_start_value
                )
                continue
            entry_start_utc = datetime.fromtimestamp(entry_start_value, tz=UTC)
            entry_start = dt_util.as_local(entry_start_utc)
            date_str = entry_start.strftime("%Y-%m-%d")
            hour = entry_start.hour
            value = int(round(entry.get("mean", 0.0) or 0.0))
            if date_str not in historical_data:
                historical_data[date_str] = dict.fromkeys(range(HRS_PER_DAY), 0)
            historical_data[date_str][hour] = value

        return historical_data

    async def get_multiday_hourly_loads(self) -> dict[int, int]:
        """Fetch and calculate average hourly load over multiple days.

        Returns:
            dict[int, int]: Dictionary mapping hour to average load.

        """
        start, end = start_and_end_utc(self.days_load_history)
        stats: dict[str, list[StatisticsRow]] = await get_instance(
            self.hass
        ).async_add_executor_job(
            statistics_during_period,
            self.hass,
            start,
            end,
            {SENSOR_LOAD_POWER},
            "hour",
            None,
            {"mean"},
        )

        data = stats.get(SENSOR_LOAD_POWER, [])
        if not data:
            logger.warning(
                "No historical data found for entity %s over the last %d days.",
                SENSOR_LOAD_POWER,
                self.days_load_history,
            )
            return {}

        # Use a fixed-size array for sums and counts for each hour
        sums = [0.0] * HRS_PER_DAY
        counts = [0] * HRS_PER_DAY

        for entry in data:
            start_value = entry.get("start")
            if not isinstance(start_value, (int, float)):
                logger.warning(
                    "Invalid start value for %s entry: %s",
                    SENSOR_LOAD_POWER,
                    start_value,
                )
                continue
            hour = dt_util.as_local(datetime.fromtimestamp(start_value, tz=UTC)).hour
            mean = entry.get("mean", 0.0) or 0.0
            sums[hour] += mean
            counts[hour] += 1

        # Calculate integer mean per hour
        return {
            hour: int(round(sums[hour] / counts[hour])) if counts[hour] > 0 else 0
            for hour in range(HRS_PER_DAY)
        }

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
    def losses(self) -> float:
        """Return the calculated average losses in watts."""
        return self._losses

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

    logger.debug(
        "Starting performance ratio calculations for %d days", DEFAULT_PV_MAX_DAYS
    )

    for day in range(1, DEFAULT_PV_MAX_DAYS + 1):
        this_day = dt_util.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=-day)
        this_day_str = this_day.strftime("%Y-%m-%d")

        # Check if all required data is available for this day
        has_forecast = forecasted_pv.get(this_day_str) is not None
        has_soc = soc.get(this_day_str) is not None
        has_actual = actual_pv.get(this_day_str) is not None

        if not (has_forecast and has_soc and has_actual):
            logger.debug(
                "Day %s: Skipping (forecast=%s, soc=%s, actual=%s)",
                this_day_str,
                has_forecast,
                has_soc,
                has_actual,
            )
            continue

        logger.debug(">>>Day %s: Processing hourly ratios", this_day_str)
        hourly_ratios = dict.fromkeys(range(HRS_PER_DAY), 1.0)

        for hour in range(HRS_PER_DAY):
            forecasted_pv_hour = forecasted_pv[this_day_str].get(hour)
            soc_hour = soc[this_day_str].get(hour)
            actual_pv_hour = actual_pv[this_day_str].get(hour)

            if forecasted_pv_hour is None or soc_hour is None or actual_pv_hour is None:
                logger.debug(
                    "Day %s hour %d: Missing data (forecast=%s, soc=%s, actual=%s) - using default ratio 1.0",
                    this_day_str,
                    hour,
                    forecasted_pv_hour,
                    soc_hour,
                    actual_pv_hour,
                )
                continue

            if forecasted_pv_hour > 0 and soc_hour > 98:
                ratio = actual_pv_hour / forecasted_pv_hour
                hourly_ratios[hour] = ratio
                logger.debug(
                    "Day %s hour %d: Optimal conditions (forecast=%d > 0, soc=%d > 98) - "
                    "calculated ratio = %d / %d = %.3f",
                    this_day_str,
                    hour,
                    forecasted_pv_hour,
                    soc_hour,
                    actual_pv_hour,
                    forecasted_pv_hour,
                    ratio,
                )
            else:
                hourly_ratios[hour] = 1.0
                reasons = []
                if forecasted_pv_hour <= 0:
                    reasons.append(f"forecast={forecasted_pv_hour} <= 0")
                if soc_hour <= 98:
                    reasons.append(f"soc={soc_hour} <= 98")
                logger.debug(
                    "Day %s hour %d: Not optimal (%s) - using default ratio 1.0",
                    this_day_str,
                    hour,
                    ", ".join(reasons),
                )

        daily_ratios[this_day_str] = hourly_ratios

    logger.debug(">>>Calculating average ratios across %d days", len(daily_ratios))

    for hour in range(HRS_PER_DAY):
        if len(daily_ratios) == 0:
            average_ratios[hour] = 1.0
            logger.debug(
                "Hour %d: No daily data available - using default ratio 1.0", hour
            )
        else:
            daily_values = [ratios.get(hour, 1.0) for _, ratios in daily_ratios.items()]
            total = sum(daily_values)
            average_ratios[hour] = total / len(daily_ratios)
            logger.debug(
                "Hour %d: Average ratio = %.3f (sum=%.3f / %d days, values=%s)",
                hour,
                average_ratios[hour],
                total,
                len(daily_ratios),
                [f"{v:.2f}" for v in daily_values],
            )

    logger.debug(
        "Unusual hourly ratios: %s",
        {
            hour: f"{ratio:.1f}"
            for hour, ratio in average_ratios.items()
            if ratio != 1.0
        },
    )
    return average_ratios


def start_and_end_utc(days=1) -> tuple[datetime, datetime]:
    """Return UTC start and end datetimes for a given number of days of history.

    The end time is yesterday at 23:59:59, and the start time is 'days' before midnight today.

    Args:
        days (int): The number of days of history to include.

    Returns:
        tuple[datetime, datetime]: A tuple containing the start and end datetimes.

    """

    # Subtracting one second from midnight today gives 23:59:59 of the previous day.
    local_end_time = dt_util.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(seconds=1)
    local_start_time = dt_util.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=days)
    end_time = dt_util.as_utc(local_end_time)
    start_time = dt_util.as_utc(local_start_time)

    return start_time, end_time
