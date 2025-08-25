# Developer notes for GRIST, the Grid Boost Scheduler

The **Grid Boost Scheduler** custom component helps Home Assistant users minimize grid electricity costs by intelligently managing battery charging and solar usage in homes equipped with solar panels and battery storage. It is designed for systems where the battery can supply most or all of the home's daily electricity needs. The scheduler automatically determines how much to charge the battery during off-peak hours, aiming to avoid grid usage during expensive peak times. It adapts to changing weather and load conditions using solar forecasts and historical consumption data, and provides manual override options for special circumstances.

---

## Quality Scale Rules

## Bronze
- action-setup:
    This integration does not expose any user-triggerable actions; all actions are handled internally based on configuration options.

- brands: todo

- common-modules: I have functions that are similar to the build-in functions, but provide error checking and default values. The prevents the need to duplicate error checking when those functions are used in different places in my code. For example, I have a helper function called get_state which returns the state of an entity (as opposed to the entity with the associated state, attributes, etc.). If the entity is not present or fails in some way, this helper function manages those error conditions.

- config-flow: done

- config-flow-test-coverage: todo (having trouble getting pytest to run in my docker instance. Will have to try again with a new instance.)

- dependency-transparency: This integration is dependant upon the home assistant statistics recorder as well as MQTT integration. It further depends upon Solar Assistant, an external hardware/software system to supply sensor information necessary for this integration. Also required is one of three other integrations to supply solar forcast information: Solcast, Meteo or Forecast.Solar. See the documentation for details.

- docs-actions: This integration does not expose any user-triggerable actions; all actions are handled internally based on configuration options.

  - docs-high-level-description: done

  - docs-installation-instructions:
  todo

  - docs-removal-instructions:
  todo

  - entity-event-setup: n/a (The integration does gather information from recorder statistics and from other sensor data, but it does not listen for events.)

  - entity-unique-id: done

  - has-entity-name: done

  - runtime-data:
  todo

  - test-before-configure:
  todo

  - test-before-setup:
  todo

  - unique-config-entry:
  todo


  # Silver
  action-exceptions: todo
  config-entry-unloading: todo
  docs-configuration-parameters: todo
  docs-installation-parameters: todo
  entity-unavailable: todo
  integration-owner: todo
  log-when-unavailable: todo
  parallel-updates: todo
  reauthentication-flow: todo
  test-coverage: todo

  # Gold
  devices: todo
  diagnostics: todo
  discovery-update-info: todo
  discovery: todo
  docs-data-update: todo
  docs-examples: todo
  docs-known-limitations: todo
  docs-supported-devices: todo
  docs-supported-functions: todo
  docs-troubleshooting: todo
  docs-use-cases: todo
  dynamic-devices: todo
  entity-category: todo
  entity-device-class: todo
  entity-disabled-by-default: todo
  entity-translations: todo
  exception-translations: todo
  icon-translations: todo
  reconfiguration-flow: todo
  repair-issues: todo
  stale-devices: todo

  # Platinum
  async-dependency: todo
  inject-websession: todo
  strict-typing: todo
