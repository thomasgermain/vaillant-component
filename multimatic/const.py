"""multimatic integration constants."""

# constants used in hass.data
DOMAIN = "multimatic"
HUB = "hub"
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
CONF_SMARTPHONE_ID = "smartphoneid"
CONF_SERIAL_NUMBER = "serial_number"

# constants for states_attributes
ATTR_MULTIMATIC_MODE = "multimatic_mode"
ATTR_MULTIMATIC_SETTING = "setting"
ATTR_ENDS_AT = "ends_at"
ATTR_QUICK_MODE = "quick_mode"
ATTR_START_DATE = "start_date"
ATTR_END_DATE = "end_date"
ATTR_TEMPERATURE = "temperature"
ATTR_DURATION = "duration"

SERVICES_HANDLER = "services_handler"
HUB = "hub"

REFRESH_ENTITIES_EVENT = "multimatic_refresh_entities"
