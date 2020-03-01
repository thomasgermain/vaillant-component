"""Utilities for HA."""
from datetime import timedelta

from pymultimatic.model import OperatingModes

from homeassistant.util import dt

from .const import (
    ATTR_ENDS_AT,
    ATTR_VAILLANT_MODE,
    ATTR_VAILLANT_NEXT_SETTING,
    ATTR_VAILLANT_SETTING,
)


def gen_state_attrs(component, active_mode):
    """Generate state_attrs."""
    attrs = {}
    attrs.update({ATTR_VAILLANT_MODE: active_mode.current_mode.name})

    if active_mode.current_mode == OperatingModes.QUICK_VETO:
        if component.quick_veto.remaining_duration:
            qveto_end = _get_quick_veto_end(component)
            if qveto_end:
                attrs.update({ATTR_ENDS_AT: qveto_end.isoformat()})
    elif active_mode.current_mode == OperatingModes.AUTO:
        setting = _get_next_setting(component)
        value = setting.setting.name if setting.setting else setting.target_temperature
        attrs.update(
            {
                ATTR_VAILLANT_NEXT_SETTING: value,
                ATTR_ENDS_AT: setting.start.isoformat(),
            }
        )

        if active_mode.sub_mode is not None:
            attrs.update({ATTR_VAILLANT_SETTING: active_mode.sub_mode.name})

    return attrs


def _get_quick_veto_end(component):
    end_time = None
    # there is no remaining duration for zone
    if component.quick_veto.remaining_duration:
        millis = component.quick_veto.remaining_duration * 60 * 1000
        end_time = dt.now() + timedelta(milliseconds=millis)
        end_time = end_time.replace(second=0, microsecond=0)
    return end_time


def _get_next_setting(component):
    now = dt.now()
    setting = component.time_program.get_next(now)

    abs_min = now.hour * 60 + now.minute

    if setting.absolute_minutes < abs_min:
        now += timedelta(days=1)

    setting.start = now.replace(
        hour=setting.hour, minute=setting.minute, second=0, microsecond=0
    )
    return setting
