# GRIST, the Grid Boost Scheduler for Home Assistant

**GRIST** helps Home Assistant users minimize grid electricity costs by intelligently managing battery charging and solar usage in homes equipped with solar panels and battery storage.

It is designed for systems where the battery can supply most or all of the home's daily electricity needs and where your electicity costs during early morning hours are cheaper than during peak grid use hours (usually the afternoon).

The scheduler automatically determines how much to charge the battery during off-peak hours, aiming to avoid grid usage during expensive peak times. It adapts to changing weather and load conditions using solar forecasts and historical consumption data, and provides manual override options for special circumstances.

**NOTE: Version 1.0.0 only works with batteries that are managed by State of Charge (not voltage).** For the Sol-Ark and Deye inverters, this is called Lithium batteries of Type 00. Subsequent versions may include manage voltage levels instead of state of charge, if that is desired.'

NOTE: Installing this integration and using the mode to either Automatic or Manual will turn On the Time of Use feature in your inverter. If you want to turn that off, you must turn it off through the inverter directly. This does NOT turn off the time of use feature. Why? You may want...

## Features

- **Automatic Grid Boost Calculation:**
  Calculates the required battery charge (SoC) for off-peak charging based on solar forecasts, historical load, and PV performance.
- **Manual Override:**
  Allows users to manually set the grid boost SoC target.
- **PV Forecast Integration:**
  Fetches and automatically adjusts solar production forecasts based on actual PV performance.
- **Historical Data Integration:**
  Tracks and averages load and PV production using Home Assistant sensors in order to optimize calculations as seasonal changes occur or system changes are introduced.
- **Battery and PV Monitoring:**
  Self-adjusts to the addition or removal of battery and PV capacity.
- **Custom Sensors:**
  Exposes calculated values and statistics as Home Assistant sensor entities so you can display key information on your dashboards.
- **Configurable Options:**
  All key options (modes, off-peak start and stophours, SoC targets, forecast update hour, history days, minimum SoC) are configurable via the UI.
- **Extensible Forecast Support:**
  Supports multiple forecast providers:[Solcast]([https://solcast.com](https://github.com/BJReplay/ha-solcast-solar), [Forecast.solar](https://forecast.solar/),and [Meteo](https://github.com/rany2/ha-open-meteo-solar-forecast).
- **Multiple modes:**
  Supports the following modes: *Automatic*, *Manual*, *Testing*, and *Off*. *Automatic* mode manages grid boost daily. *Manual* mode allows you to set a specific boost amount, which could be helpful for days when you know your usage will signficantly differ from your normal patterns of use (or when you know your panels will be covered with snow and produce little power even though the forecast expects sun). *Testing* mode allows you to watch what the system will do, but will not actually change the Time of Use settings of your inverter. *Off* operates in the same ways as *testing* - it is just for peace of mind so you realize it will not affect your inverter.
- **Low overhead:**
  The system is designed to minimize the use of system resources.

## How It Works

Basically the system monitors PV forecasts, and compares forecasts to actual PV performance and actual loads to calculate the optimal state of charge that the battery should have starting at 6:00am.

Sol-Ark (Deye) inverters allow you to set six Time of Use slots where your battery will charge from the grid if the state of charge drops below the set value for that time slot. This integration sets the starting time of the first time slot (defaults to midnight) and sets the inverter state of charge setting for that period based on either the calculated (*automatic*) value, or the value you set for the *manual* mode. The start of the second slot marks the end of the off-peak charging time, and it defaults to 6am.

### Data Collection and Forecasting

- **Solar Forecasts:**
  The integration fetches hourly solar production forecasts from supported APIs. These are updated twice daily; just past midnight local time, and at a configurable hour (default: 22:00 local time).

- **PV History:**
  The component tracks a rollling 21 day history of PV forecasts to compare forecasts to actual performance. This allows for more precise automatic adjustments of forecasts specific to your system, local shading, etc.

### Calculations

- **Required Boost Calculation:**
  Each day, the scheduler compares the adjusted solar forecast for tomorrow with the average load for each hour. It calculates the net deficit (when load exceeds PV) and determines the required battery boost percentage to cover expected shortfalls. This minimum requirement is added to a "buffer" the user sets so that there is always some reserve for those days when extra consumption occurs. This minimum buffer value is clamped between 5% and 99%.

- **Automatic PV Forecast Adjustment:**
  The forecasted PV for tomorrow is adjusted using the ratio of actual to forecast PV from the past 21 days, improving accuracy. This is important if you have shaded conditions during parts of the day, or if you have (for example) some panels facing east and some facing west. Most free teir forecasts do not allow you to specify multiple panel arrays, but the ratio is an elegent solution to account for this situation.

### Sensors Exposed

- **Estimated PV Power:**
  Current estimated PV power output as adjusted based on your system performance.

- **Calculated Grid Boost SoC:**
  Automatically calculated battery charge target for off-peak charging.

- **Actual Grid Boost SoC:**
  Actual grid boost setting applied to the inverter. (If you are

- **Manual Grid Boost SoC:**
  Manually set battery charge target, if override is active.

- **Battery Time Remaining:**
  Estimated hours of battery power remaining at current load.

- **Scheduler Entity:**
  Summarizes the current mode (automatic/manual), boost settings, load history days, and forecast values.

- **Load Entity:**
  Presents the average hourly load over the selected history period.

- **Shading Entity:**
  Shows the calculated shading ratio for each hour, based on PV performance.

- **Battery Life Entity:**
  Estimates the State of Charge for the battery for each hour, based on hourly estimated PV and load averages.

## Configuration

### Initial Setup

1. **Install the Integration:**
   Copy the `grist` folder to your Home Assistant `custom_components` directory. HACS installation will be added in a future release.

2. **Add via Home Assistant UI:**
   Go to *Settings → Devices & Services → Add Integration* and search for "Grid Boost". Install the Grid Boost integration.

3. **Configure Options:**
   Set your preferred boost mode, manual SoC, grid boost start time, update hour, history days, and minimum SoC via the integration options panel.

### Options

- **Boost Mode:**
  Select between automatic, manual, off, or testing. The default is testing.
- **Manual Grid Boost (%):**
  Set the manual grid boost value as a percentage. This is used only when in Manual mode. The default is 50%.
- **Grid Boost Start Time:**
  Set the time to start grid boost. (The default is 00:02 - two minutes past midnight).
- **Update Hour:**
  Set the hour of the day to run the calculations and update the inverter Time of Use setting (0-23, the default hour is 22, which is 10pm local time).
- **Days of Load History:**
  Number of days of load history to use for calculations, a number between 1 and 10. The default value is 4 days. If your weather quickly, you may want to set this shorter. If your weather is more stable, you may want to set it longer. Weekdays and weekend days are treated the same.
- **Minimum State of Charge (%):**
  Set the minimum battery SoC value. This is the buffer so your battery does not run down to 0% state of charge. The default is 20%.

## Notes

As mentioned above, there are six Time of Use slots in a Deye (Sol-Ark) inverter. This integration turns on the Time of Use feature, manages slot 1 start time and state of charge value, and sets the start time of slot 2. (It does not manage the power level used from the grid. The inverter default is the maximum value for your inverter model. You may change this value if you like.)

The inverter requires all slots to be set in order to use the Time of Use feature, and will have default values. You may change the values in slots 2-6 as you desire. Remember that this integration does manage the time value for slot 2. Just be sure to read your inverter documentation before making changes.

The inverter Time of Use feature also allows you to set the days when Grid charging will take place. Unfortunely this is not accessable through Solar Assistant. The inverter should default to turn on all days. You may want to check this.

If you use the other slots, I recommend setting the values to a very low number such as 2-5% so that your battery can use as much of the capacity it has instead of pulling from the grid.

I have chosen a "super saver" rate with my energy provider. This provides very low rates from midnight until 6 am, but very high rates from 4pm until 8pm local time.

Early on when my battery was smaller, I wanted to make sure that I never used grid power from 4-8pm, so I set my 2nd time slot, which starts at 6 am, to 10% state of charge. I then set the 3rd slot to 3pm and set the state of charge to 50%. If I didn't have enought sun to bring the state of charge to 50% by 3pm, the grid would boost it to that level. Then at the 4th slot to start at 4pm and set the state of charge back down to 2%. With my loads, I would never need grid power for the next four hours if I had 50% state of charge!

I have been able to upgrade my battery capacity (if you add another battery, this integration will recognize that through Solar Assistant). I now do not need to worry about any of the Time of Use slots beyond the first slot. I have set all those remaining slots to 4%.

## File Structure

- `__init__.py` – Integration setup and teardown logic
- `config_flow.py` – UI configuration and options flow
- `const.py` – Shared constants and enums
- `coordinator.py` – Update coordinator for polling and data refresh
- `daily_calcs.py` – Daily calculation logic for PV/load/boost
- `entity.py` – Entity base classes and helpers
- `forecast_solar.py`, `solcast.py`, `meteo.py` – Forecast provider modules
- `grist.py` – Main scheduler and calculation logic
- `sensor.py` – Sensor entity definitions
- `services.yaml` – Service definitions
- `strings.json` – UI translation strings

---

## Development Notes

- **Python 3.13+** is required.
- **Solar Assistant** is required. (Solar Assistant provides sensor data for actual PV data as well as manages Time of Use settings for the inverter.)
- **Sol-Ark Inverter**. This has only been tested with a Sol-Ark 12K2P inverter. While it would not be hard to modify for other inverters, the current version is only tested with a single Sol-Ark 12K2P inverter.
- Code is formatted with Ruff and linted with PyLint/MyPy.
- All I/O is async; no blocking calls.
- Follows Home Assistant's update coordinator and config flow patterns.
- Constants are centralized in `const.py` for maintainability.
- All sensors use unique IDs for state persistence. These are also maintained via const.py.

---

## Contributing

Contributions are welcome! Please follow the code style and patterns used in this repository. See `.github/copilot-instructions.md` for detailed coding standards.

---

## License

This project is licensed under the terms of the GNU GENERAL PUBLIC LICENSE. See `LICENSE` for details.
