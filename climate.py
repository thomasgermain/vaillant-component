import abc
import logging
from typing import Optional, List, Dict

from vr900connector.model import System, Room, Component, QuickMode, Zone, HeatingMode, Mode

from . import HUB, BaseVaillantEntity, CONF_ROOM_CLIMATE, CONF_ZONE_CLIMATE

from homeassistant.components.climate import ClimateDevice
from homeassistant.components.climate.const import SUPPORT_TARGET_TEMPERATURE, DOMAIN, \
    SUPPORT_TARGET_TEMPERATURE_RANGE, ATTR_TARGET_TEMP_LOW, ATTR_TARGET_TEMP_HIGH, SUPPORT_PRESET_MODE, HVAC_MODE_OFF, \
    HVAC_MODE_HEAT, HVAC_MODE_AUTO, PRESET_AWAY, HVAC_MODE_FAN_ONLY, PRESET_COMFORT, PRESET_BOOST, \
    PRESET_SLEEP, PRESET_HOME, HVAC_MODE_COOL
from homeassistant.const import TEMP_CELSIUS, ATTR_TEMPERATURE

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    HUB.update_system()
    system = HUB.system

    climates = []

    if system:
        if HUB.config[CONF_ZONE_CLIMATE]:
            for zone in HUB.system.zones:
                if not zone.rbr:
                    entity = VaillantZoneClimate(HUB.system, zone)
                    HUB.add_listener(entity)
                    climates.append(entity)

        if HUB.config[CONF_ROOM_CLIMATE]:
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
    def is_aux_heat(self) -> Optional[bool]:
        return False

    @property
    def fan_mode(self) -> Optional[str]:
        return None

    @property
    def fan_modes(self) -> Optional[List[str]]:
        return None

    @property
    def swing_mode(self) -> Optional[str]:
        return None

    @property
    def swing_modes(self) -> Optional[List[str]]:
        return None

    def set_humidity(self, humidity: int) -> None:
        pass

    def set_fan_mode(self, fan_mode: str) -> None:
        pass

    def set_swing_mode(self, swing_mode: str) -> None:
        pass

    def turn_aux_heat_on(self) -> None:
        pass

    def turn_aux_heat_off(self) -> None:
        pass

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

    _MODE_TO_PRESET = {
        HeatingMode.QUICK_VETO: PRESET_BOOST,
        HeatingMode.AUTO: PRESET_COMFORT,
        HeatingMode.ON: PRESET_HOME,
        HeatingMode.OFF: PRESET_SLEEP,
        HeatingMode.MANUAL: PRESET_COMFORT,
        QuickMode.HOLIDAY: PRESET_AWAY,
        QuickMode.QM_SYSTEM_OFF: PRESET_SLEEP
    }

    _MODE_TO_HVAC: Dict[Mode, str] = {
        HeatingMode.QUICK_VETO: HVAC_MODE_HEAT,
        HeatingMode.ON: HVAC_MODE_HEAT,
        HeatingMode.MANUAL: HVAC_MODE_HEAT,

        HeatingMode.AUTO: HVAC_MODE_AUTO,

        HeatingMode.OFF: HVAC_MODE_OFF,
        QuickMode.HOLIDAY: HVAC_MODE_OFF,
        QuickMode.QM_SYSTEM_OFF: HVAC_MODE_OFF
    }

    _HVAC_TO_MODE: Dict[str, Mode] = {
        HVAC_MODE_AUTO: HeatingMode.AUTO,
        HVAC_MODE_OFF: HeatingMode.OFF,
        HVAC_MODE_HEAT: HeatingMode.MANUAL
    }

    _SUPPORTED_HVAC_MODE = list(set(_MODE_TO_HVAC.values()))

    _SUPPORTED_PRESET_MODE = list(set(_MODE_TO_PRESET.values()))

    def __init__(self, system: System, room: Room):
        super().__init__(system, room.name, room.name, room)
        self._active_mode = system.get_active_mode_room(room)
        self._supported_features = SUPPORT_TARGET_TEMPERATURE | SUPPORT_PRESET_MODE

    @property
    def hvac_mode(self) -> str:
        return self.__class__._MODE_TO_HVAC[self._active_mode.current_mode]

    @property
    def hvac_modes(self) -> List[str]:
        return self.__class__._SUPPORTED_HVAC_MODE

    @property
    def preset_mode(self) -> Optional[str]:
        return self.__class__._MODE_TO_PRESET[self._active_mode.current_mode]

    @property
    def preset_modes(self) -> Optional[List[str]]:
        return self.__class__._SUPPORTED_PRESET_MODE

    @property
    def supported_features(self):
        return self._supported_features

    @property
    def min_temp(self):
        return Room.MIN_TEMP

    @property
    def max_temp(self):
        return Room.MAX_TEMP

    def get_active_mode(self):
        return self._system.get_active_mode_room(self._component)

    def set_temperature(self, **kwargs):
        HUB.set_room_target_temperature(self, self._component, float(kwargs.get(ATTR_TEMPERATURE)))

    def set_preset_mode(self, preset_mode: str) -> None:
        if PRESET_AWAY == preset_mode:
            HUB.set_room_operation_mode(self, self._component, HeatingMode.OFF.name)
        else:
            HUB.set_room_operation_mode(self, self._component, HeatingMode.AUTO.name)

    def set_hvac_mode(self, hvac_mode: str) -> None:
        mode = self.__class__._HVAC_TO_MODE[hvac_mode]
        HUB.set_zone_operation_mode(self, self._component, mode)

    @property
    def target_temperature_high(self) -> Optional[float]:
        return None

    @property
    def target_temperature_low(self) -> Optional[float]:
        return None


class VaillantZoneClimate(VaillantClimate):
    _MODE_TO_PRESET = {
        HeatingMode.QUICK_VETO: PRESET_BOOST,
        HeatingMode.AUTO: PRESET_COMFORT,
        HeatingMode.NIGHT: PRESET_SLEEP,
        HeatingMode.DAY: PRESET_HOME,
        HeatingMode.OFF: PRESET_SLEEP,
        QuickMode.QM_ONE_DAY_AWAY: PRESET_AWAY,
        QuickMode.HOLIDAY: PRESET_AWAY,
        QuickMode.QM_ONE_DAY_AT_HOME: PRESET_COMFORT,
        QuickMode.QM_PARTY: PRESET_COMFORT,
        QuickMode.QM_SYSTEM_OFF: PRESET_SLEEP,
        QuickMode.QM_VENTILATION_BOOST: PRESET_BOOST
    }

    _MODE_TO_HVAC: Dict[Mode, str] = {
        HeatingMode.QUICK_VETO: HVAC_MODE_HEAT,
        HeatingMode.DAY: HVAC_MODE_HEAT,
        QuickMode.QM_PARTY: HVAC_MODE_HEAT,

        HeatingMode.NIGHT: HVAC_MODE_COOL,

        HeatingMode.AUTO: HVAC_MODE_AUTO,
        QuickMode.QM_ONE_DAY_AT_HOME: HVAC_MODE_AUTO,

        HeatingMode.OFF: HVAC_MODE_OFF,
        QuickMode.QM_ONE_DAY_AWAY: HVAC_MODE_OFF,
        QuickMode.HOLIDAY: HVAC_MODE_OFF,
        QuickMode.QM_SYSTEM_OFF: HVAC_MODE_OFF,

        QuickMode.QM_VENTILATION_BOOST: HVAC_MODE_FAN_ONLY
    }

    _HVAC_TO_MODE: Dict[str, Mode] = {
        HVAC_MODE_COOL: HeatingMode.NIGHT,
        HVAC_MODE_AUTO: HeatingMode.AUTO,
        HVAC_MODE_OFF: HeatingMode.OFF,
        HVAC_MODE_HEAT: HeatingMode.DAY,
        HVAC_MODE_FAN_ONLY: QuickMode.QM_VENTILATION_BOOST
    }

    _SUPPORTED_HVAC_MODE = list(set(_MODE_TO_HVAC.values()))

    _SUPPORTED_PRESET_MODE = list(set(_MODE_TO_PRESET.values()))

    def __init__(self, system: System, zone: Zone):
        super().__init__(system, zone.id, zone.name, zone)
        self._active_mode = system.get_active_mode_zone(zone)
        self._supported_features = SUPPORT_TARGET_TEMPERATURE_RANGE | SUPPORT_TARGET_TEMPERATURE | SUPPORT_PRESET_MODE

    @property
    def hvac_mode(self) -> str:
        return self.__class__._MODE_TO_HVAC[self._active_mode.current_mode]

    @property
    def hvac_modes(self) -> List[str]:
        return self.__class__._SUPPORTED_HVAC_MODE

    @property
    def preset_mode(self) -> Optional[str]:
        return self.__class__._MODE_TO_PRESET[self._active_mode.current_mode]

    @property
    def preset_modes(self) -> Optional[List[str]]:
        return self.__class__._SUPPORTED_PRESET_MODE

    def set_preset_mode(self, preset_mode: str) -> None:
        if PRESET_AWAY == preset_mode:
            HUB.set_zone_operation_mode(self, self._component, HeatingMode.OFF.name)
        else:
            HUB.set_zone_operation_mode(self, self._component, HeatingMode.AUTO.name)

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

    def set_hvac_mode(self, hvac_mode):
        mode = self.__class__._HVAC_TO_MODE[hvac_mode]
        HUB.set_zone_operation_mode(self, self._component, mode)
