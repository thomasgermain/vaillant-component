"""Utilities for HA."""
from datetime import timedelta

from pymultimatic.model import OperatingModes

from homeassistant.util import dt

from .const import ATTR_ENDS_AT, ATTR_VAILLANT_MODE, ATTR_VAILLANT_SETTING


def gen_state_attrs(component, active_mode):
    """Generate state_attrs."""
    attrs = {}
    attrs.update({ATTR_VAILLANT_MODE: active_mode.current.name})
    if active_mode.sub is not None:
        attrs.update({ATTR_VAILLANT_SETTING: active_mode.sub.name})

    if active_mode.current == OperatingModes.QUICK_VETO:
        qveto_end = _get_quick_veto_end(component)
        if qveto_end:
            attrs.update({ATTR_ENDS_AT: qveto_end.isoformat()})
    return attrs


def _get_quick_veto_end(component):
    end_time = None
    # there is no remaining duration for zone
    if component.quick_veto.duration:
        millis = component.quick_veto.duration * 60 * 1000
        end_time = dt.now() + timedelta(milliseconds=millis)
        end_time = end_time.replace(second=0, microsecond=0)
    return end_time
