import abc
import logging
from abc import ABC
from datetime import timedelta
from typing import Optional

import voluptuous as vol

from homeassistant.const import (CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME)
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle, slugify
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import discovery


REQUIREMENTS = ['vr900-connector==0.3.1']

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'vaillant'

PLATFORMS = [
    'binary_sensor',
    'sensor',
    'climate',
    'water_heater'
]

CONF_SMARTPHONE_ID = 'smartphoneid'
CONF_QUICK_VETO_DURATION = 'quick_veto_duration'
CONF_BINARY_SENSOR_CIRCULATION = 'binary_sensor_circulation'
CONF_BINARY_SENSOR_BOILER_ERROR = 'binary_sensor_boiler_error'
CONF_BINARY_SENSOR_SYSTEM_ONLINE = 'binary_sensor_system_online'
CONF_BINARY_SENSOR_SYSTEM_UPDATE = 'binary_sensor_system_update'
CONF_BINARY_SENSOR_ROOM_WINDOW = 'binary_sensor_room_window'
CONF_BINARY_SENSOR_ROOM_CHILD_LOCK = 'binary_sensor_room_child_lock'
CONF_BINARY_SENSOR_DEVICE_BATTERY = 'binary_sensor_device_battery'
CONF_BINARY_SENSOR_DEVICE_RADIO_REACH = 'binary_sensor_device_radio_reach'
CONF_SENSOR_ROOM_TEMPERATURE = 'sensor_room_temperature'
CONF_SENSOR_ZONE_TEMPERATURE = 'sensor_zone_temperature'
CONF_SENSOR_OUTDOOR_TEMPERATURE = 'sensor_outdoor_temperature'
CONF_SENSOR_HOT_WATER_TEMPERATURE = 'sensor_hot_water_temperature'
CONF_WATER_HEATER = 'water_heater'
CONF_ROOM_CLIMATE = 'room_climate'
CONF_ZONE_CLIMATE = 'zone_climate'

DEFAULT_EMPTY = ''
MIN_SCAN_INTERVAL = timedelta(minutes=5)
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)
DEFAULT_SMART_PHONE_ID = 'homeassistant'
DEFAULT_QUICK_VETO_DURATION = 3 * 60
QUICK_VETO_MIN_DURATION = 0.5 * 60
QUICK_VETO_MAX_DURATION = 24 * 60


# TODO translation, see zha component
# TODO config to enable/disable binary-sensor, sensor, climate, water heater etc. IDK how to handle the config
# TODO add TimeProgram as state attr for climate and water_heater ?
CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): (
            vol.All(cv.time_period, vol.Clamp(min=MIN_SCAN_INTERVAL))),
        vol.Optional(CONF_SMARTPHONE_ID, default=DEFAULT_SMART_PHONE_ID): cv.string,
        vol.Optional(CONF_QUICK_VETO_DURATION, default=DEFAULT_QUICK_VETO_DURATION): (
            vol.All(cv.positive_int, vol.Clamp(min=QUICK_VETO_MIN_DURATION, max=QUICK_VETO_MAX_DURATION))),
        vol.Optional(CONF_BINARY_SENSOR_CIRCULATION, default=True): cv.boolean,
        vol.Optional(CONF_BINARY_SENSOR_BOILER_ERROR, default=True): cv.boolean,
        vol.Optional(CONF_BINARY_SENSOR_SYSTEM_ONLINE, default=True): cv.boolean,
        vol.Optional(CONF_BINARY_SENSOR_SYSTEM_UPDATE, default=True): cv.boolean,
        vol.Optional(CONF_BINARY_SENSOR_ROOM_WINDOW, default=True): cv.boolean,
        vol.Optional(CONF_BINARY_SENSOR_ROOM_CHILD_LOCK, default=True): cv.boolean,
        vol.Optional(CONF_BINARY_SENSOR_DEVICE_BATTERY, default=True): cv.boolean,
        vol.Optional(CONF_BINARY_SENSOR_DEVICE_RADIO_REACH, default=True): cv.boolean,
        vol.Optional(CONF_SENSOR_ROOM_TEMPERATURE, default=True): cv.boolean,
        vol.Optional(CONF_SENSOR_ZONE_TEMPERATURE, default=True): cv.boolean,
        vol.Optional(CONF_SENSOR_OUTDOOR_TEMPERATURE, default=True): cv.boolean,
        vol.Optional(CONF_SENSOR_HOT_WATER_TEMPERATURE, default=True): cv.boolean,
        vol.Optional(CONF_WATER_HEATER, default=True): cv.boolean,
        vol.Optional(CONF_ROOM_CLIMATE, default=True): cv.boolean,
        vol.Optional(CONF_ZONE_CLIMATE, default=True): cv.boolean
    })
}, extra=vol.ALLOW_EXTRA)

HUB = None


async def async_setup(hass, config):
    global HUB

    HUB = VaillantHub(config[DOMAIN][CONF_USERNAME], config[DOMAIN][CONF_PASSWORD], config[DOMAIN][CONF_SMARTPHONE_ID],
                      config[DOMAIN][CONF_QUICK_VETO_DURATION])
    HUB.update_system = Throttle(
        config[DOMAIN][CONF_SCAN_INTERVAL])(HUB.update_system)

    HUB.update_system()

    for platform in PLATFORMS:
        hass.async_create_task(discovery.async_load_platform(hass, platform, DOMAIN, {}, config))

    _LOGGER.info("Successfully initialized")

    return True


class VaillantHub:

    def __init__(self, username, password, smart_phone_id, quick_veto_duration):
        from vr900connector.systemmanager import SystemManager
        from vr900connector.model import System

        self._manager = SystemManager(username, password,
                                      smart_phone_id)
        self._listeners = []
        self.system: System = None
        self._quick_veto_duration = quick_veto_duration

    def update_system(self):
        """
        Fetches vaillant system. This function is throttled in order to avoid fetching full system for each platform
        entity refresh.
        """
        self._manager.request_hvac_update()
        self.system = self._manager.get_system()
        _LOGGER.info("update_system successfully fetched")

    def find_component(self, comp):
        from vr900connector.model import Zone, Room, HotWater, Circulation
        """
        Find a component in the system with the given id, no IO is done
        :return: The component or None
        """
        if isinstance(comp, Zone):
            return self.system.get_zone(comp.id)
        elif isinstance(comp, Room):
            return self.system.get_room(comp.id)
        elif isinstance(comp, HotWater):
            if self.system.hot_water and self.system.hot_water.id == comp.id:
                return self.system.hot_water
        elif isinstance(comp, Circulation):
            if self.system.circulation and self.system.circulation.id == comp.id:
                return self.system.circulation

        return None

    def add_listener(self, listener):
        self._listeners.append(listener)

    def refresh_listening_entities(self):
        self.update_system(no_throttle=True)
        for listener in self._listeners:
            listener.async_schedule_update_ha_state(True)

    def set_hot_water_target_temperature(self, entity, hot_water, target_temperature):
        ok = self._manager.set_hot_water_setpoint_temperature(hot_water, target_temperature)

        if ok:
            self.system.hot_water = self._manager.get_hot_water(hot_water)
            entity.async_schedule_update_ha_state(True)

    def set_room_target_temperature(self, entity, room, target_temperature):
        """
        Setting target temperature only works if operation mode is MANUAL, otherwise the API call has no effect
        If the operation mode is not MANUAL, the call to this function will create a quick veto

        :param entity:
        :param room:
        :param target_temperature:
        :return:
        """
        from vr900connector.model import HeatingMode, QuickVeto

        am = self.system.get_active_mode_room(room)

        if am.current_mode != HeatingMode.MANUAL:
            veto = QuickVeto(self._quick_veto_duration, target_temperature)
            ok = self._manager.set_room_quick_veto(room, veto)
        else:
            ok = self._manager.set_room_setpoint_temperature(room, target_temperature)

        if ok:
            self.system.set_room(room.id, self._manager.get_room(room))
            entity.async_schedule_update_ha_state(True)

    def set_zone_target_temperature(self, entity, zone, target_temperature):
        """
        Setting target temperature only works if operation mode is DAY, otherwise the API call has no effect
        If the operation mode is not DAY, the call to this function will create a quick veto

        :param entity:
        :param zone:
        :param target_temperature:
        :return:
        """
        from vr900connector.model import HeatingMode, QuickVeto

        am = self.system.get_active_mode_zone(zone)

        if am.current_mode != HeatingMode.DAY:
            veto = QuickVeto(self._quick_veto_duration, target_temperature)
            ok = self._manager.set_zone_quick_veto(zone, veto)
        elif am.current_mode == HeatingMode.NIGHT:
            ok = self._manager.set_zone_setback_temperature(zone, target_temperature)
        else:
            ok = self._manager.set_zone_setpoint_temperature(zone, target_temperature)

        if ok:
            self.system.set_zone(zone.id, self._manager.get_zone(zone))
            entity.async_schedule_update_ha_state(True)

    def set_zone_target_high_temperature(self, entity, zone, temperature):
        ok = self._manager.set_zone_setpoint_temperature(zone, temperature)
        if ok:
            entity.async_schedule_update_ha_state(True)

    def set_zone_target_low_temperature(self, entity, zone, temperature):
        ok = self._manager.set_zone_setback_temperature(zone, temperature)
        if ok:
            entity.async_schedule_update_ha_state(True)

    def set_hot_water_operation_mode(self, entity, hot_water, operation_mode):
        from vr900connector.model import HeatingMode

        was_quick_mode = self._set_quick_mode(operation_mode)

        if not was_quick_mode:
            mode = HeatingMode[operation_mode]
            ok = self._manager.set_hot_water_operation_mode(hot_water, mode)
            if ok:
                self.system.hot_water = self._manager.get_hot_water(hot_water)
                entity.async_schedule_update_ha_state(True)

    def set_room_operation_mode(self, entity, room, operation_mode):
        from vr900connector.model import HeatingMode

        was_quick_mode = self._set_quick_mode(operation_mode)

        if not was_quick_mode:
            mode = HeatingMode[operation_mode]
            ok = self._manager.set_room_operation_mode(room, mode)
            if ok:
                self.system.set_room(room.id, self._manager.get_room(room))
                entity.async_schedule_update_ha_state(True)

    def set_zone_operation_mode(self, entity, zone, operation_mode):
        from vr900connector.model import HeatingMode

        was_quick_mode = self._set_quick_mode(operation_mode)

        if not was_quick_mode:
            mode = HeatingMode[operation_mode]
            ok = self._manager.set_zone_operation_mode(zone, mode)
            if ok:
                self.system.set_zone(zone.id, self._manager.get_zone(zone))
                entity.async_schedule_update_ha_state(True)

    def set_holiday_mode(self):
        self.refresh_listening_entities()

    def _set_quick_mode(self, quick_mode):
        from vr900connector.model import QuickMode

        if quick_mode in QuickMode.__members__:
            _LOGGER.debug('Mode %s is a quick mode', quick_mode)
            mode = QuickMode[quick_mode]
            ok = self._manager.set_quick_mode(self.system.quick_mode, mode)
            if ok:
                _LOGGER.debug("Set quick successfully")
                self.refresh_listening_entities()
            return True
        return False


class BaseVaillantEntity(Entity, ABC):

    def __init__(self, domain, device_class, comp_id, comp_name):
        self.comp_id = comp_id
        self.comp_name = comp_name
        self._device_class = device_class
        if device_class:
            self.id_format = domain + '.' + DOMAIN + '_{}_' + device_class
        else:
            self.id_format = domain + '.' + DOMAIN + '_{}'
        # self.name_format = self.id_format.replace("_", " ")

        self.entity_id = self.id_format.format(slugify(self.comp_id)).replace(' ', '_').lower()
        self._vaillant_name = comp_name

    @property
    def name(self) -> Optional[str]:
        return self._vaillant_name

    async def async_update(self):
        _LOGGER.debug("Time to update %s", self.entity_id)
        HUB.update_system()

        await self.vaillant_update()

    @property
    def device_class(self):
        return self._device_class

    @abc.abstractmethod
    async def vaillant_update(self):
        pass
