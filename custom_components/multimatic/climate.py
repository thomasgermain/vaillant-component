"""Interfaces with Multimatic climate."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
import logging
from typing import Any

from pymultimatic.model import (
    ActiveFunction,
    ActiveMode,
    Component,
    HotWater,
    Mode,
    OperatingModes,
    QuickModes,
    Room,
    Zone,
)

from homeassistant.components.climate import (
    DOMAIN,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_COMFORT,
    PRESET_HOME,
    PRESET_NONE,
    PRESET_SLEEP,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SERVICES
from .const import (
    CONF_APPLICATION,
    DEFAULT_QUICK_VETO_DURATION,
    DHW,
    DOMAIN as MULTIMATIC,
    PRESET_COOLING_FOR_X_DAYS,
    PRESET_COOLING_ON,
    PRESET_DAY,
    PRESET_HOLIDAY,
    PRESET_MANUAL,
    PRESET_PARTY,
    PRESET_QUICK_VETO,
    PRESET_SYSTEM_OFF,
    ROOMS,
    SENSO,
    VENTILATION,
    ZONES,
)
from .coordinator import MultimaticCoordinator
from .entities import MultimaticEntity
from .service import SERVICE_REMOVE_QUICK_VETO, SERVICE_SET_QUICK_VETO
from .utils import get_coordinator

_LOGGER = logging.getLogger(__name__)

_FUNCTION_TO_HVAC_ACTION: dict[ActiveFunction, HVACAction] = {
    ActiveFunction.COOLING: HVACAction.COOLING,
    ActiveFunction.HEATING: HVACAction.HEATING,
    ActiveFunction.STANDBY: HVACAction.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the multimatic climate platform."""
    climates: list[MultimaticClimate] = []
    zones_coo = get_coordinator(hass, ZONES, entry.entry_id)
    rooms_coo = get_coordinator(hass, ROOMS, entry.entry_id)
    dhw_coo = get_coordinator(hass, DHW, entry.entry_id)

    ventilation_coo = get_coordinator(hass, VENTILATION, entry.entry_id)
    system_application = SENSO if entry.data[CONF_APPLICATION] == SENSO else MULTIMATIC

    if zones_coo.data:
        for zone in zones_coo.data:
            if not zone.rbr and zone.enabled:
                climates.append(
                    build_zone_climate(
                        zones_coo, zone, ventilation_coo.data, system_application
                    )
                )

    if rooms_coo.data:
        rbr_zone = next((zone for zone in zones_coo.data if zone.rbr), None)
        for room in rooms_coo.data:
            climates.append(RoomClimate(rooms_coo, zones_coo, room, rbr_zone))

    if dhw_coo.data:
        climates.append(DHWClimate(dhw_coo))

    _LOGGER.info("Adding %s climate entities", len(climates))

    async_add_entities(climates)

    if len(climates) > 0:
        platform = entity_platform.async_get_current_platform()
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


class MultimaticClimate(MultimaticEntity, ClimateEntity, ABC):
    """Base class for climate."""

    def __init__(
        self,
        coordinator: MultimaticCoordinator,
        comp_id,
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator, DOMAIN, comp_id)
        self._comp_id = comp_id
        self._supported_hvac = list(self._ha_mode().keys())
        self._supported_presets = list(self._ha_preset().keys())

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
    @abstractmethod
    def component(self) -> Component:
        """Return the room or the zone."""

    @abstractmethod
    def _ha_mode(self):
        pass

    @abstractmethod
    def _multimatic_mode(self):
        pass

    @abstractmethod
    def _ha_preset(self):
        pass

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return super().available and self.component

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return UnitOfTemperature.CELSIUS

    @property
    def target_temperature(self) -> float:
        """Return the temperature we try to reach."""
        return self.active_mode.target

    @property
    def current_temperature(self) -> float:
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

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available hvac operation modes."""
        return self._supported_hvac

    @property
    def preset_modes(self) -> list[str] | None:
        """Return a list of available preset modes.

        Requires SUPPORT_PRESET_MODE.
        """

        mapping = self._multimatic_mode().get(self.active_mode.current)
        if (
            mapping is not None
            and mapping[1] is not None
            and mapping[1] not in self._supported_presets
        ):
            return self._supported_presets + [mapping[1]]
        return self._supported_presets

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., home, away, temp."""
        return self._multimatic_mode()[self.active_mode.current][1]

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features."""
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
        )


class RoomClimate(MultimaticClimate):
    """Climate for a room."""

    _MULTIMATIC_TO_HA: dict[Mode, list] = {
        OperatingModes.AUTO: [HVACMode.AUTO, PRESET_COMFORT],
        OperatingModes.OFF: [HVACMode.OFF, PRESET_NONE],
        OperatingModes.QUICK_VETO: [None, PRESET_QUICK_VETO],
        QuickModes.SYSTEM_OFF: [HVACMode.OFF, PRESET_SYSTEM_OFF],
        QuickModes.HOLIDAY: [HVACMode.OFF, PRESET_HOLIDAY],
        OperatingModes.MANUAL: [None, PRESET_MANUAL],
    }

    _HA_MODE_TO_MULTIMATIC = {
        HVACMode.AUTO: OperatingModes.AUTO,
        HVACMode.OFF: OperatingModes.OFF,
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
        self._zone_id = zone.id if zone else None
        self._room_id = room.id
        self._zone_coo = zone_coo

    def _ha_mode(self):
        return RoomClimate._HA_MODE_TO_MULTIMATIC

    def _multimatic_mode(self):
        return RoomClimate._MULTIMATIC_TO_HA

    def _ha_preset(self):
        return RoomClimate._HA_PRESET_TO_MULTIMATIC

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device specific attributes."""
        devices = self.component.devices
        if len(devices) == 1:  # Can't link an entity to multiple devices
            return DeviceInfo(
                identifiers={(MULTIMATIC, devices[0].sgtin)},
                name=devices[0].name,
                manufacturer="Vaillant",
                model=devices[0].device_type,
            )
        return None

    @property
    def component(self) -> Room:
        """Get the component."""
        return self.coordinator.find_component(self._room_id)

    @property
    def hvac_mode(self) -> HVACMode:
        """Get the hvac mode based on multimatic mode."""
        hvac_mode = RoomClimate._MULTIMATIC_TO_HA[self.active_mode.current][0]
        if not hvac_mode:
            if self.active_mode.current in (
                OperatingModes.MANUAL,
                OperatingModes.QUICK_VETO,
            ):
                if self.hvac_action == HVACAction.HEATING:
                    return HVACMode.HEAT
                return HVACMode.OFF
        return hvac_mode

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return Room.MIN_TARGET_TEMP

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return Room.MAX_TARGET_TEMP

    @property
    def zone(self):
        """Return the zone the current room belongs."""
        if self._zone_coo.data and self._zone_id:
            return next(
                (zone for zone in self._zone_coo.data if zone.id == self._zone_id), None
            )
        return None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        await self.coordinator.api.set_room_target_temperature(
            self, kwargs.get(ATTR_TEMPERATURE)
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        mode = RoomClimate._HA_MODE_TO_MULTIMATIC[hvac_mode]
        await self.coordinator.api.set_room_operating_mode(self, mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        mode = RoomClimate._HA_PRESET_TO_MULTIMATIC[preset_mode]
        await self.coordinator.api.set_room_operating_mode(self, mode)

    @property
    def hvac_action(self) -> HVACAction:
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
        humidity = self.component.humidity
        return int(humidity) if humidity is not None else None


def build_zone_climate(
    coordinator: MultimaticCoordinator, zone: Zone, ventilation, application
) -> AbstractZoneClimate:
    """Create correct climate entity."""
    if application == MULTIMATIC:
        return ZoneClimate(coordinator, zone, ventilation)
    return ZoneClimateSenso(coordinator, zone, ventilation)


class AbstractZoneClimate(MultimaticClimate, ABC):
    """Abstract class for a climate for a zone."""

    def __init__(
        self, coordinator: MultimaticCoordinator, zone: Zone, ventilation
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator, zone.id)

        if not zone.cooling:
            self._supported_presets.remove(PRESET_COOLING_ON)
            self._supported_presets.remove(PRESET_COOLING_FOR_X_DAYS)
            self._supported_hvac.remove(HVACMode.COOL)

        if not ventilation:
            self._supported_hvac.remove(HVACMode.FAN_ONLY)

        self._zone_id = zone.id

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""
        attr = {}
        if self.active_mode.current == QuickModes.COOLING_FOR_X_DAYS:
            attr.update(
                {"cooling_for_x_days_duration": self.active_mode.current.duration}
            )
        return attr

    @property
    def component(self) -> Zone:
        """Return the zone."""
        return self.coordinator.find_component(self._zone_id)

    @property
    def hvac_mode(self) -> HVACMode:
        """Get the hvac mode based on multimatic mode."""
        current_mode = self.active_mode.current
        hvac_mode = self._multimatic_mode()[current_mode][0]
        if not hvac_mode:
            if (
                current_mode
                in [
                    OperatingModes.DAY,
                    OperatingModes.NIGHT,
                    QuickModes.PARTY,
                    OperatingModes.QUICK_VETO,
                ]
                and self.hvac_action == HVACAction.HEATING
            ):
                return HVACMode.HEAT
            if (
                self.preset_mode in (PRESET_COOLING_ON, PRESET_COOLING_FOR_X_DAYS)
                and self.hvac_action == HVACAction.COOLING
            ):
                return HVACMode.COOL
        return hvac_mode if hvac_mode else HVACMode.OFF

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return Zone.MIN_TARGET_HEATING_TEMP

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return Zone.MAX_TARGET_TEMP

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)

        if temp and temp != self.active_mode.target:
            _LOGGER.debug("Setting target temp to %s", temp)
            await self.coordinator.api.set_zone_target_temperature(self, temp)
        else:
            _LOGGER.debug("Nothing to do")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        mode = self._ha_mode()[hvac_mode]
        await self.coordinator.api.set_zone_operating_mode(self, mode)

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running hvac operation if supported.

        Need to be one of CURRENT_HVAC_*.
        """
        return _FUNCTION_TO_HVAC_ACTION.get(self.component.active_function)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        mode = self._ha_preset()[preset_mode]
        await self.coordinator.api.set_zone_operating_mode(self, mode)


class ZoneClimate(AbstractZoneClimate):
    """Climate for a MULTIMATIC zone."""

    _MULTIMATIC_TO_HA: dict[Mode, list] = {
        OperatingModes.AUTO: [HVACMode.AUTO, PRESET_COMFORT],
        OperatingModes.DAY: [None, PRESET_DAY],
        OperatingModes.NIGHT: [None, PRESET_SLEEP],
        OperatingModes.OFF: [HVACMode.OFF, PRESET_NONE],
        OperatingModes.ON: [None, PRESET_COOLING_ON],
        OperatingModes.QUICK_VETO: [None, PRESET_QUICK_VETO],
        QuickModes.ONE_DAY_AT_HOME: [HVACMode.AUTO, PRESET_HOME],
        QuickModes.PARTY: [None, PRESET_PARTY],
        QuickModes.VENTILATION_BOOST: [HVACMode.FAN_ONLY, PRESET_NONE],
        QuickModes.ONE_DAY_AWAY: [HVACMode.OFF, PRESET_AWAY],
        QuickModes.SYSTEM_OFF: [HVACMode.OFF, PRESET_SYSTEM_OFF],
        QuickModes.HOLIDAY: [HVACMode.OFF, PRESET_HOLIDAY],
        QuickModes.COOLING_FOR_X_DAYS: [None, PRESET_COOLING_FOR_X_DAYS],
    }

    _HA_MODE_TO_MULTIMATIC = {
        HVACMode.AUTO: OperatingModes.AUTO,
        HVACMode.OFF: OperatingModes.OFF,
        HVACMode.FAN_ONLY: QuickModes.VENTILATION_BOOST,
        HVACMode.COOL: QuickModes.COOLING_FOR_X_DAYS,
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

    def _ha_mode(self):
        return ZoneClimate._HA_MODE_TO_MULTIMATIC

    def _multimatic_mode(self):
        return ZoneClimate._MULTIMATIC_TO_HA

    def _ha_preset(self):
        return ZoneClimate._HA_PRESET_TO_MULTIMATIC


class ZoneClimateSenso(AbstractZoneClimate):
    """Climate for a SENSO zone."""

    _SENSO_TO_HA: dict[Mode, list] = {
        OperatingModes.TIME_CONTROLLED: [HVACMode.AUTO, PRESET_COMFORT],
        OperatingModes.DAY: [None, PRESET_DAY],
        OperatingModes.NIGHT: [None, PRESET_SLEEP],
        OperatingModes.OFF: [HVACMode.OFF, PRESET_NONE],
        OperatingModes.MANUAL: [None, PRESET_COOLING_ON],
        OperatingModes.QUICK_VETO: [None, PRESET_QUICK_VETO],
        QuickModes.ONE_DAY_AT_HOME: [HVACMode.AUTO, PRESET_HOME],
        QuickModes.PARTY: [None, PRESET_PARTY],
        QuickModes.VENTILATION_BOOST: [HVACMode.FAN_ONLY, PRESET_NONE],
        QuickModes.ONE_DAY_AWAY: [HVACMode.OFF, PRESET_AWAY],
        QuickModes.SYSTEM_OFF: [HVACMode.OFF, PRESET_SYSTEM_OFF],
        QuickModes.HOLIDAY: [HVACMode.OFF, PRESET_HOLIDAY],
        QuickModes.COOLING_FOR_X_DAYS: [None, PRESET_COOLING_FOR_X_DAYS],
    }
    _HA_MODE_TO_SENSO = {
        HVACMode.AUTO: OperatingModes.TIME_CONTROLLED,
        HVACMode.OFF: OperatingModes.OFF,
        HVACMode.FAN_ONLY: QuickModes.VENTILATION_BOOST,
        HVACMode.COOL: QuickModes.COOLING_FOR_X_DAYS,
    }

    _HA_PRESET_TO_SENSO = {
        PRESET_COMFORT: OperatingModes.TIME_CONTROLLED,
        PRESET_DAY: OperatingModes.DAY,
        PRESET_SLEEP: OperatingModes.NIGHT,
        PRESET_COOLING_ON: OperatingModes.MANUAL,
        PRESET_HOME: QuickModes.ONE_DAY_AT_HOME,
        PRESET_PARTY: QuickModes.PARTY,
        PRESET_AWAY: QuickModes.ONE_DAY_AWAY,
        PRESET_SYSTEM_OFF: QuickModes.SYSTEM_OFF,
        PRESET_COOLING_FOR_X_DAYS: QuickModes.COOLING_FOR_X_DAYS,
    }

    def _ha_mode(self):
        return ZoneClimateSenso._HA_MODE_TO_SENSO

    def _multimatic_mode(self):
        return ZoneClimateSenso._SENSO_TO_HA

    def _ha_preset(self):
        return ZoneClimateSenso._HA_PRESET_TO_SENSO


class DHWClimate(MultimaticClimate):
    """Climate entity representing DHW."""

    _HA_MODE_TO_MULTIMATIC = {
        HVACMode.OFF: OperatingModes.OFF,
        HVACMode.HEAT: OperatingModes.ON,
        HVACMode.AUTO: OperatingModes.AUTO,
    }

    _HA_PRESET_TO_MULTIMATIC = {
        PRESET_COMFORT: OperatingModes.AUTO,
        PRESET_BOOST: QuickModes.HOTWATER_BOOST,
    }

    _MULTIMATIC_TO_HA: dict[Mode, list] = {
        OperatingModes.OFF: [HVACMode.OFF, PRESET_NONE],
        QuickModes.HOLIDAY: [HVACMode.OFF, PRESET_AWAY],
        QuickModes.ONE_DAY_AWAY: [HVACMode.OFF, PRESET_AWAY],
        QuickModes.SYSTEM_OFF: [HVACMode.OFF, PRESET_SYSTEM_OFF],
        QuickModes.HOTWATER_BOOST: [HVACMode.HEAT, PRESET_BOOST],
        QuickModes.PARTY: [HVACMode.OFF, PRESET_HOME],
        OperatingModes.ON: [HVACMode.HEAT, PRESET_NONE],
        OperatingModes.AUTO: [HVACMode.AUTO, PRESET_COMFORT],
    }

    def __init__(self, coordinator: MultimaticCoordinator) -> None:
        """Initialize entity."""
        super().__init__(coordinator, coordinator.data.hotwater.id)

    async def set_quick_veto(self, **kwargs):
        """Set quick veto, called by service."""
        _LOGGER.info("Cannot set quick veto for hotwater")

    async def remove_quick_veto(self, **kwargs):
        """Remove quick veto, called by service."""
        _LOGGER.info("Cannot remove quick veto for hotwater")

    @property
    def component(self) -> Component:
        """Return the DHW component."""
        return self.coordinator.data.hotwater

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return HotWater.MIN_TARGET_TEMP

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return HotWater.MAX_TARGET_TEMP

    def _ha_mode(self):
        return DHWClimate._HA_MODE_TO_MULTIMATIC

    def _multimatic_mode(self):
        return DHWClimate._MULTIMATIC_TO_HA

    def _ha_preset(self):
        return DHWClimate._HA_PRESET_TO_MULTIMATIC

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current running hvac operation if supported."""
        should_heat = (
            self.current_temperature is None
            or self.current_temperature < self.target_temperature
        )
        return (
            HVACAction.HEATING
            if should_heat and self.hvac_mode != HVACMode.OFF
            else HVACAction.IDLE
        )

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return hvac operation ie. heat, cool mode."""
        return DHWClimate._MULTIMATIC_TO_HA[self.active_mode.current][0]

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode."""
        mode = DHWClimate._HA_PRESET_TO_MULTIMATIC[preset_mode]
        _LOGGER.info("Will set %s operation mode to hot water", mode)
        await self.coordinator.api.set_hot_water_operating_mode(self, mode)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        await self.coordinator.api.set_hot_water_target_temperature(
            self, kwargs.get(ATTR_TEMPERATURE)
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        mode = DHWClimate._HA_MODE_TO_MULTIMATIC[hvac_mode]
        await self.coordinator.api.set_hot_water_operating_mode(self, mode)
