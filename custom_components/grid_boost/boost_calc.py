"""Boost calculation utilities for grid_boost integration."""

import logging
import math

from homeassistant.util import dt as dt_util

from .const import DEBUGGING, DEFAULT_DONT_BOOST_BEFORE, PURPLE, RESET

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if DEBUGGING else logging.INFO)

def calculate_required_boost(battery_max_wh, efficiency, minimum_soc, adjusted_pv, average_hourly_load) -> float | None:
    """Calculate required boost for tomorrow."""
    # Debugging, check adjusted_pv to see if it is all zeros
    if not adjusted_pv or all(value == 0 for value in adjusted_pv.values()):
        logger.warning("Adjusted PV data is empty or all zeros, skipping boost calculation")
        return None
    # Only do this after the configured hour
    if dt_util.now().hour < DEFAULT_DONT_BOOST_BEFORE:
        if DEFAULT_DONT_BOOST_BEFORE == 0:
            am_pm_time = "midnight"
        elif DEFAULT_DONT_BOOST_BEFORE < 12:
            am_pm_time = f"{DEFAULT_DONT_BOOST_BEFORE}:00 AM"
        elif DEFAULT_DONT_BOOST_BEFORE == 12:
            am_pm_time = "Noon"
        else:
            am_pm_time = f"{DEFAULT_DONT_BOOST_BEFORE - 12}:00 PM"
        logger.debug("Skipping boost calculation, current hour is before %s", am_pm_time)
        return None

    battery_wh_per_percent = battery_max_wh / 100
    running_soc = 0
    lowest_soc = 0
    starting = 0
    for hour in range(6, 24):
        # Calculate the load for the hour (multiplied by the efficiency factor)
        load = average_hourly_load.get(hour, 1) * 100/efficiency
        pv = adjusted_pv.get(hour, 0)
        # Calculate net power and its contribution to SoC
        ending = min(starting + pv - load, battery_max_wh)
        running_soc = ending / battery_wh_per_percent
        # Track the lowest point of SoC
        lowest_soc = min(lowest_soc, running_soc)
        starting = ending
    # Calculate the required SoC for the grid boost
    soc = -lowest_soc
    # Clamp the required SoC to a maximum of 99%
    required_soc = math.ceil(max(0, min(99, soc + minimum_soc)))


    # Run the numbers with the required soc to verify the calculation
    starting = required_soc * battery_wh_per_percent

    msg: list[str] = []
    msg.append("\n")
    msg.append(
        f"---Verifying required boost starting at {required_soc:.1f}% SOC---"
        )
    msg.append(f"Minimum SoC is {minimum_soc:.1f}%")
    msg.append(
        "\nHour Starting - Load    + PV  = Ending | Battery SoC"
    )
    running_soc = required_soc
    for hour in range(6, 24):
        # Calculate the load for the hour (multiplied by the efficiency factor)
        load = average_hourly_load.get(hour, 1) * 100/efficiency
        pv = adjusted_pv.get(hour, 0)
        # Calculate net power and its contribution to SoC
        ending = min(starting + pv - load, battery_max_wh)
        running_soc = ending / battery_wh_per_percent
        # Update the running SoC, ensuring it does not exceed 100%
        running_soc = min(100, running_soc)

        # Log the calculations for the hour, reporting if we drop below the minimum SoC
        warning = " <<< LOW SoC" if running_soc < minimum_soc else ""
        msg.append(f"{hour:>2}  {round(starting):>8} {round(load):>6}  {round(pv):>6}  {round(ending):>8} |      {round(running_soc):>4}{warning}")
        starting = ending

    msg.append(f"{RESET}")
    logger.info(f"{RESET}\n{PURPLE}".join(msg))

    return required_soc
