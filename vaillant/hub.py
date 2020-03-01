"""Api hub and integration data."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.util import Throttle

from .const import (
    DEFAULT_QUICK_VETO_DURATION,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SMART_PHONE_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class ApiHub:
    """Vaillant entry point for home-assistant."""

    def __init__(self, hass, username, password):
        """Initialize hub."""
        from pymultimatic.systemmanager import SystemManager

        self._manager = SystemManager(username, password, DEFAULT_SMART_PHONE_ID)
        self.system = None
        self.update_system = Throttle(DEFAULT_SCAN_INTERVAL)(self._update_system)
        self._hass = hass

    def authenticate(self):
        """Try to authenticate to the API."""
        return self._manager.login(True)

    def _update_system(self):
        """Fetch vaillant system."""
        from pymultimatic.api import ApiError

        try:
            self._manager.request_hvac_update()
            self.system = self._manager.get_system()
            _LOGGER.debug("update_system successfully fetched")
        except ApiError:
            _LOGGER.exception("Enable to fetch data from vaillant API")
            # update_system can is called by all entities, if it fails for
            # one entity, it will certainly fail for others.
            # catching exception so the throttling is occurring

    def logout(self):
        """Logout from API."""
        from pymultimatic.api import ApiError

        try:
            self._manager.logout()
        except ApiError:
            _LOGGER.warning("Cannot logout from vaillant API", exc_info=True)
            return False
        return True

    def find_component(self, comp):
        """Find a component in the system with the given id, no IO is done."""
        from pymultimatic.model import Zone, Room, HotWater, Circulation

        if isinstance(comp, Zone):
            for zone in self.system.zones:
                if zone.id == comp.id:
                    return zone
        if isinstance(comp, Room):
            for room in self.system.rooms:
                if room.id == comp.id:
                    return room
        if isinstance(comp, HotWater):
            if self.system.hot_water and self.system.hot_water.id == comp.id:
                return self.system.hot_water
        if isinstance(comp, Circulation):
            if self.system.circulation and self.system.circulation.id == comp.id:
                return self.system.circulation

        return None

    def set_hot_water_target_temperature(self, entity, hot_water, target_temp):
        """Set hot water target temperature.

        * If there is a quick mode that impact dhw running on or holiday mode,
        remove it.

        * If dhw is ON or AUTO, modify the target temperature

        * If dhw is OFF, change to ON and set target temperature
        """
        from pymultimatic.model import OperatingModes

        touch_system = self._remove_quick_mode_or_holiday(entity)

        current_mode = self.system.get_active_mode_hot_water(hot_water).current_mode

        if current_mode == OperatingModes.OFF or touch_system:
            self._manager.set_hot_water_operating_mode(hot_water.id, OperatingModes.ON)
        self._manager.set_hot_water_setpoint_temperature(hot_water.id, target_temp)

        self.system.hot_water = hot_water
        self._refresh(touch_system, entity)

    def set_room_target_temperature(self, entity, room, target_temp):
        """Set target temperature for a room.

        * If there is a quick mode that impact room running on or holiday mode,
        remove it.

        * If the room is in MANUAL mode, simply modify the target temperature.

        * if the room is not in MANUAL mode, create à quick veto.
        """
        from pymultimatic.model import QuickVeto, OperatingModes

        touch_system = self._remove_quick_mode_or_holiday(entity)

        current_mode = self.system.get_active_mode_room(room).current_mode

        if current_mode == OperatingModes.MANUAL:
            self._manager.set_room_setpoint_temperature(room.id, target_temp)
            room.target_temperature = target_temp
        else:
            if current_mode == OperatingModes.QUICK_VETO:
                self._manager.remove_room_quick_veto(room.id)

            qveto = QuickVeto(DEFAULT_QUICK_VETO_DURATION, target_temp)
            self._manager.set_room_quick_veto(room.id, qveto)
            room.quick_veto = qveto
        self.system.set_room(room.id, room)

        self._refresh(touch_system, entity)

    def set_zone_target_temperature(self, entity, zone, target_temp):
        """Set target temperature for a zone.

        * If there is a quick mode related to zone running or holiday mode,
        remove it.

        * If quick veto running on, remove it and create a new one with the
            new target temp

        * If any other mode, create a quick veto
        """
        from pymultimatic.model import QuickVeto, OperatingModes

        touch_system = self._remove_quick_mode_or_holiday(entity)

        current_mode = self.system.get_active_mode_zone(zone).current_mode

        if current_mode == OperatingModes.QUICK_VETO:
            self._manager.remove_zone_quick_veto(zone.id)

        veto = QuickVeto(None, target_temp)
        self._manager.set_zone_quick_veto(zone.id, veto)
        zone.quick_veto = veto

        self.system.set_zone(zone.id, zone)
        self._refresh(touch_system, entity)

    def set_hot_water_operating_mode(self, entity, hot_water, mode):
        """Set hot water operation mode.

        If there is a quick mode that impact hot warter running on or holiday
        mode, remove it.
        """
        touch_system = self._remove_quick_mode_or_holiday(entity)

        self._manager.set_hot_water_operating_mode(hot_water.id, mode)
        hot_water.operating_mode = mode

        self.system.hot_water = hot_water
        self._refresh(touch_system, entity)

    def set_room_operating_mode(self, entity, room, mode):
        """Set room operation mode.

        If there is a quick mode that impact room running on or holiday mode,
        remove it.
        """
        touch_system = self._remove_quick_mode_or_holiday(entity)
        if room.quick_veto is not None:
            self._manager.remove_room_quick_veto(room.id)
            room.quick_veto = None

        self._manager.set_room_operating_mode(room.id, mode)
        room.operating_mode = mode

        self.system.set_room(room.id, room)
        self._refresh(touch_system, entity)

    def set_zone_operating_mode(self, entity, zone, mode):
        """Set zone operation mode.

        If there is a quick mode that impact zone running on or holiday mode,
        remove it.
        """
        touch_system = self._remove_quick_mode_or_holiday(entity)

        if zone.quick_veto is not None:
            self._manager.remove_zone_quick_veto(zone.id)
            zone.quick_veto = None

        self._manager.set_zone_operating_mode(zone.id, mode)
        zone.operating_mode = mode

        self.system.set_zone(zone.id, zone)
        self._refresh(touch_system, entity)

    def remove_quick_mode(self, entity=None):
        """Remove quick mode.

        If entity is not None, only remove if the quick mode applies to the
        given entity.
        """
        if self._remove_quick_mode_no_refresh(entity):
            self._refresh_entities()

    def remove_holiday_mode(self):
        """Remove holiday mode."""
        if self._remove_holiday_mode_no_refresh():
            self._refresh_entities()

    def set_holiday_mode(self, start_date, end_date, temperature):
        """Set holiday mode."""
        self._manager.set_holiday_mode(start_date, end_date, temperature)
        self._refresh_entities()

    def set_quick_mode(self, mode):
        """Set quick mode (remove previous one)."""
        from pymultimatic.model import QuickModes

        self._remove_quick_mode_no_refresh()
        self._manager.set_quick_mode(QuickModes.get(mode))
        self._refresh_entities()

    def set_quick_veto(self, entity, temperature, duration=None):
        """Set quick veto for the given entity."""
        from pymultimatic.model import QuickVeto, Zone

        comp = self.find_component(entity.component)

        q_duration = duration if duration else DEFAULT_QUICK_VETO_DURATION
        qveto = QuickVeto(q_duration, temperature)

        if isinstance(comp, Zone):
            if comp.quick_veto:
                self._manager.remove_zone_quick_veto(comp.id)
            self._manager.set_zone_quick_veto(comp.id, qveto)
        else:
            if comp.quick_veto:
                self._manager.remove_room_quick_veto(comp.id)
            self._manager.set_room_quick_veto(comp.id, qveto)
        comp.quick_veto = qveto
        self._refresh(False, entity)

    def remove_quick_veto(self, entity):
        """Remove quick veto for the given entity."""
        from pymultimatic.model import Zone

        comp = self.find_component(entity.component)

        if comp and comp.quick_veto:
            if isinstance(comp, Zone):
                self._manager.remove_zone_quick_veto(comp.id)
            else:
                self._manager.remove_room_quick_veto(comp.id)
            comp.quick_veto = None
            self._refresh(False, entity)

    def get_entity(self, entity_id):
        """Get entity owned by this component."""
        for entity in self._hass.data[DOMAIN].entities:
            if entity.entity_id == entity_id:
                return entity
        return None

    def _remove_quick_mode_no_refresh(self, entity=None):
        from pymultimatic.model import Zone, Room, HotWater

        removed = False

        if self.system.quick_mode is not None:
            qmode = self.system.quick_mode

            if entity:
                if (
                    (isinstance(entity.component, Zone) and qmode.for_zone)
                    or (isinstance(entity.component, Room) and qmode.for_room)
                    or (isinstance(entity.component, HotWater) and qmode.for_dhw)
                ):
                    self._hard_remove_quick_mode()
                    removed = True
            else:
                self._hard_remove_quick_mode()
                removed = True
        return removed

    def _hard_remove_quick_mode(self):
        self._manager.remove_quick_mode()
        self.system.quick_mode = None

    def _remove_holiday_mode_no_refresh(self):
        from pymultimatic.model import HolidayMode

        removed = False

        if self.system.holiday_mode is not None and self.system.holiday_mode.is_active:
            removed = True
            self._manager.remove_holiday_mode()
            self.system.holiday_mode = HolidayMode(False)
        return removed

    def _remove_quick_mode_or_holiday(self, entity):
        return self._remove_holiday_mode_no_refresh() | self._remove_quick_mode_no_refresh(
            entity
        )

    def _refresh_entities(self):
        """Fetch vaillant data and force refresh of all listening entities."""
        self.update_system(no_throttle=True)
        for entity in self._hass.data[DOMAIN].entities:
            if entity.listening:
                entity.async_schedule_update_ha_state(True)

    def _refresh(self, touch_system, entity):
        if touch_system:
            self._refresh_entities()
        else:
            entity.async_schedule_update_ha_state(True)


class DomainData:
    """Data for the integration."""

    def __init__(self, api: ApiHub, entry: ConfigEntry) -> None:
        """Init."""
        self.api = api
        self.entry = entry
        self.entities = []
