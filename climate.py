import abc
import logging

from vr900connector.model import System, Room, Component, QuickMode, Zone, HeatingMode

from . import HUB, BaseVaillantEntity, DOMAIN as VAILLANT, CONF_ROOM_CLIMATE, CONF_ZONE_CLIMATE

from homeassistant.components.climate import ClimateDevice, SUPPORT_AWAY_MODE, SUPPORT_OPERATION_MODE
from homeassistant.components.climate.const import SUPPORT_TARGET_TEMPERATURE, DOMAIN, SUPPORT_TARGET_TEMPERATURE_LOW, \
    SUPPORT_TARGET_TEMPERATURE_HIGH, ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH
from homeassistant.const import TEMP_CELSIUS, ATTR_TEMPERATURE

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    HUB.update_system()
    system = HUB.system

    climates = []

    if system:
        # if config[CONF_ZONE_CLIMATE]:
        for zone in HUB.system.zones:
            if not zone.rbr:
                entity = VaillantZoneClimate(HUB.system, zone)
                HUB.add_listener(entity)
                climates.append(entity)

        # if config[CONF_ROOM_CLIMATE]:
        for room in HUB.system.rooms:
            entity = VaillantRoomClimate(HUB.system, room)
            HUB.add_listener(entity)
            climates.append(entity)

    _LOGGER.info("Adding %s climate entities", len(climates))

    async_add_entities(climates)


class VaillantClimate(BaseVaillantEntity, ClimateDevice, abc.ABC):

    def __init__(self, system: System, comp_name, comp_id, component: Component):
        super().__init__(DOMAIN, None, comp_name, comp_id)
        self._system = None
        self._component = None
        self._active_mode = None
        self._refresh(system, component)

    def set_humidity(self, humidity):
        pass

    def set_fan_mode(self, fan_mode):
        pass

    def set_swing_mode(self, swing_mode):
        pass

    def set_hold_mode(self, hold_mode):
        pass

    def turn_aux_heat_on(self):
        pass

    def turn_aux_heat_off(self):
        pass

    def turn_on(self):
        pass

    def turn_off(self):
        pass

    @property
    def available(self):
        return self._component is not None

    @property
    def temperature_unit(self):
        return TEMP_CELSIUS

    @property
    def target_temperature(self):
        _LOGGER.debug("Target temp is %s", self._active_mode.target_temperature)
        return self._active_mode.target_temperature

    @property
    def current_temperature(self):
        return self._component.current_temperature

    @property
    def current_operation(self):
        _LOGGER.debug("current_operation is %s", self._active_mode.current_mode)
        return self._active_mode.current_mode.name

    @property
    def is_away_mode_on(self):
        return self._active_mode.current_mode == HeatingMode.OFF or self._system.holiday_mode.active

    async def vaillant_update(self):
        self._refresh(HUB.system, HUB.find_component(self._component))

    def _refresh(self, system, component):
        self._system = system
        self._component = component
        self._active_mode = self.get_active_mode()

    @abc.abstractmethod
    def get_active_mode(self):
        pass


class VaillantRoomClimate(VaillantClimate):

    def __init__(self, system: System, room: Room):
        super().__init__(system, room.name, room.name, room)
        self._active_mode = system.get_active_mode_room(room)
        self._supported_features = SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE | SUPPORT_AWAY_MODE
        mode_list = Room.MODES + QuickMode.for_room()
        mode_list.remove(QuickMode.HOLIDAY)
        mode_list.remove(HeatingMode.QUICK_VETO)
        self._operation_list = [mode.name for mode in mode_list]

    @property
    def supported_features(self):
        return self._supported_features

    @property
    def min_temp(self):
        return Room.MIN_TEMP

    @property
    def max_temp(self):
        return Room.MAX_TEMP

    @property
    def operation_list(self):
        if self._active_mode.current_mode == HeatingMode.QUICK_VETO:
            return self._operation_list + [HeatingMode.QUICK_VETO.name]
        else:
            return self._operation_list

    def get_active_mode(self):
        return self._system.get_active_mode_room(self._component)

    def set_temperature(self, **kwargs):
        HUB.set_room_target_temperature(self, self._component, float(kwargs.get(ATTR_TEMPERATURE)))

    def set_operation_mode(self, operation_mode):
        HUB.set_room_operation_mode(self, self._component, operation_mode)

    def turn_away_mode_on(self):
        HUB.set_room_operation_mode(self, self._component, HeatingMode.OFF.name)

    def turn_away_mode_off(self):
        HUB.set_room_operation_mode(self, self._component, HeatingMode.AUTO.name)


class VaillantZoneClimate(VaillantClimate):

    def __init__(self, system: System, zone: Zone):
        super().__init__(system, zone.id, zone.name, zone)
        self._active_mode = system.get_active_mode_zone(zone)
        self._supported_features = \
            SUPPORT_TARGET_TEMPERATURE_HIGH | SUPPORT_TARGET_TEMPERATURE_LOW | SUPPORT_TARGET_TEMPERATURE | \
            SUPPORT_OPERATION_MODE | SUPPORT_AWAY_MODE
        mode_list = Zone.MODES + QuickMode.for_zone()
        mode_list.remove(QuickMode.HOLIDAY)
        mode_list.remove(HeatingMode.QUICK_VETO)
        mode_list.remove(QuickMode.QM_QUICK_VETO)
        self._operation_list = [mode.name for mode in mode_list]

    @property
    def supported_features(self):
        return self._supported_features

    @property
    def min_temp(self):
        return Zone.MIN_TEMP

    @property
    def max_temp(self):
        return Zone.MAX_TEMP

    @property
    def operation_list(self):
        if self._active_mode.current_mode == HeatingMode.QUICK_VETO:
            return self._operation_list + [HeatingMode.QUICK_VETO.name]
        else:
            return self._operation_list

    @property
    def target_temperature_high(self):
        _LOGGER.debug("Target high temp is %s", self._component.target_temperature)
        return self._component.target_temperature

    @property
    def target_temperature_low(self):
        _LOGGER.debug("Target low temp is %s", self._component.target_min_temperature)
        return self._component.target_min_temperature

    def get_active_mode(self):
        return self._system.get_active_mode_zone(self._component)

    def set_temperature(self, **kwargs):
        low_temp = kwargs.get(ATTR_TARGET_TEMP_LOW)
        high_temp = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        temp = kwargs.get(ATTR_TEMPERATURE)

        if temp and temp != self._active_mode.target_temperature:
            _LOGGER.info("Setting target temp to %s", temp)
            HUB.set_zone_target_temperature(self, self._component, temp)
        elif low_temp and low_temp != self._component.target_min_temperature:
            _LOGGER.info("Setting target low temp to %s", low_temp)
            HUB.set_zone_target_low_temperature(self, self._component, low_temp)
        elif high_temp and high_temp != self._component.target_temperature:
            _LOGGER.info("Setting target high temp to %s", high_temp)
            HUB.set_zone_target_high_temperature(self, self._component, high_temp)
        else:
            _LOGGER.info("Nothing to do")

    def set_operation_mode(self, operation_mode):
        HUB.set_zone_operation_mode(self, self._component, operation_mode)

    def turn_away_mode_on(self):
        HUB.set_zone_operation_mode(self, self._component, HeatingMode.OFF.name)

    def turn_away_mode_off(self):
        HUB.set_zone_operation_mode(self, self._component, HeatingMode.AUTO.name)
