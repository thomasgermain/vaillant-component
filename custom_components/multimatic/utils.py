"""Utility."""
from __future__ import annotations

from datetime import datetime

from pymultimatic.model import HolidayMode, QuickMode, QuickModes

from homeassistant.core import HomeAssistant

from .const import COORDINATORS, DOMAIN as MULTIMATIC

_DATE_FORMAT = "%Y-%m-%d"


def get_coordinator(hass: HomeAssistant, key: str, entry_id: str | None):
    """Get coordinator from hass data."""
    return hass.data[MULTIMATIC][entry_id][COORDINATORS][key]


def holiday_mode_to_json(holiday_mode):
    """Convert holiday to json."""
    if holiday_mode and holiday_mode.is_applied:
        return {
            "active": True,
            "start_date": holiday_mode.start_date.strftime(_DATE_FORMAT),
            "end_date": holiday_mode.end_date.strftime(_DATE_FORMAT),
            "target": holiday_mode.target,
        }
    return None


def holiday_mode_from_json(str_json) -> HolidayMode:
    """Convert json to holiday mode."""
    if str_json:
        return HolidayMode(
            str_json["active"],
            datetime.strptime(str_json["start_date"], _DATE_FORMAT).date(),
            datetime.strptime(str_json["end_date"], _DATE_FORMAT).date(),
            str_json["target"],
        )
    return HolidayMode(False)


def quick_mode_to_json(quick_mode):
    """Convert quick mode to json."""
    if quick_mode:
        return {"name": quick_mode.name, "duration": quick_mode.duration}
    return None


def quick_mode_from_json(str_json) -> QuickMode:
    """Convert json to quick mode."""
    if str_json:
        return QuickModes.get(str_json["name"], str_json["duration"])
    return None
