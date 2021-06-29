"""Interfaces with Multimatic climate."""
from __future__ import annotations

import abc
import logging
from typing import Any, Mapping

from pymultimatic.model import (
    ActiveFunction,
    ActiveMode,
    Component,
    Mode,
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

from . import SERVICES
from .const import (
    DEFAULT_QUICK_VETO_DURATION,
    PRESET_COOLING_FOR_X_DAYS,
    PRESET_COOLING_ON,
    PRESET_DAY,
    PRESET_HOLIDAY,
    PRESET_MANUAL,
    PRESET_PARTY,
    PRESET_QUICK_VETO,
    PRESET_SYSTEM_OFF,
    ROOMS,
    VENTILATION,
    ZONES,
)
from .coordinator import MultimaticCoordinator
from .entities import MultimaticEntity
from .service import SERVICE_REMOVE_QUICK_VETO, SERVICE_SET_QUICK_VETO
from .utils import get_coordinator

_LOGGER = logging.getLogger(__name__)

_FUNCTION_TO_HVAC_ACTION: dict[ActiveFunction, str] = {
    ActiveFunction.COOLING: CURRENT_HVAC_COOL,
    ActiveFunction.HEATING: CURRENT_HVAC_HEAT,
    ActiveFunction.STANDBY: CURRENT_HVAC_IDLE,
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the multimatic climate platform."""
    climates = []
    zones_coo = get_coordinator(hass, ZONES, entry.unique_id)
    rooms_coo = get_coordinator(hass, ROOMS, entry.unique_id)
    ventilation_coo = get_coordinator(hass, VENTILATION, entry.unique_id)

    if zones_coo.data:
        for zone in zones_coo.data:
            if not zone.rbr and zone.enabled:
                climates.append(ZoneClimate(zones_coo, zone, ventilation_coo.data))

    if rooms_coo.data:
        rbr_zone = [zone for zone in zones_coo.data if zone.rbr][0]
        for room in rooms_coo.data:
            climates.append(RoomClimate(rooms_coo, zones_coo, room, rbr_zone))

    _LOGGER.info("Adding %s climate entities", len(climates))

    async_add_entities(climates)

    if len(climates) > 0:
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

    def __init__(
        self,
        coordinator: MultimaticCoordinator,
        comp_id,
    ):
        """Initialize entity."""
        super().__init__(coordinator, DOMAIN, comp_id)
        self._comp_id = comp_id

    async def set_quick_veto(self, **kwargs):
        """Set quick veto, called by service."""
        temperature = kwargs.get("temperature")
        duration = kwargs.get("duration", DEFAULT_QUICK_VETO_DURATION)
        await self.coordinator.api.set_quick_veto(self, temperature, duration)

    async def remove_quick_veto(self, **kwargs):
        """Remove quick veto, called by service."""
        await self.coordinator.api.remove_quick_veto(self)

    @property
    def active_mode(self) -> ActiveMode:
        """Get active mode of the climate."""
        return self.coordinator.api.get_active_mode(self.component)

    @property
    @abc.abstractmethod
    def component(self) -> Component:
        """Return the room or the zone."""

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.component

    @property
    def temperature_unit(self):
        """Return the unit of measurement used by the platform."""
        return TEMP_CELSIUS

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.active_mode.target

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self.component.temperature

    @property
    def name(self) -> str | None:
        """Return the name of the entity."""
        return self.component.name if self.component else None

    @property
    def is_aux_heat(self) -> bool | None:
        """Return true if aux heater."""
        return False

    @property
    def fan_mode(self) -> str | None:
        """Return the fan setting."""
        return None

    @property
    def fan_modes(self) -> list[str] | None:
        """Return the list of available fan modes."""
        return None

    @property
    def swing_mode(self) -> str | None:
        """Return the swing setting."""
        return None

    @property
    def swing_modes(self) -> list[str] | None:
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
    def target_temperature_high(self) -> float | None:
        """Return the highbound target temperature we try to reach."""
        return None

    @property
    def target_temperature_low(self) -> float | None:
        """Return the lowbound target temperature we try to reach."""
        return None


class RoomClimate(MultimaticClimate):
    """Climate for a room."""

    _MULTIMATIC_TO_HA: dict[Mode, list] = {
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

    def __init__(
        self, coordinator: MultimaticCoordinator, zone_coo, room: Room, zone: Zone
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator, room.name)
        self._zone_id = zone.id
        self._room_id = room.id
        self._supported_hvac = list(RoomClimate._HA_MODE_TO_MULTIMATIC.keys())
        self._supported_presets = list(RoomClimate._HA_PRESET_TO_MULTIMATIC.keys())
        self._zone_coo = zone_coo

    @property
    def component(self) -> Component:
        """Get the component."""
        return self.coordinator.find_component(self._room_id)

    @property
    def hvac_mode(self) -> str:
        """Get the hvac mode based on multimatic mode."""
        hvac_mode = RoomClimate._MULTIMATIC_TO_HA[self.active_mode.current][0]
        if not hvac_mode:
            if (
                self.active_mode.current
                in (OperatingModes.MANUAL, OperatingModes.QUICK_VETO)
                and self.hvac_action == CURRENT_HVAC_HEAT
            ):
                return HVAC_MODE_HEAT
        return hvac_mode

    @property
    def hvac_modes(self) -> list[str]:
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
    def zone(self):
        """Return the zone the current room belongs."""
        if self._zone_coo.data:
            return next(
                (zone for zone in self._zone_coo.data if zone.id == self._zone_id), None
            )
        return None

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        await self.coordinator.api.set_room_target_temperature(
            self, float(kwargs.get(ATTR_TEMPERATURE))
        )

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        mode = RoomClimate._HA_MODE_TO_MULTIMATIC[hvac_mode]
        await self.coordinator.api.set_room_operating_mode(self, mode)

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., home, away, temp.

        Requires SUPPORT_PRESET_MODE.
        """
        return RoomClimate._MULTIMATIC_TO_HA[self.active_mode.current][1]

    @property
    def preset_modes(self) -> list[str] | None:
        """Return a list of available preset modes.

        Requires SUPPORT_PRESET_MODE.
        """
        if self.active_mode.current == OperatingModes.QUICK_VETO:
            return self._supported_presets + [PRESET_QUICK_VETO]
        return self._supported_presets

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        mode = RoomClimate._HA_PRESET_TO_MULTIMATIC[preset_mode]
        await self.coordinator.api.set_room_operating_mode(self, mode)

    @property
    def hvac_action(self) -> str | None:
        """Return the current running hvac operation if supported.

        Need to be one of CURRENT_HVAC_*.
        """
        if (
            self.zone
            and self.zone.active_function == ActiveFunction.HEATING
            and self.component.temperature < self.active_mode.target
        ):
            return _FUNCTION_TO_HVAC_ACTION[ActiveFunction.HEATING]
        return _FUNCTION_TO_HVAC_ACTION[ActiveFunction.STANDBY]

    @property
    def current_humidity(self) -> int | None:
        """Return the current humidity."""
        return self.component.humidity


class ZoneClimate(MultimaticClimate):
    """Climate for a zone."""

    _MULTIMATIC_TO_HA: dict[Mode, list] = {
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

    def __init__(
        self, coordinator: MultimaticCoordinator, zone: Zone, ventilation
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator, zone.id)

        self._supported_hvac = list(ZoneClimate._HA_MODE_TO_MULTIMATIC.keys())
        self._supported_presets = list(ZoneClimate._HA_PRESET_TO_MULTIMATIC.keys())

        if not zone.cooling:
            self._supported_presets.remove(PRESET_COOLING_ON)
            self._supported_presets.remove(PRESET_COOLING_FOR_X_DAYS)

        if not ventilation:
            self._supported_hvac.remove(HVAC_MODE_FAN_ONLY)

        self._zone_id = zone.id

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""
        attr = {}
        if self.active_mode == QuickModes.COOLING_FOR_X_DAYS:
            attr.update(
                {"cooling_for_x_days_duration": self.active_mode.current.duration}
            )
        return attr

    @property
    def component(self) -> Component:
        """Return the room."""
        return self.coordinator.find_component(self._zone_id)

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
    def hvac_modes(self) -> list[str]:
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

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)

        if temp and temp != self.active_mode.target:
            _LOGGER.debug("Setting target temp to %s", temp)
            await self.coordinator.api.set_zone_target_temperature(self, temp)
        else:
            _LOGGER.debug("Nothing to do")

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        mode = ZoneClimate._HA_MODE_TO_MULTIMATIC[hvac_mode]
        await self.coordinator.api.set_zone_operating_mode(self, mode)

    @property
    def hvac_action(self) -> str | None:
        """Return the current running hvac operation if supported.

        Need to be one of CURRENT_HVAC_*.
        """
        return _FUNCTION_TO_HVAC_ACTION.get(self.component.active_function)

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., home, away, temp."""
        return ZoneClimate._MULTIMATIC_TO_HA[self.active_mode.current][1]

    @property
    def preset_modes(self) -> list[str] | None:
        """Return a list of available preset modes."""
        if self.active_mode.current == OperatingModes.QUICK_VETO:
            return self._supported_presets + [PRESET_QUICK_VETO]
        return self._supported_presets

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        mode = ZoneClimate._HA_PRESET_TO_MULTIMATIC[preset_mode]
        await self.coordinator.api.set_zone_operating_mode(self, mode)
