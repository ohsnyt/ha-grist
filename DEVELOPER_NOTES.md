# Developer notes for GRIST, the Grid Boost Scheduler

The **GRIST Scheduler** custom component helps Home Assistant users minimize grid electricity costs by intelligently managing battery charging and solar usage in homes equipped with solar panels and battery storage. It is designed for systems where the battery can supply most or all of the home's daily electricity needs. The scheduler automatically determines how much to charge the battery during off-peak hours, aiming to avoid grid usage during expensive peak times. It adapts to changing weather and load conditions using solar forecasts and historical consumption data, and provides manual override options for special circumstances.

## Notes

  **Solar Assistant** is required. (Solar Assistant provides sensor data for actual PV data as well as manages Time of Use settings for the inverter.)

  **Sol-Ark Inverter**. This has only been tested with a Sol-Ark 12K2P inverter. I assume it will work with any Deye based inverter. *I invite your feedback, both positive and negative.*
- Code is formatted with Ruff and linted with PyLint/MyPy.
- All I/O is async; no blocking calls.
- Follows Home Assistant's update coordinator and config flow patterns.
- Constants are centralized in `const.py` for maintainability.
- All sensors use unique IDs for state persistence. These are also maintained via const.py.

## Quality Scale Rules

### Bronze

**action-setup**: Done. This integration does not expose anyuser-triggerable actions; all actions are handled internally based onconfiguration options.

**brands**: *todo*

**common-modules**: Done. I have functions that are similar to thebuild-in functions, but provide error checking and default values. Theprevents the need to duplicate error checking when those functions areused in different places in my code. For example, I have a helperfunction called get_state which returns the state of an entity (asopposed to the entity with the associated state, attributes, etc.). Ifthe entity is not present or fails in some way, this helper functionmanages those error conditions.

**config-flow**: Done. Options are set through a series of formsdesigned to make setup as easy as possible (given the limitations onHome Assistant forms).

**config-flow-test-coverage**: *todo* (having trouble getting pytestto run in my docker instance. Will have to try again with a newinstance.)

**dependency-transparency**: Done. This integration is dependant uponthe home assistant statistics recorder as well as MQTT integration. Itfurther depends upon Solar Assistant, an external hardware/softwaresystem to supply sensor information necessary for this integration.Also required is one of three other integrations to supply solarforcast information**: Solcast, Meteo or Forecast.Solar. See thedocumentation for details.

**docs-actions**: Done. This integration does not expose anyuser-triggerable actions; all actions are handled internally based onconfiguration options.

**docs-high-level-description**: Done.

**docs-installation-instructions**: *todo*

**docs-removal-instructions**: Done.

**entity-event-setup**: n/a (The integration does gather information from recorder statistics and from other sensor data, but it does not listen for events beyond listening for the initial start of Home Assistant. The intigration delays startup until Home Assistant has completed the startup of all components. This ensures that your desired forecaster is loaded.)

**entity-unique-id**: Done.

**has-entity-name**: Done.

**runtime-data**: Done. The integration stores forecast data in the hass storage using the keys found in constants as FORECAST_KEY, and STORAGE_VERSION. Of course hass also stores integration information and options during the initialization and config_flow_options routines.

**test-before-configure**: Done. The integration supplies default values for all items that can be configured. This ensures that the integration will behave correctly before it is configured. In addition, the integration tests for the presense of a valid solar forcaster prior to running any function, method or calculation that depends on data from a forecaster.

**test-before-setup**: Done. See test-before-configure.

**unique-config-entry**: Done. This entity is a singe-instance integration and follows the idiomatic and correct method to ensure that. Testing is incorporated. **But I am still waiting to figure out how to run pytest for home assistant within docker.**

## Silver

**action-exceptions**: n/a. No exposed actions.

**config-entry-unloading**: Done. Unloading is done. Since there are no listeners, no further checks are needed. Testing is incorporated. *But I am still waiting to figure out how to run pytest for home assistant within docker.*

**docs-configuration-parameters**: Done.

**docs-installation-parameters**: Mostly Done. (Need HACS instructions.)

**entity-unavailable**: Done.  Double check if I uninstall the forecaster.
- What:
Entities must correctly report when they are unavailable (e.g., due to lost connection or missing data).

**integration-owner**: Done.

**log-when-unavailable**: VERIFY
- What:
Log a debug or warning message when an entity becomes unavailable.

How:

In your entity code, log when available changes to False.
Add a test that simulates this and checks for the log message.

**parallel-updates**: n/a

**reauthentication-flow**: n/a. This integration does not rely on authentication. All external api calls are managed by the forecast integrations, and those integrations are currently designed so they do not require authentication.

**test-coverage**: *todo*
What:
Your tests must cover all critical code paths, including error handling, setup, unloading, and unavailable states.

How:

Add or expand tests to cover all the above scenarios.
Use pytest coverage tools to measure and report coverage.

## Gold

**devices**: *todo*
**diagnostics**: *todo*
**discovery-update-info**: *todo*
**discovery**: *todo*
**docs-data-update**: *todo*
**docs-examples**: *todo*
**docs-known-limitations**: *todo*
**docs-supported-devices**: *todo*
**docs-supported-functions**: *todo*
**docs-troubleshooting**: *todo*
**docs-use-cases**: *todo*
**dynamic-devices**: *todo*
**entity-category**: *todo*
**entity-device-class**: *todo*
**entity-disabled-by-default**: *todo*
**entity-translations**: *todo*
**exception-translations**: *todo*
**icon-translations**: *todo*
**reconfiguration-flow**: *todo*
**repair-issues**: *todo*
**stale-devices**: *todo*

## Platinum

**async-dependency**: *todo*
**inject-websession**: *todo*
**strict-typing**: *todo*
