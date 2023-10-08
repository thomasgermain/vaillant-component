"""multimatic integration constants."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "multimatic"
SENSO = "SENSO"
MULTIMATIC = "MULTIMATIC"
ENTITIES = "entities"

# list of platforms into entity are created
PLATFORMS = ["binary_sensor", "sensor", "climate", "fan"]

# climate custom presets
PRESET_SYSTEM_OFF = "System off"
PRESET_QUICK_VETO = "Quick Veto"


# default values for configuration
DEFAULT_EMPTY = ""
DEFAULT_SCAN_INTERVAL = 2
DEFAULT_QUICK_VETO_DURATION_HOURS = 3
DEFAULT_QUICK_VETO_DURATION = DEFAULT_QUICK_VETO_DURATION_HOURS * 60
DEFAULT_SMART_PHONE_ID = "homeassistant"

# max and min values for quick veto
MIN_QUICK_VETO_DURATION = 0.5 * 60
MAX_QUICK_VETO_DURATION = 24 * 60

# configuration keys
CONF_QUICK_VETO_DURATION = "quick_veto_duration"
CONF_SERIAL_NUMBER = "serial_number"
CONF_APPLICATION = "application"

# constants for states_attributes
ATTR_QUICK_MODE = "quick_mode"
ATTR_START_DATE = "start_date"
ATTR_END_DATE = "end_date"
ATTR_TEMPERATURE = "temperature"
ATTR_DURATION = "duration"
ATTR_LEVEL = "level"
ATTR_DATE_TIME = "datetime"

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
EMF_REPORTS = "emf_reports"
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
    EMF_REPORTS: None,
}

FORCE_RELOGIN_TIMEDELTA = timedelta(hours=1)
RELOGIN_TASK_CLEAN = "relogin_task_clean"
