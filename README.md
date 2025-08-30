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

Solar Assistant, a Raspberry Pi based tool to monitory your solar system, provides both the data to this integration as well as a means to control the inverter settings. (Earlier verions of this integration used data from the deye (and later solark) cloud servers, however that proved signficantly less reliable.)

I have found that the performance of my solar panels varies from season to season and year to year. Panels will slowly degrade. Some years have more dust on the panels than other years. During the spring my panels have more morning shade than during the summer. All these changing factors affect performance and how much power I need from the grids. This integration takes those changes into account and adjusts grid boost based on those changes!

### Data Collection and Forecasting

- **Solar Forecasts:**
  GRIST fetches hourly solar production forecasts from supported APIs. These are updated twice daily; just past midnight local time, and at a configurable hour (default: 22:00 local time).

- **PV History:**
  GRIST tracks a rollling 21 day history of PV forecasts to compare forecasts to actual performance. This allows for more precise automatic adjustments of forecasts specific to your system, local shading, etc.

  **Load History**
  GRIST monitors recent load usage for each hour of the day, computing averages for each hour so that it can calculate how your battery will likely perform through the coming day given the forecast for solar power and the actual recent performance of your panels.

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

**Prerequisites:**
  To use the integration, you must have:

- a Sol-Ark (or Deye based) inverter,
- an LFP (Lithium Iron Phosphate, or LiFePo4) battery that is able to report it's state of charge to the inverter, and
- Solar Assistant monitoring your inverter and batteries and reporting real-time data to your instance of Home Assistant

In addition you must install one of three solar forecaster tools:

- [Solcast]([https://solcast.com](https://github.com/BJReplay/ha-solcast-solar)
- [Forecast.solar](https://forecast.solar/)
- [Meteo](https://github.com/rany2/ha-open-meteo-solar-forecast)

(If you install more than one, they will be selected in the order presented above.)

I use the Solcast tool because I like the unique feature it offers of allowing you to decide how pessimistic (or optimistic) you want the forecast to be. Solcast give a 10 percentile forecast (worst case), a 50 percentile forecast (most likely) and a 90% forecast (best case). When heavy but intermitted clouds are forecast, the spread between 10 and 90 percentile can be quite large. GRIST extrapolates those forecasts so you can choose any percentile you want between 10 and 90. Since I am optimizing to avoid using the grid after 6am, I normally use a 25 percentile figure. (I'm not TOTALLY pessimistic!!!)

**Install the Integration:**
   TODO: HACS installation instructions and link to page

**Configure Options:**
   Set your preferred options via the integration options panel. For the system to actually control the inverter and set your early morning grid boost level, you must set the integration into *Automatic* mode.

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

## Removal

To remove GRIST, Go to Settings/Devices & Services/GRIST. Using the three vertical dots next to CONFIGURE, select DELETE from the drop down menu. If you want to turn off the Time of Use feature on your inverter, you should first click on the CONFIGURE button and set the Boost Mode to Off. You will need to confirm that choice, continue on to the details form, and Save. This will turn off the Time of Use mode through Solar Assistant. You can then remove GRIST.

## Notes

As mentioned above, there are six Time of Use slots in a Deye (Sol-Ark) inverter. GRIST turns on the Time of Use feature, manages slot 1 start time and state of charge value, and sets the start time of slot 2. (It does not manage the power level used from the grid. The inverter default is the maximum value for your inverter model. You may change this value if you like.)

The inverter requires all slots to be set in order to use the Time of Use feature, and will have default values. You may change the values in slots 3-6 as you desire. Remember that this integration does manage the time value for slot 2. Be sure to read your inverter documentation before making changes.

The inverter Time of Use feature allows you to set the days when Grid charging will take place. This is not accessable through Solar Assistant. The inverter will default to turn on all days. (GRIST is designed with the assumption that charging will happen every day.)

If you use the other slots, I recommend setting the values to a very low number such as 2-5% so that your battery can use as much of the capacity it has instead of pulling from the grid.

TIP: Early on I had a pretty small solar panel array. There were days when I couldn't charge my battery enough before my peak electricity rates (4-8pm). I wanted to make sure that I never used grid power from 4-8pm. While I set slots 2,4,5 and 6 to 4%, I set the 3rd slot start one hour before the peak rate hour and boost, if neccesary, the battery to 45% by 4pm. This ensured that I always had enough power to get me through my peak-cost grid energy period by running only on my battery.

## File Structure

- `__init__.py` – Integration setup and teardown logic
- `config_flow.py` – UI configuration and options flow
- `const.py` – Shared constants and enums
- `coordinator.py` – Update coordinator for polling and data refresh
- `daily_calcs.py` – Daily calculation logic for PV/load/boost
- `entity.py` – Entity base classes and helpers
- forecasters/`forecast_solar.py`, `solcast.py`, `meteo.py` – Forecast provider modules
- `grist.py` – Main scheduler and calculation logic
- `sensor.py` – Sensor entity definitions
- `services.yaml` – Service definitions
- translations/`en.json` – UI translation strings

## Contributing

Contributions are welcome! Please follow the code style and patterns used in this repository. (I strive to follow best practices used within the Home Assistant community.)

## License

This project is licensed under the terms of the GNU GENERAL PUBLIC LICENSE. See `LICENSE` for details.
