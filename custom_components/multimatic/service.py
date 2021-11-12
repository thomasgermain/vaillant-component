"""multimatic services."""
import logging

from pymultimatic.model import QuickMode, QuickModes
import voluptuous as vol

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.util.dt import parse_date

from .const import (
    ATTR_DURATION,
    ATTR_END_DATE,
    ATTR_LEVEL,
    ATTR_QUICK_MODE,
    ATTR_START_DATE,
    ATTR_TEMPERATURE,
)
from .coordinator import MultimaticApi

_LOGGER = logging.getLogger(__name__)

QUICK_MODES_LIST = [
    v.name for v in QuickModes.__dict__.values() if isinstance(v, QuickMode)
]

SERVICE_REMOVE_QUICK_MODE = "remove_quick_mode"
SERVICE_REMOVE_HOLIDAY_MODE = "remove_holiday_mode"
SERVICE_SET_QUICK_MODE = "set_quick_mode"
SERVICE_SET_HOLIDAY_MODE = "set_holiday_mode"
SERVICE_SET_QUICK_VETO = "set_quick_veto"
SERVICE_REMOVE_QUICK_VETO = "remove_quick_veto"
SERVICE_REQUEST_HVAC_UPDATE = "request_hvac_update"
SERVICE_SET_VENTILATION_DAY_LEVEL = "set_ventilation_day_level"
SERVICE_SET_VENTILATION_NIGHT_LEVEL = "set_ventilation_night_level"

SERVICE_REMOVE_QUICK_MODE_SCHEMA = vol.Schema({})
SERVICE_REMOVE_HOLIDAY_MODE_SCHEMA = vol.Schema({})
SERVICE_REMOVE_QUICK_VETO_SCHEMA = vol.Schema(
    {vol.Required(ATTR_ENTITY_ID): vol.All(vol.Coerce(str))}
)
SERVICE_SET_QUICK_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_QUICK_MODE): vol.All(
            vol.Coerce(str), vol.In(QUICK_MODES_LIST)
        ),
        vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(int), vol.Clamp(min=1)),
    }
)
SERVICE_SET_HOLIDAY_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_START_DATE): vol.All(vol.Coerce(str)),
        vol.Required(ATTR_END_DATE): vol.All(vol.Coerce(str)),
        vol.Required(ATTR_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Clamp(min=5, max=30)
        ),
    }
)
SERVICE_SET_QUICK_VETO_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): vol.All(vol.Coerce(str)),
        vol.Required(ATTR_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Clamp(min=5, max=30)
        ),
        vol.Optional(ATTR_DURATION): vol.All(
            vol.Coerce(int), vol.Clamp(min=30, max=1440)
        ),
    }
)
SERVICE_REQUEST_HVAC_UPDATE_SCHEMA = vol.Schema({})

SERVICE_SET_VENTILATION_DAY_LEVEL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_LEVEL): vol.All(vol.Coerce(int), vol.Clamp(min=1, max=6)),
    }
)

SERVICE_SET_VENTILATION_NIGHT_LEVEL_SCHEMA = SERVICE_SET_VENTILATION_DAY_LEVEL_SCHEMA

SERVICES = {
    SERVICE_REMOVE_QUICK_MODE: {
        "schema": SERVICE_REMOVE_QUICK_MODE_SCHEMA,
    },
    SERVICE_REMOVE_HOLIDAY_MODE: {
        "schema": SERVICE_REMOVE_HOLIDAY_MODE_SCHEMA,
    },
    SERVICE_REMOVE_QUICK_VETO: {
        "schema": SERVICE_REMOVE_QUICK_VETO_SCHEMA,
        "entity": True,
    },
    SERVICE_SET_QUICK_MODE: {
        "schema": SERVICE_SET_QUICK_MODE_SCHEMA,
    },
    SERVICE_SET_HOLIDAY_MODE: {
        "schema": SERVICE_SET_HOLIDAY_MODE_SCHEMA,
    },
    SERVICE_SET_QUICK_VETO: {"schema": SERVICE_SET_QUICK_VETO_SCHEMA, "entity": True},
    SERVICE_REQUEST_HVAC_UPDATE: {
        "schema": SERVICE_REQUEST_HVAC_UPDATE_SCHEMA,
    },
    SERVICE_SET_VENTILATION_NIGHT_LEVEL: {
        "schema": SERVICE_SET_VENTILATION_NIGHT_LEVEL_SCHEMA
    },
    SERVICE_SET_VENTILATION_DAY_LEVEL: {
        "schema": SERVICE_SET_VENTILATION_DAY_LEVEL_SCHEMA
    },
}


class MultimaticServiceHandler:
    """Service implementation."""

    def __init__(self, hub: MultimaticApi, hass) -> None:
        """Init."""
        self.api = hub
        self._hass = hass

    async def service_call(self, call):
        """Handle service calls."""
        service = call.service
        method = getattr(self, service)
        await method(data=call.data)

    async def remove_quick_mode(self, data):
        """Remove quick mode. It has impact on all components."""
        await self.api.remove_quick_mode()

    async def set_holiday_mode(self, data):
        """Set holiday mode."""
        start_str = data.get(ATTR_START_DATE, None)
        end_str = data.get(ATTR_END_DATE, None)
        temp = data.get(ATTR_TEMPERATURE)
        start = parse_date(start_str.split("T")[0])
        end = parse_date(end_str.split("T")[0])
        if end is None or start is None:
            raise ValueError(f"dates are incorrect {start_str} {end_str}")
        await self.api.set_holiday_mode(start, end, temp)

    async def remove_holiday_mode(self, data):
        """Remove holiday mode."""
        await self.api.remove_holiday_mode()

    async def set_quick_mode(self, data):
        """Set quick mode, it may impact the whole system."""
        quick_mode = data.get(ATTR_QUICK_MODE, None)
        duration = data.get(ATTR_DURATION, None)
        await self.api.set_quick_mode(quick_mode, duration)

    async def request_hvac_update(self, data):
        """Ask multimatic API to get data from the installation."""
        await self.api.request_hvac_update()

    async def set_ventilation_day_level(self, data):
        """Set ventilation day level."""
        await self.api.set_fan_day_level(data.get(ATTR_LEVEL))

    async def set_ventilation_night_level(self, data):
        """Set ventilation day level."""
        await self.api.set_fan_night_level(data.get(ATTR_LEVEL))
