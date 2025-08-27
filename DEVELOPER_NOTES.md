# Developer notes for GRIST, the Grid Boost Scheduler

The **Grid Boost Scheduler** custom component helps Home Assistant users minimize grid electricity costs by intelligently managing battery charging and solar usage in homes equipped with solar panels and battery storage. It is designed for systems where the battery can supply most or all of the home's daily electricity needs. The scheduler automatically determines how much to charge the battery during off-peak hours, aiming to avoid grid usage during expensive peak times. It adapts to changing weather and load conditions using solar forecasts and historical consumption data, and provides manual override options for special circumstances.

---

## Quality Scale Rules

## Bronze

- **action-setup**:
 This integration does not expose any user-triggerable actions; all actions are handled internally based on configuration options.

- **brands**: *todo*

- **common-modules**: I have functions that are similar to the build-in functions, but provide error checking and default values. The prevents the need to duplicate error checking when those functions are used in different places in my code. For example, I have a helper function called get_state which returns the state of an entity (as opposed to the entity with the associated state, attributes, etc.). If the entity is not present or fails in some way, this helper function manages those error conditions.

- **config-flow**: done

- **config-flow-test-coverage**: *todo* (having trouble getting pytest to run in my docker instance. Will have to try again with a new instance.)

- **dependency-transparency**: This integration is dependant upon the home assistant statistics recorder as well as MQTT integration. It further depends upon Solar Assistant, an external hardware/software system to supply sensor information necessary for this integration. Also required is one of three other integrations to supply solar forcast information**: Solcast, Meteo or Forecast.Solar. See the documentation for details.

- **docs-actions**: This integration does not expose any user-triggerable actions; all actions are handled internally based on configuration options.

- **docs-high-level-description**: done

- **docs-installation-instructions**: *todo*

- **docs-removal-instructions**: *todo*

- **entity-event-setup**: n/a (The integration does gather information from recorder statistics and from other sensor data, but it does not listen for events.)

- **entity-unique-id**: done

- **has-entity-name**: done

- **runtime-data**: The integration stores forecast data in the hass storage using the keys found in constants as FORECAST_KEY, and STORAGE_VERSION. Of course hass also stores integration information and options during the initialization and config_flow_options routines.

- **test-before-configure**: The integration supplies default values for all items that can be configured. This ensures that the integration will behave correctly before it is configured. In addition, the integration tests for the presense of a valid solar forcaster prior to running any function, method or calculation that depends on data from a forecaster.

- **test-before-setup**: See test-before-configure.

- **unique-config-entry**: This entity is a singe-instance integration and follows the idiomatic and correct method to ensure that. Testing is incorporated. **But I am still waiting to figure out how to run pytest for home assistant within docker.**

## Silver

- **action-exceptions**: n/a. No exposed actions.
- **config-entry-unloading**: Unloading is done. Since there are no listeners, no further checks are needed. Testing is incorporated. **But I am still waiting to figure out how to run pytest for home assistant within docker.**
- **docs-configuration-parameters**: *todo*
- What:
Document all configuration parameters (options, YAML, UI) your integration supports.

How:

Add a section to your README or documentation listing all configuration options, their types, defaults, and effects.

- **docs-installation-parameters**: *todo*
- What:
Document any parameters or requirements for installation (e.g., required integrations, hardware, permissions).

How:

Add a section to your README or documentation explaining what is needed before installation and any parameters that must be set.

- **entity-unavailable**: *todo*
- What:
Entities must correctly report when they are unavailable (e.g., due to lost connection or missing data).

How:

Implement the available property for your entities.
Add tests that simulate unavailable conditions and assert that available is False and the entity state is handled as expected.

- **integration-owner**: Done
- **log-when-unavailable**: *todo*
- What:
Log a debug or warning message when an entity becomes unavailable.

How:

In your entity code, log when available changes to False.
Add a test that simulates this and checks for the log message.

- **parallel-updates**: *todo*
What:
If your integration updates multiple entities, use parallel updates to avoid blocking.

How:

Use the PLATFORM_PARALLEL_UPDATES constant or implement async update patterns.
Add a test to ensure updates are not blocking.

- **reauthentication-flow**: n/a. This integration does not rely on authentication as all api calls are managed by other integrations (and currently do not require authentication).
-
- **test-coverage**: *todo*
What:
Your tests must cover all critical code paths, including error handling, setup, unloading, and unavailable states.

How:

Add or expand tests to cover all the above scenarios.
Use pytest coverage tools to measure and report coverage.

## Gold

- **devices**: *todo*
- **diagnostics**: *todo*
- **discovery-update-info**: *todo*
- **discovery**: *todo*
- **docs-data-update**: *todo*
- **docs-examples**: *todo*
- **docs-known-limitations**: *todo*
- **docs-supported-devices**: *todo*
- **docs-supported-functions**: *todo*
- **docs-troubleshooting**: *todo*
- **docs-use-cases**: *todo*
- **dynamic-devices**: *todo*
- **entity-category**: *todo*
- **entity-device-class**: *todo*
- **entity-disabled-by-default**: *todo*
- **entity-translations**: *todo*
- **exception-translations**: *todo*
- **icon-translations**: *todo*
- **reconfiguration-flow**: *todo*
- **repair-issues**: *todo*
- **stale-devices**: *todo*

## Platinum

- **async-dependency**: *todo*
- **inject-websession**: *todo*
- **strict-typing**: *todo*
