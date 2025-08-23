"""Utilites for Home Assistant shared by Grid Boost integration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
import logging
from typing import Any

# from config.custom_components.grid_boost.solcast import HourlyForecast
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    StatisticsRow,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DEBUGGING

logger: logging.Logger = logging.getLogger(__name__)
if DEBUGGING:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)


async def find_entities_by_prefixes(
    hass: HomeAssistant, prefixes: list[str]
) -> list[str]:
    """Find entities starting with a given prefix.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        prefixes (list[str]): The list of prefixes to match entity IDs against.

    Returns:
        float: The sum of the states of entities that match the prefixes, or the default value if none are found.

    """
    # Find all entities that start with the given prefix
    entities = []
    for prefix in prefixes:
        entities.extend(
            state.entity_id
            for state in hass.states.async_all("sensor")
            if state.entity_id.startswith(prefix)
        )
    if not entities:
        logger.warning("No entities found with prefix %s", prefixes)
    return entities


async def get_state(hass: HomeAssistant, entity_id: str) -> str | None:
    """Safely retrieves the state of a Home Assistant entity.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entity_id (str): The entity ID to retrieve.

    Returns:
        str | None: The state of the entity if it exists; otherwise, None.

    """
    entity = await get_entity(hass, entity_id)
    if entity:
        return entity["state"]
    return None


async def get_entity(hass: HomeAssistant, entity_id: str) -> dict[str, Any] | None:
    """Safely retrieves the state and attributes of a Home Assistant entity.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entity_id (str): The entity ID to retrieve.

    Returns:
        dict[str, Any] | None: A dictionary containing the entity's state, attributes,
        last_changed, and last_updated if the entity exists; otherwise, None.

    """
    state_obj = hass.states.get(entity_id)
    # logger.debug("State object for %s: %s", entity_id, state_obj)
    if not state_obj:
        logger.debug("Entity %s not found", entity_id)
        return None

    return {
        "state": state_obj.state,
        "attributes": state_obj.attributes,
        "last_changed": state_obj.last_changed,
        "last_updated": state_obj.last_updated,
    }


async def get_state_as_float(
    hass: HomeAssistant, entity_id: str, default: float = 0.0
) -> float:
    """Get the value of a number entity.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entity_id (str): The entity ID to retrieve.
        default (float): The default value to return if the entity does not exist.

    Returns:
        float: The value of the state or the default value if not found.

    """
    state = await get_entity(hass, entity_id)
    if state and "state" in state:
        state_value = state["state"]
        try:
            # Check for unavailable/unknown and non-numeric values
            if state_value in ("unavailable", "unknown", None):
                logger.error("Invalid number state for %s: %s", entity_id, state_value)
                return default
            return float(state_value)
        except (ValueError, TypeError):
            logger.error("Invalid number state for %s: %s", entity_id, state_value)
    return default


async def sum_states_starting_with(
    hass: HomeAssistant, prefixes: list[str], default: float = 0.0
) -> float:
    """Sum states of entities starting with a given prefix.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        prefixes (list[str]): The list of prefixes to match entity IDs against.
        default (float): The default value to return if no entities are found.

    Returns:
        list[str]: A list of entity IDs that match the prefixes.

    """
    # Find all entities that match the prefixes
    entities = [
        state.entity_id
        for state in hass.states.async_all("sensor")
        if any(state.entity_id.startswith(prefix) for prefix in prefixes)
    ]

    if not entities:
        logger.warning("No entities found with prefixes: %s", prefixes)
        return default

    # Sum the states of the matching entities
    values = []
    for entity_id in entities:
        state = await get_state(hass, entity_id)
        if state is not None and state.replace(".", "", 1).isdigit():
            values.append(float(state))

    total = sum(values)
    return total if total else default


async def get_multiday_hourly_states(
    hass: HomeAssistant, entity_id: str, days: int = 1, default: float = 0.0
) -> dict[int, int]:
    """Fetch and format hourly statistics data for a given entity.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entity_id (str): The entity_id to fetch history for.
        days (int): How many days of history to fetch (default is 1).
        default (float): The default value to use if no data is available.

    Returns:
        list[dict[str, Any]]: A list of dictionaries containing the formatted data.

    """
    # Calculate the start and end times for the statistics query
    start, end = start_and_end_utc(days)

    # Fetch statistics data using the recorder instance
    stats: dict[str, list[StatisticsRow]] = await get_instance(
        hass
    ).async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        end,
        {entity_id},
        "hour",
        None,
        {"mean"},
    )

    # Extract data for the specific entity
    data = stats.get(entity_id, [])
    if not data:
        logger.warning(
            "No historical data found for entity %s over the last %d days.",
            entity_id,
            days,
        )
        return {}

    # Format the data with the hour as the key and the sum of the means / count of the means as the value
    hourly_data: dict[int, Any] = {}
    for entry in data:
        start_value: float | None = entry.get("start", None)
        if isinstance(start_value, (int, float)):
            start = dt_util.as_local(datetime.fromtimestamp(start_value))
        else:
            logger.warning("Invalid start value for %s entry: %s", entity_id, start_value)
            continue
        hour = start.hour
        raw = entry.get("mean", default)
        raw_value: int = int(raw) if raw is not None else int(default)
        if hour not in hourly_data:
            hourly_data[hour] = {"mean": 0.0, "count": 0}
        hourly_data[hour]["mean"] += raw_value
        hourly_data[hour]["count"] += 1

    # Calculate the final mean values
    for values in hourly_data.values():
        if values["count"] > 0:
            values["mean"] = int(round(values["mean"] / values["count"]))
    # Convert the hourly data to a dictionary with hour as the key and mean as the value
    return dict(sorted((hour, values["mean"]) for hour, values in hourly_data.items()))

async def get_historical_hourly_states(
    hass: HomeAssistant, entity_id: str, days: int = 1, default: float = 0.0
) -> dict[str, dict[int, int]]:
    """Fetch and format hourly statistics data for a given entity.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entity_id (str): The entity_id to fetch history for.
        days (int): How many days of history to fetch (default is 1).
        default (float): The default value to use if no data is available.

    Returns:
        dict[str, dict[int, int]]: A dictionary containing the formatted data by day.

    """
    # Calculate the start and end times for the statistics query
    start, end = start_and_end_utc(days)

    # Fetch statistics data using the recorder instance
    stats: dict[str, list[StatisticsRow]] = await get_instance(
        hass
    ).async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        end,
        {entity_id},
        "hour",
        None,
        {"mean"},
    )

    # Extract data for the specific entity
    data = stats.get(entity_id, [])
    if not data:
        logger.warning(
            "No historical data found for entity %s over the last %d days.",
            entity_id,
            days,
        )
        return {}

    # Initialize the return dictionary
    historical_data: dict[str, dict[int, int]] = {}
    hourly_data: dict[int, int] = dict.fromkeys(range(24), int(default))
    last_date_str = None

    # Get the date of the first entry in the format of YYYY-MM-DD. If it isn't a valid date, skip the entry.
    # For every date, add hourly data to the historical data for this date
    for entry in data:
        entry_start_value = entry.get("start", None)
        if isinstance(entry_start_value, (int, float)):
            entry_start_utc = datetime.fromtimestamp(entry_start_value, tz=UTC)
            entry_start = dt_util.as_local(entry_start_utc)
        else:
            logger.warning("Invalid start value for %s entry: %s", entity_id, entry_start_value)
            continue
        date_str: str = entry_start.strftime("%Y-%m-%d")
        # First time through, set the last_date_str to the current date_str
        if last_date_str is None:
            last_date_str = date_str
        # If the date has changed, add the hourly data to the historical data and reset hourly_data
        if date_str != last_date_str:
            historical_data[date_str] = hourly_data
            hourly_data = dict.fromkeys(range(24), int(default))
            last_date_str = date_str
        entry_hour = entry_start.hour
        entry_value = entry.get("mean", default)
        int_value = int(round(entry_value)) if entry_value is not None else int(default)
        hourly_data[entry_hour] = int_value
    # We are at the end of the data, so add the last day's data
    historical_data[date_str] = hourly_data
    return historical_data


async def get_number(
    hass: HomeAssistant, entity_id: str, default: float = 0.0
) -> float:
    """Get the value of a number entity.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entity_id (str): The entity ID to retrieve.
        default (float): The default value to return if the entity does not exist.

    Returns:
        float: The value of the state or the default value if not found.

    """
    state = await get_entity(hass, entity_id)
    if state and "state" in state:
        try:
            return float(state["state"])
        except ValueError:
            logger.error("Invalid number state for %s: %s", entity_id, state["state"])
    return default

async def set_number(
    hass: HomeAssistant, entity_id: str, value: int
) -> None:
    """Set the value of a number entity.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entity_id (str): The entity ID to set.
        value (int): The value to set.

    """
    await hass.services.async_call("number", "set_value", {"entity_id": entity_id, "value": value})


def start_and_end_utc(days=1) -> tuple[datetime, datetime]:
    """Calculate the start and end times for a given number of days. Since this is historical data, it must end yesterday at 23:59:59.

    Args:
        days (int): The number of days of history to include.

    Returns:
        tuple[datetime, datetime]: A tuple containing the start and end datetimes.

    """

    # Subtracting one second from midnight today gives 23:59:59 of the previous day.
    local_end_time = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
    local_start_time = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    end_time = dt_util.as_utc(local_end_time)
    start_time = dt_util.as_utc(local_start_time)

    return start_time, end_time
