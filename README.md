# vaillant-component

**Please note that this component is still in beta test, so I may do (unwanted) breaking changes.**

Ideas are welcome ! Don't hesitate to create issue to suggest something, it will be really appreciated.

Please download the `vaillant` folder and put it inside your `custom_components` folder.

You can configure it through the UI using integration.
You have to provided your username and password (same as multimatic app)

**It is strongly recommended to use a dedicated user for HA**, for 2 reasons:
- As usual for security reason, if your HA is compromised somehow, you know which user to block
- I cannot strongly confirm it, but it seems vaillant API only accept the same user to be connected at the same time


## Releases
### [1.0.0](https://github.com/thomasgermain/vaillant-component/releases/tag/1.0.0)
First release using config flow
### [1.1.0](https://github.com/thomasgermain/vaillant-component/releases/tag/1.1.0)
- Move everything to async
- Bugfix for circulation (no considered `on` when hot water boost was activated)
- Removed boiler temperature and boiler water pressure in favor of `report` entity (breaking change)
- Better error handling
- Automatic re-authentication in case of error
### [1.2.0](https://github.com/thomasgermain/vaillant-component/releases/tag/1.2.0)
- Adding a way to specify serial number in case you have multiple
- some error log improvement/fix
- adding some none check
### [1.2.1](https://github.com/thomasgermain/vaillant-component/releases/tag/1.2.1)
- warning log fix
### [1.2.2](https://github.com/thomasgermain/vaillant-component/releases/tag/1.2.2)
- Better error handling
- Component does a reconnection every time an error occurs
### [1.2.3](https://github.com/thomasgermain/vaillant-component/releases/tag/1.2.3)
- Adapt to HA 0.110 deprecation/warning
- Add some None-check in case of error when component is starting
- Fix issue with `set_holiday_mode` (ValueError: unconverted data remains: T00:00:00.000Z)
### [1.3.0](https://github.com/thomasgermain/vaillant-component/releases/tag/1.3.0)
- `request hvac update` is not done by the component automatically. Instead, there is a new service `request_hvac_update`. 
If you have any issue with refresh time of the data, you can use an automation to call the service. **I recommend to do it very 1 hour**. If you really hove data refresh issue, you can do down until every 30min. Doing it more often will likely end up in an error at vaillant API. 
You can use something like this as automation:
```yaml
- id: "Refresh vaillant data"
  alias: "Refresh vaillant data"
  trigger:
    - platform: time_pattern
      hours: "/1"
  action:
    - service: vaillant.request_hvac_update
```
### [1.3.1](https://github.com/thomasgermain/vaillant-component/releases/tag/1.3.1)
- check if a zone is enabled before creating a climate entity.
### [1.3.2](https://github.com/thomasgermain/vaillant-component/releases/tag/1.3.2)
- Fix the way the dynamic errors (coming from the API) are refreshed in order to have entities created/removed dynamically without restarting HA

### [1.4.0](https://github.com/thomasgermain/vaillant-component/releases/tag/1.4.0)
- Supporting cooling
- **BREAKING CHANGES** on vaillant mode <> hvac mode & preset mode, please see `Expected behavior` below

### [1.4.1b1](https://github.com/thomasgermain/vaillant-component/releases/tag/1.4.1b1)
- Allow integration to be added multiple times by adding serial number to device_info identifiers and entity_id, when serial number is specified.


## Provided entities
- 1 water_heater entity, if any water heater: `water_heater.vaillant_<water heater id>`, basically `water_heater.vaillant_control_dhw`
- 1 climate entity per zone (expect if the zone is controlled by room) `climate.vaillant_<zone id>`
- 1 climate entity per room `climate.vaillant_<room name>`
- 1 binary_sensor entity `binary_sensor.vaillant_control_dhw` reflecting if the circulation is on or off
- 1 binary_sensor entity `climate.vaillant_<room name>_window` per room reflecting the state of the "open window" in a room (this is a feature of the vaillant API, if the temperature is going down pretty fast, the API assumes there is an open window and heating stops)
- 1 binary_sensor entity `climate.vaillant_<sgtin>_lock`per device reflecting if valves are "child locked" or not
- 1 binary_sensor entity `binary_sensor.vaillant_<sgtin>_battery` reflecting battery level for each device (VR50, VR51) in the system
- 1 binary_sensor entity `binary_sensor.vaillant_<sgtin>_battery` reflecting connectivity for each device (VR50, VR51) in the system
- 1 binary_sensor entity `binary_sensor.vaillant_system_update`to know if there is an update pending
- 1 binary_sensor entity `binary_sensor.vaillant_system_online` to know if the vr900/920 is connected to the internet
- 1 binary_sensor entity `binary_sensor.vaillant_<boiler model>` to know if there is an error at the boiler. **Some boiler does not provide this information, so entity won't be available.**
- 1 temperature sensor `sensor.vaillant_outdoor_temperature` for outdoor temperature
- 1 sensor for each report in live_report (boiler temperature, boiler water pressure, etc.)
- 1 binary sensor `binary_sensor.vaillant_quick_mode` to know a quick mode is running on
- 1 binary sensor ` binary_sensor.vaillant_holiday` to know the holiday mode is on/off
- dynamic binary sensors if there are extra errors coming from the api.

## Provided devices
- 1 device per VR50 or VR51
- 1 device for the boiler (if supported). Some boiler don't provide enough information to be able to create a device in HA.
- 1 device for the gateway (like VR920)
- 1 "multimatic" (VRC700) device (the water pressure is linked to the VRC 700 inside the vaillant API)
- hot water circuit
- heating circuit


For the climate and water heater entities, you can also found 
- the 'real vaillant mode' running on (AUTO, MANUAL, DAY, etc)

For the boiler error entity, you can also found 
- the last update (this is not the last HA update, this is the last time vaillant checks the boiler)
- the status code (these can be found in your documentation)
- the title (human readable description of the status code)

For the `binary_sensor.vaillant_quick_mode`, when on, you have the current quick mode name is available
For the `binary_sensor.vaillant_holiday`, when on, you have the start date, end date and temperature

## Provided services
- `vaillant.set_holiday_mode` to set the holiday mode (see services in HA ui to get the params)
- `vaillant.remove_holiday_mode` .. I guess you get it
- `vaillant.set_quick_mode` to set a quick mode
- `vaillant.remove_quick_mode` don't tell me you don't get it 
- `vaillant.set_quick_veto` to set a quick veto for a climate entity
- `vaillant.remove_quick_veto` to remove a quick veto for a climate entity
- `vaillant.request_hvac_update` to tell vaillant API to fetch data from your installation and made them available in the API

This will allow you to create some buttons in UI to activate/deactivate quick mode or holiday mode with a single click


## Expected behavior

On **room** climate:

Changing temperature while ...
- `MANUAL` mode -> it simply changes target temperature
- other modes -> it creates a quick_veto (duration = 3 hours) (it's also removing holiday or quick mode)

Modes mapping:
- `AUTO` -> `HVAC_MODE_AUTO` & `PRESET_COMFORT`
- `OFF` -> `HVAC_MODE_OFF` & no preset
- `QUICK_VETO` -> no hvac & `PRESET_QUICK_VETO` (custom)
- `QM_SYSTEM_OFF` -> `HVAC_MODE_OFF` & `PRESET_SYSTEM_OFF` (custom)
- `HOLIDAY` -> `HVAC_MODE_OFF` & `PRESET_HOLIDAY` (custom)
- `MANUAL` -> no hvac & `PRESET_MANUAL` (custom)

On **zone** climate:
- Changing temperature will lead to a quick veto with selected temperature for 6 hours (quick veto duration is not configurable for a zone)

Modes mapping:
- `AUTO` -> `HVAC_MODE_AUTO` & `PRESET_COMFORT`
- `DAY`: no hvac & `PRESET_DAY` (custom)
- `NIGHT`: no hvac & `PRESET_SLEEP`
- `OFF` -> `HVAC_MODE_OFF` & no preset
- `ON` (= cooling ON) -> no hvac & `PRESET_COOLING_ON` (custom)
- `QUICK_VETO` -> no hvac & `PRESET_QUICK_VETO` (custom)
- `QM_ONE_DAY_AT_HOME` -> HVAC_MODE_AUTO & `PRESET_HOME`
- `QM_PARTY` -> no hvac & `PRESET_PARTY` (custom)
- `QM_VENTILATION_BOOST` -> `HVAC_MODE_FAN_ONLY` & no preset
- `QM_ONE_DAY_AWAY` -> `HVAC_MODE_OFF` & `PRESET_AWAY`
- `QM_SYSTEM_OFF` -> `HVAC_MODE_OFF` & `PRESET_SYSTEM_OFF` (custom)
- `HOLIDAY` -> `HVAC_MODE_OFF` & `PRESET_HOLIDAY` (custom)
- `QM_COOLING_FOR_X_DAYS` -> no hvac & `PRESET_COOLING_FOR_X_DAYS`

