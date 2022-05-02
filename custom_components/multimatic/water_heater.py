"""Interfaces with multimatic water heater."""
import logging

from pymultimatic.model import HotWater, OperatingModes, QuickModes

from homeassistant.components.water_heater import (
    DOMAIN,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS

from .const import DHW
from .coordinator import MultimaticCoordinator
from .entities import MultimaticEntity
from .utils import get_coordinator

_LOGGER = logging.getLogger(__name__)

SUPPORTED_FLAGS = (
    WaterHeaterEntityFeature.TARGET_TEMPERATURE
    | WaterHeaterEntityFeature.OPERATION_MODE
    | WaterHeaterEntityFeature.AWAY_MODE
)
ATTR_CURRENT_TEMPERATURE = "current_temperature"
ATTR_TIME_PROGRAM = "time_program"

AWAY_MODES = [
    OperatingModes.OFF,
    QuickModes.HOLIDAY,
    QuickModes.ONE_DAY_AWAY,
    QuickModes.SYSTEM_OFF,
]


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up water_heater platform."""
    entities = []
    coordinator = get_coordinator(hass, DHW, entry.unique_id)

    if coordinator.data and coordinator.data.hotwater:
        entities.append(MultimaticWaterHeater(coordinator))

    async_add_entities(entities)
    return True


class MultimaticWaterHeater(MultimaticEntity, WaterHeaterEntity):
    """Represent the multimatic water heater."""

    def __init__(self, coordinator: MultimaticCoordinator) -> None:
        """Initialize entity."""
        super().__init__(coordinator, DOMAIN, coordinator.data.hotwater.id)
        self._operations = {mode.name: mode for mode in HotWater.MODES}
        self._name = coordinator.data.hotwater.name

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def component(self):
        """Return multimatic component."""
        return self.coordinator.data.hotwater

    @property
    def active_mode(self):
        """Return multimatic component's active mode."""
        return self.coordinator.api.get_active_mode(self.component)

    @property
    def supported_features(self):
        """Return the list of supported features.

        !! It could be misleading here, since when heater is not heating,
        target temperature if fixed (35 °C) - The API doesn't allow to change
        this setting. It means if the user wants to change the target
        temperature, it will always be the target temperature when the
        heater is on function. See example below:

        1. Target temperature when heater is off is 35 (this is a fixed
        setting)
        2. Target temperature when heater is on is for instance 50 (this is a
        configurable setting)
        3. While heater is off, user changes target_temperature to 45. It will
        actually change the target temperature from 50 to 45
        4. While heater is off, user will still see 35 in UI
        (even if he changes to 45 before)
        5. When heater will go on, user will see the target temperature he set
         at point 3 -> 45.

        Maybe I can remove the SUPPORT_TARGET_TEMPERATURE flag if the heater
        is off, but it means the user will be able to change the target
         temperature only when the heater is ON (which seems odd to me)
        """
        if self.active_mode != QuickModes.HOLIDAY:
            return SUPPORTED_FLAGS
        return 0

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.component is not None

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
    def min_temp(self):
        """Return the minimum temperature."""
        return HotWater.MIN_TARGET_TEMP

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return HotWater.MAX_TARGET_TEMP

    @property
    def current_operation(self):
        """Return current operation ie. eco, electric, performance, ..."""
        return self.active_mode.current.name

    @property
    def operation_list(self):
        """Return current operation ie. eco, electric, performance, ..."""
        if self.active_mode.current != QuickModes.HOLIDAY:
            return list(self._operations.keys())
        return []

    @property
    def is_away_mode_on(self):
        """Return true if away mode is on."""
        return self.active_mode.current in AWAY_MODES

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        target_temp = float(kwargs.get(ATTR_TEMPERATURE))
        await self.coordinator.api.set_hot_water_target_temperature(self, target_temp)

    async def async_set_operation_mode(self, operation_mode):
        """Set new target operation mode."""
        if operation_mode in self._operations.keys():
            mode = self._operations[operation_mode]
            await self.coordinator.api.set_hot_water_operating_mode(self, mode)
        else:
            _LOGGER.debug("Operation mode %s is unknown", operation_mode)

    async def async_turn_away_mode_on(self):
        """Turn away mode on."""
        await self.coordinator.api.set_hot_water_operating_mode(
            self, OperatingModes.OFF
        )

    async def async_turn_away_mode_off(self):
        """Turn away mode off."""
        await self.coordinator.api.set_hot_water_operating_mode(
            self, OperatingModes.AUTO
        )
