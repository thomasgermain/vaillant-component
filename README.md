[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/thomasgermain/vaillant-component?style=for-the-badge)

# Multimatic integration

**Please note that this integration is still in beta test, so I may do (unwanted) breaking changes.**

Ideas are welcome ! Don't hesitate to create issue to suggest something, it will be really appreciated.

**This integration is also compatible with sensoAPP and has been tested with the vr920 and vr921 devices.**

## Installations

- Through HACS [custom repositories](https://hacs.xyz/docs/faq/custom_repositories/) !
- Otherwise, download the zip from the latest release and copy `multimatic` folder and put it inside
  your `custom_components` folder.

You can configure it through the UI using integration.
You have to provide your username and password (same as multimatic or senso app), if you have multiple serial numbers,
you can choose for which number serial number you want the integration.
You can create multiple instance of the integration with different serial number (**This is still a beta feature**).

**It is strongly recommended using a dedicated user for HA**, for 2 reasons:

- As usual for security reason, if your HA got compromised somehow, you know which user to block
- I cannot confirm it, but it seems multimatic and senso API only accept the same user to be connected at the same time

## Changelog

See [releases details](https://github.com/thomasgermain/vaillant-component/releases)

## Provided entities

- 1 water_heater entity, if any water heater: `water_heater.<water heater id>`, basically `water_heater.control_dhw`
- 1 climate entity per zone (expect if the zone is controlled by room) `climate.<zone id>`
- 1 climate entity per room `climate.<room name>`
- 1 fan entity `fan.<ventilation_id>`
- 1 binary_sensor entity `binary_sensor.control_dhw` reflecting if the circulation is on or off
- 1 binary_sensor entity `climate.<room name>_window` per room reflecting the state of the "open window" in a room (this
  is a feature of the multimatic API, if the temperature is going down pretty fast, the API assumes there is an open
  window and heating stops)
- 1 binary_sensor entity `climate.<sgtin>_lock`per device reflecting if valves are "child locked" or not
- 1 binary_sensor entity `binary_sensor.<sgtin>_battery` reflecting battery level for each device (VR50, VR51) in the
  system
- 1 binary_sensor entity `binary_sensor.<sgtin>_battery` reflecting connectivity for each device (VR50, VR51) in the
  system
- 1 binary_sensor entity `binary_sensor.multimtic_system_update`to know if there is an update pending
- 1 binary_sensor entity `binary_sensor.multimtic_system_online` to know if the vr900/920 is connected to the internet
- 1 binary_sensor entity `binary_sensor.<boiler model>` to know if there is an error at the boiler. **Some boiler does
  not provide this information, so entity won't be available.**
- 1 temperature sensor `sensor.outdoor_temperature` for outdoor temperature
- 1 sensor for each report in live_report (boiler temperature, boiler water pressure, etc.)
- 1 binary sensor `binary_sensor.multimtic_quick_mode` to know a quick mode is running on
- 1 binary sensor ` binary_sensor.multimtic_holiday` to know the holiday mode is on/off
- 1 binary sensor `binary_sensor.multimatic_errors`indicating if there are errors coming from the API (if `on`, details
  are in `state_attributes`)

## Provided devices

- 1 device per VR50 or VR51
- 1 device for the boiler (if supported). Some boilers don't provide enough information to be able to create a device in
  HA.
- 1 device for the gateway (like VR920)
- 1 "multimatic" (VRC700) device (the water pressure is linked to the VRC 700 inside the multimatic API)
- hot water circuit
- heating circuit

For the climate and water heater entities, you can also find

- the 'real multimatic mode' running on (AUTO, MANUAL, DAY, etc)

For the boiler error entity, you can also find

- the last update (this is not the last HA update, this is the last time multimatic checks the boiler)
- the status code (these can be found in your documentation)
- the title (human-readable description of the status code)

For the `binary_sensor.multimtic_quick_mode`, when on, you have the current quick mode name is available
For the `binary_sensor.multimtic_holiday`, when on, you have the start date, end date and target temperature

## Provided services

- `multimatic.set_holiday_mode` to set the holiday mode (see services in HA ui to get the params)
- `multimatic.remove_holiday_mode` .. I guess you get it
- `multimatic.set_quick_mode` to set a quick mode
- `multimatic.remove_quick_mode` don't tell me you don't get it
- `multimatic.set_quick_veto` to set a quick veto for a climate entity
- `multimatic.remove_quick_veto` to remove a quick veto for a climate entity
- `multimatic.request_hvac_update` to tell multimatic API to fetch data from your installation and made them available
  in the API
- `multimatic.set_ventilation_day_level` to set ventilation day level
- `multimatic.set_ventilation_night_level` to set ventilation night level
- `multimatic.set_datetime` to set the current date time of the system

This will allow you to create some buttons in UI to activate/deactivate quick mode or holiday mode with a single click

## Expected behavior

### Room climate

#### Changing temperature

- `MANUAL` mode -> it simply changes target temperature
- other modes -> it creates a quick_veto (duration = 3 hours) and it removes holiday or quick mode.

#### Modes mapping

| Multimatic mode         | HA HVAC          | HA preset                  |
|-------------------------|------------------|----------------------------|
| AUTO                    | AUTO             | COMFORT                    |
| OFF                     | OFF              | /                          |
| QUICK_VETO              | Depends on state | PRESET_QUICK_VETO (custom) |
| SYSTEM_OFF (quick mode) | OFF              | PRESET_SYSTEM_OFF (custom) |
| HOLIDAY (quick mode)    | OFF              | PRESET_AWAY                |
| MANUAL                  | Depends on state | PRESET_HOME                |

#### Available HVAC mode

| HVAC mode | Multimatic mode |
|-----------|-----------------|
| AUTO      | AUTO            |
| OFF       | OFF             |

#### Available preset mode

| preset mode    | Multimatic mode |
|----------------|-----------------|
| PRESET_COMFORT | AUTO            |
| PRESET_HOME    | MANUAL          |

### Zone climate

#### Changing temperature

Changing temperature will lead to a quick veto with selected temperature for 6 hours (quick veto duration is not
configurable for a zone)

#### Modes mapping

| Vaillant Mode                   | HA HVAC          | HA preset                  |
|---------------------------------|------------------|----------------------------|
| AUTO / TIMED CONTROLLED         | AUTO             | PRESET_COMFORT             |
| DAY                             | Depends on state | PRESET_HOME                |
| NIGHT                           | Depends on state | PRESET_SLEEP               |
| MANUAL (= cooling)              | Depends on state | PRESET_COOLING_ON          |
| OFF                             | OFF              | /                          |
| ON (= cooling ON)               | Depends on state | PRESET_COOLING_ON (custom) |
| QUICK_VETO                      | Depends on state | PRESET_QUICK_VETO (custom) |
| ONE_DAY_AT_HOME (quick mode)    | AUTO             | PRESET_HOME                |
| PARTY (quick mode)              | OFF              | PRESET_HOME                |
| VENTILATION_BOOST (quick mode)  | FAN_ONLY         | /                          | 
| ONE_DAY_AWAY (quick mode)       | OFF              | PRESET_AWAY                |
| SYSTEM_OFF (quick mode)         | OFF              | PRESET_SYSTEM_OFF (custom) |
| HOLIDAY (quick mode)            | OFF              | PRESET_AWAY                |
| COOLING_FOR_X_DAYS (quick mode) | COOL             | /                          |

#### Available HVAC mode

| HVAC mode | Multimatic mode                 |
|-----------|---------------------------------|
| AUTO      | AUTO                            |
| OFF       | OFF                             |
| FAN_ONLY  | VENTILATION_BOOST (quick mode)  |
| COOL      | COOLING_FOR_X_DAYS (quick mode) |

#### Available preset mode

| preset mode    | Multimatic mode              |
|----------------|------------------------------|
| PRESET_COMFORT | AUTO                         |
| PRESET_HOME    | ONE_DAY_AT_HOME (quick mode) |
| PRESET_AWAY    | ONE_DAY_AWWAY (quick mode)   |

### DHW climate

| Vaillant Mode               | HA HVAC | HA preset         |
|-----------------------------|---------|-------------------|
| AUTO                        | AUTO    | PRESET_COMFORT    |
| OFF                         | OFF     | PRESET_NONE       |
| HOLIDAY (quick mode)        | OFF     | PRESET_AWAY       |
| ONE_DAY_AWAY (quick mode)   | OFF     | PRESET_AWAY       |
| SYSTEM_OFF (quick mode)     | OFF     | PRESET_SYSTEM_OFF |
| HOTWATER_BOOST (quick mode) | HEAT    | PRESET_BOOST      |
| PARTY (quick mode)          | OFF     | PRESET_HOME       |
| ON                          | EAT     | PRESET_NONE       |

#### Available HVAC mode

| HVAC mode | Multimatic mode |
|-----------|-----------------|
| AUTO      | AUTO            |
| OFF       | OFF             |
| HEAT      | ON              |

#### Available preset mode

| preset mode    | Multimatic mode             |
|----------------|-----------------------------|
| PRESET_COMFORT | AUTO                        |
| PRESET_BOOST   | HOTWATER_BOOST (quick mode) |

---
<a href="https://www.buymeacoffee.com/tgermain" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: auto !important;width: auto !important;" ></a>
