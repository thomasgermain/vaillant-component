"""multimatic integration constants."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "multimatic"
ENTITIES = "entities"

# list of platforms into entity are created
PLATFORMS = ["binary_sensor", "sensor", "water_heater", "climate", "fan"]

# climate custom presets
PRESET_DAY = "day"
PRESET_COOLING_ON = "cooling_on"
PRESET_MANUAL = "manual"
PRESET_SYSTEM_OFF = "system_off"
PRESET_PARTY = "party"
PRESET_HOLIDAY = "holiday"
PRESET_QUICK_VETO = "quick_veto"
PRESET_COOLING_FOR_X_DAYS = "cooling_for_x_days"


# default values for configuration
DEFAULT_EMPTY = ""
DEFAULT_SCAN_INTERVAL = 2
DEFAULT_QUICK_VETO_DURATION = 3 * 60
DEFAULT_SMART_PHONE_ID = "homeassistant"

# max and min values for quick veto
MIN_QUICK_VETO_DURATION = 0.5 * 60
MAX_QUICK_VETO_DURATION = 24 * 60

# configuration keys
CONF_QUICK_VETO_DURATION = "quick_veto_duration"
CONF_SERIAL_NUMBER = "serial_number"

# constants for states_attributes
ATTR_QUICK_MODE = "quick_mode"
ATTR_START_DATE = "start_date"
ATTR_END_DATE = "end_date"
ATTR_TEMPERATURE = "temperature"
ATTR_DURATION = "duration"

SERVICES_HANDLER = "services_handler"

REFRESH_EVENT = "multimatic_refresh_event"

# Update api keys
ZONES = "zones"
ROOMS = "rooms"
DHW = "dhw"
REPORTS = "live_reports"
OUTDOOR_TEMP = "outdoor_temperature"
VENTILATION = "ventilation"
QUICK_MODE = "quick_mode"
HOLIDAY_MODE = "holiday_mode"
HVAC_STATUS = "hvac_status"
FACILITY_DETAIL = "facility_detail"
GATEWAY = "gateway"
COORDINATORS = "coordinators"
COORDINATOR_LIST: dict[str, timedelta | None] = {
    ZONES: None,
    ROOMS: None,
    DHW: None,
    REPORTS: None,
    OUTDOOR_TEMP: None,
    VENTILATION: None,
    QUICK_MODE: None,
    HOLIDAY_MODE: None,
    HVAC_STATUS: None,
    FACILITY_DETAIL: timedelta(days=1),
    GATEWAY: timedelta(days=1),
}
