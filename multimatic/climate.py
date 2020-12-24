"""Interfaces with Multimatic climate."""

import abc
import logging
from typing import Any, Dict, List, Optional

from pymultimatic.model import (
    ActiveFunction,
    ActiveMode,
    Component,
    OperatingModes,
    QuickModes,
    Room,
    Zone,
)

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_IDLE,
    DOMAIN,
    HVAC_MODE_AUTO,
    HVAC_MODE_COOL,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_HOME,
    PRESET_NONE,
    PRESET_SLEEP,
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
)
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS
from homeassistant.helpers import entity_platform

from . import SERVICES, ApiHub
from .const import (
    DEFAULT_QUICK_VETO_DURATION,
    DOMAIN as MULTIMATIC,
    HUB,
    PRESET_COOLING_FOR_X_DAYS,
    PRESET_COOLING_ON,
    PRESET_DAY,
    PRESET_HOLIDAY,
    PRESET_MANUAL,
    PRESET_PARTY,
    PRESET_QUICK_VETO,
    PRESET_SYSTEM_OFF,
)
from .entities import MultimaticEntity
from .service import SERVICE_REMOVE_QUICK_VETO, SERVICE_SET_QUICK_VETO
from .utils import gen_state_attrs

_LOGGER = logging.getLogger(__name__)

_FUNCTION_TO_HVAC_ACTION: Dict[ActiveFunction, str] = {
    ActiveFunction.COOLING: CURRENT_HVAC_COOL,
    ActiveFunction.HEATING: CURRENT_HVAC_HEAT,
    ActiveFunction.STANDBY: CURRENT_HVAC_IDLE,
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the multimatic climate platform."""
    climates = []
    hub = hass.data[MULTIMATIC][entry.unique_id][HUB]

    if hub.system:
        if hub.system.zones:
            for zone in hub.system.zones:
                if not zone.rbr and zone.enabled:
                    entity = ZoneClimate(hub, zone)
                    climates.append(entity)

        if hub.system.rooms:
            rbr_zone = [zone for zone in hub.system.zones if zone.rbr][0]
            for room in hub.system.rooms:
                entity = RoomClimate(hub, room, rbr_zone)
                climates.append(entity)

    _LOGGER.info("Adding %s climate entities", len(climates))

    async_add_entities(climates, True)

    platform = entity_platform.current_platform.get()
    platform.async_register_entity_service(
        SERVICE_REMOVE_QUICK_VETO,
        SERVICES[SERVICE_REMOVE_QUICK_VETO]["schema"],
        SERVICE_REMOVE_QUICK_VETO,
    )
    platform.async_register_entity_service(
        SERVICE_SET_QUICK_VETO,
        SERVICES[SERVICE_SET_QUICK_VETO]["schema"],
        SERVICE_SET_QUICK_VETO,
    )

    return True


class MultimaticClimate(MultimaticEntity, ClimateEntity, abc.ABC):
    """Base class for climate."""

    def __init__(self, hub: ApiHub, comp_name, comp_id, component: Component):
        """Initialize entity."""
        super().__init__(hub, DOMAIN, comp_id, comp_name)
        self._system = None
        self.component = None
        self._refresh(hub.system, component)

    async def set_quick_veto(self, **kwargs):
        """Set quick veto, called by service."""
        temperature = kwargs.get("temperature")
        duration = kwargs.get("duration", DEFAULT_QUICK_VETO_DURATION)
        await self.coordinator.set_quick_veto(self, temperature, duration)

    async def remove_quick_veto(self, **kwargs):
        """Remove quick veto, called by service."""
        await self.coordinator.remove_quick_veto(self)

    @property
    @abc.abstractmethod
    def active_mode(self) -> ActiveMode:
        """Get active mode of the climate."""

    @property
    def listening(self):
        """Return whether this entity is listening for system changes or not."""
        return True

    @property
    def available(self):
        """Return True if entity is available."""
        return self.component is not None

    @property
    def temperature_unit(self):
        """Return the unit of measurement used by the platform."""
        return TEMP_CELSIUS

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        _LOGGER.debug("Target temp is %s", self.active_mode.target)
        return self.active_mode.target

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self.component.temperature

    @property
    def is_aux_heat(self) -> Optional[bool]:
        """Return true if aux heater."""
        return False

    @property
    def fan_mode(self) -> Optional[str]:
        """Return the fan setting."""
        return None

    @property
    def fan_modes(self) -> Optional[List[str]]:
        """Return the list of available fan modes."""
        return None

    @property
    def swing_mode(self) -> Optional[str]:
        """Return the swing setting."""
        return None

    @property
    def swing_modes(self) -> Optional[List[str]]:
        """Return the list of available swing modes."""
        return None

    def set_humidity(self, humidity: int) -> None:
        """Set new target humidity."""

    def set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""

    def set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing operation."""

    def turn_aux_heat_on(self) -> None:
        """Turn auxiliary heater on."""

    def turn_aux_heat_off(self) -> None:
        """Turn auxiliary heater off."""

    @property
    def target_temperature_high(self) -> Optional[float]:
        """Return the highbound target temperature we try to reach."""
        return None

    @property
    def target_temperature_low(self) -> Optional[float]:
        """Return the lowbound target temperature we try to reach."""
        return None

    async def async_custom_update(self):
        """Update specific for multimatic."""
        self._refresh(
            self.coordinator.system, self.coordinator.find_component(self.component)
        )

    def _refresh(self, system, component):
        """Refresh the entity."""
        self._system = system
        self.component = component


class RoomClimate(MultimaticClimate):
    """Climate for a room."""

    _MULTIMATIC_TO_HA = {
        OperatingModes.AUTO: [HVAC_MODE_AUTO, PRESET_COMFORT],
        OperatingModes.OFF: [HVAC_MODE_OFF, PRESET_NONE],
        OperatingModes.QUICK_VETO: [None, PRESET_QUICK_VETO],
        QuickModes.SYSTEM_OFF: [HVAC_MODE_OFF, PRESET_SYSTEM_OFF],
        QuickModes.HOLIDAY: [HVAC_MODE_OFF, PRESET_HOLIDAY],
        OperatingModes.MANUAL: [None, PRESET_MANUAL],
    }

    _HA_MODE_TO_MULTIMATIC = {
        HVAC_MODE_AUTO: OperatingModes.AUTO,
        HVAC_MODE_OFF: OperatingModes.OFF,
    }

    _HA_PRESET_TO_MULTIMATIC = {
        PRESET_COMFORT: OperatingModes.AUTO,
        PRESET_MANUAL: OperatingModes.MANUAL,
        PRESET_SYSTEM_OFF: QuickModes.SYSTEM_OFF,
    }

    def __init__(self, hub: ApiHub, room: Room, zone: Zone):
        """Initialize entity."""
        super().__init__(hub, room.name, room.name, room)
        self._zone = zone
        self._supported_hvac = list(RoomClimate._HA_MODE_TO_MULTIMATIC.keys())
        self._supported_presets = list(RoomClimate._HA_PRESET_TO_MULTIMATIC.keys())

    @property
    def hvac_mode(self) -> str:
        """Get the hvac mode based on multimatic mode."""
        active_mode = self.active_mode
        hvac_mode = RoomClimate._MULTIMATIC_TO_HA[active_mode.current][0]
        if not hvac_mode:
            if (
                active_mode.current
                in (OperatingModes.MANUAL, OperatingModes.QUICK_VETO)
                and self.hvac_action == CURRENT_HVAC_HEAT
            ):
                return HVAC_MODE_HEAT
        return hvac_mode

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes."""
        return self._supported_hvac

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_TARGET_TEMPERATURE | SUPPORT_PRESET_MODE

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return Room.MIN_TARGET_TEMP

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return Room.MAX_TARGET_TEMP

    @property
    def active_mode(self) -> ActiveMode:
        """Get active mode of the climate."""
        return self._system.get_active_mode_room(self.component)

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        await self.coordinator.set_room_target_temperature(
            self, float(kwargs.get(ATTR_TEMPERATURE))
        )

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        mode = RoomClimate._HA_MODE_TO_MULTIMATIC[hvac_mode]
        await self.coordinator.set_room_operating_mode(self, mode)

    @property
    def state_attributes(self) -> Dict[str, Any]:
        """Return the optional state attributes."""
        attributes = super().state_attributes
        attributes.update(gen_state_attrs(self.component, self.active_mode))
        return attributes

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., home, away, temp.

        Requires SUPPORT_PRESET_MODE.
        """
        return RoomClimate._MULTIMATIC_TO_HA[self.active_mode.current][1]

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes.

        Requires SUPPORT_PRESET_MODE.
        """
        if self.active_mode.current == OperatingModes.QUICK_VETO:
            return self._supported_presets + [PRESET_QUICK_VETO]
        return self._supported_presets

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        mode = RoomClimate._HA_PRESET_TO_MULTIMATIC[preset_mode]
        await self.coordinator.set_room_operating_mode(self, mode)

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported.

        Need to be one of CURRENT_HVAC_*.
        """
        if (
            self._zone.active_function == ActiveFunction.HEATING
            and self.component.temperature < self.active_mode.target
        ):
            return _FUNCTION_TO_HVAC_ACTION[ActiveFunction.HEATING]
        return _FUNCTION_TO_HVAC_ACTION[ActiveFunction.STANDBY]


class ZoneClimate(MultimaticClimate):
    """Climate for a zone."""

    _MULTIMATIC_TO_HA = {
        OperatingModes.AUTO: [HVAC_MODE_AUTO, PRESET_COMFORT],
        OperatingModes.DAY: [None, PRESET_DAY],
        OperatingModes.NIGHT: [None, PRESET_SLEEP],
        OperatingModes.OFF: [HVAC_MODE_OFF, PRESET_NONE],
        OperatingModes.ON: [None, PRESET_COOLING_ON],
        OperatingModes.QUICK_VETO: [None, PRESET_QUICK_VETO],
        QuickModes.ONE_DAY_AT_HOME: [HVAC_MODE_AUTO, PRESET_HOME],
        QuickModes.PARTY: [None, PRESET_PARTY],
        QuickModes.VENTILATION_BOOST: [HVAC_MODE_FAN_ONLY, PRESET_NONE],
        QuickModes.ONE_DAY_AWAY: [HVAC_MODE_OFF, PRESET_AWAY],
        QuickModes.SYSTEM_OFF: [HVAC_MODE_OFF, PRESET_SYSTEM_OFF],
        QuickModes.HOLIDAY: [HVAC_MODE_OFF, PRESET_HOLIDAY],
        QuickModes.COOLING_FOR_X_DAYS: [None, PRESET_COOLING_FOR_X_DAYS],
    }

    _HA_MODE_TO_MULTIMATIC = {
        HVAC_MODE_AUTO: OperatingModes.AUTO,
        HVAC_MODE_OFF: OperatingModes.OFF,
        HVAC_MODE_FAN_ONLY: QuickModes.VENTILATION_BOOST,
    }

    _HA_PRESET_TO_MULTIMATIC = {
        PRESET_COMFORT: OperatingModes.AUTO,
        PRESET_DAY: OperatingModes.DAY,
        PRESET_SLEEP: OperatingModes.NIGHT,
        PRESET_COOLING_ON: OperatingModes.ON,
        PRESET_HOME: QuickModes.ONE_DAY_AT_HOME,
        PRESET_PARTY: QuickModes.PARTY,
        PRESET_AWAY: QuickModes.ONE_DAY_AWAY,
        PRESET_SYSTEM_OFF: QuickModes.SYSTEM_OFF,
        PRESET_COOLING_FOR_X_DAYS: QuickModes.COOLING_FOR_X_DAYS,
    }

    def __init__(self, hub: ApiHub, zone: Zone):
        """Initialize entity."""
        super().__init__(hub, zone.name, zone.id, zone)

        self._supported_hvac = list(ZoneClimate._HA_MODE_TO_MULTIMATIC.keys())
        self._supported_presets = list(ZoneClimate._HA_PRESET_TO_MULTIMATIC.keys())

        if not zone.cooling:
            self._supported_presets.remove(PRESET_COOLING_ON)
            self._supported_presets.remove(PRESET_COOLING_FOR_X_DAYS)

        if not hub.system.ventilation:
            self._supported_hvac.remove(HVAC_MODE_FAN_ONLY)

    @property
    def hvac_mode(self):
        """Get the hvac mode based on multimatic mode."""
        current_mode = self.active_mode.current
        hvac_mode = ZoneClimate._MULTIMATIC_TO_HA[current_mode][0]
        if not hvac_mode:
            if (
                current_mode
                in [
                    OperatingModes.DAY,
                    OperatingModes.NIGHT,
                    QuickModes.PARTY,
                    OperatingModes.QUICK_VETO,
                ]
                and self.hvac_action == CURRENT_HVAC_HEAT
            ):
                return HVAC_MODE_HEAT
            if (
                self.preset_mode == PRESET_COOLING_ON
                and self.hvac_action == CURRENT_HVAC_COOL
            ):
                return HVAC_MODE_COOL
        return hvac_mode

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes."""
        return self._supported_hvac

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_TARGET_TEMPERATURE | SUPPORT_PRESET_MODE

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return Zone.MIN_TARGET_HEATING_TEMP

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return Zone.MAX_TARGET_TEMP

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.active_mode.target

    @property
    def active_mode(self) -> ActiveMode:
        """Get active mode of the climate."""
        return self._system.get_active_mode_zone(self.component)

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)

        if temp and temp != self.active_mode.target:
            _LOGGER.debug("Setting target temp to %s", temp)
            await self.coordinator.set_zone_target_temperature(self, temp)
        else:
            _LOGGER.debug("Nothing to do")

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        mode = ZoneClimate._HA_MODE_TO_MULTIMATIC[hvac_mode]
        await self.coordinator.set_zone_operating_mode(self, mode)

    @property
    def state_attributes(self) -> Dict[str, Any]:
        """Return the optional state attributes."""
        attributes = super().state_attributes
        attributes.update(gen_state_attrs(self.component, self.active_mode))
        return attributes

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported.

        Need to be one of CURRENT_HVAC_*.
        """
        return _FUNCTION_TO_HVAC_ACTION.get(self.component.active_function)

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., home, away, temp."""
        return ZoneClimate._MULTIMATIC_TO_HA[self.active_mode.current][1]

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes."""
        if self.active_mode.current == OperatingModes.QUICK_VETO:
            return self._supported_presets + [PRESET_QUICK_VETO]
        return self._supported_presets

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        mode = ZoneClimate._HA_PRESET_TO_MULTIMATIC[preset_mode]
        await self.coordinator.set_zone_operating_mode(self, mode)
