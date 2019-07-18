import logging

from vr900connector.model import System, HotWater, QuickMode, HeatingMode

from . import HUB, BaseVaillantEntity, CONF_WATER_HEATER

from homeassistant.helpers.temperature import display_temp as show_temp
from homeassistant.const import ATTR_TEMPERATURE, TEMP_CELSIUS, STATE_ON, STATE_OFF
from homeassistant.components.water_heater import (
    WaterHeaterDevice,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_AWAY_MODE,
    SUPPORT_OPERATION_MODE,
    ATTR_MIN_TEMP,
    ATTR_MAX_TEMP,
    ATTR_OPERATION_MODE,
    ATTR_OPERATION_LIST,
    ATTR_AWAY_MODE,
    DOMAIN
)

_LOGGER = logging.getLogger(__name__)

SUPPORTED_FLAGS = (SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE | SUPPORT_AWAY_MODE)
ATTR_CURRENT_TEMPERATURE = 'current_temperature'
ATTR_TIME_PROGRAM = 'time_program'


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    entities = []
    HUB.update_system()

    if HUB.system and HUB.system.hot_water and HUB.config[CONF_WATER_HEATER]:
        entity = VaillantWaterHeater(HUB.system)
        entities.append(entity)
        HUB.add_listener(entity)

    _LOGGER.info("Added water heater? %s", len(entities) > 0)
    async_add_entities(entities)


class VaillantWaterHeater(BaseVaillantEntity, WaterHeaterDevice):

    def __init__(self, system: System):
        super().__init__(DOMAIN, None, system.hot_water.id, system.hot_water.name)
        self._system = None
        self._active_mode = None
        self._refresh(system)

        mode_list = HotWater.MODES + QuickMode.for_hot_water()
        mode_list.remove(QuickMode.HOLIDAY)
        self._operation_list = [mode.name for mode in mode_list]

    @property
    def supported_features(self):
        """!! It could be misleading here, since when heater is not heating, target temperature if fixed (35 °C) -
        The API doesn't allow to change this setting.
        It means if the user wants to change the target temperature, it will always be the target temperature when the
        heater is on function. See example below:

        1. Target temperature when heater is off is 35 (this is a fixed setting)
        2. Target temperature when heater is on is for instance 50 (this is a configurable setting)
        3. While heater is off, user changes target_temperature to 45. It will actually change the target temperature
        from 50 to 45
        4. While heater is off, user will still see 35 on UI (even if he changes to 45 before)
        5. When heater will go on, user will see the target temperature he set at point 3 -> 45.

        Maybe I can remove the SUPPORT_TARGET_TEMPERATURE flag if the heater is off, but it means the user will be
        able to change the target temperature only when the heater is ON (which seems odd to me)
        """
        return SUPPORTED_FLAGS

    @property
    def available(self):
        return self._system.hot_water is not None

    @property
    def temperature_unit(self):
        return TEMP_CELSIUS

    @property
    def state_attributes(self):
        """
        I had to override this function in order to add the current temperature, all the other things remain the same
        """

        data = {
            ATTR_MIN_TEMP: show_temp(
                self.hass, self.min_temp, self.temperature_unit,
                self.precision),
            ATTR_MAX_TEMP: show_temp(
                self.hass, self.max_temp, self.temperature_unit,
                self.precision),
            ATTR_TEMPERATURE: show_temp(
                self.hass, self.target_temperature, self.temperature_unit,
                self.precision),
            ATTR_CURRENT_TEMPERATURE: show_temp(
                self.hass, self.temperature, self.temperature_unit,
                self.precision),
            ATTR_OPERATION_MODE: self.current_operation, ATTR_OPERATION_LIST: self.operation_list,
            ATTR_AWAY_MODE: STATE_ON if self.is_away_mode_on else STATE_OFF
            # ATTR_TIME_PROGRAM: self._system.hot_water.time_program
        }

        return data

    @property
    def target_temperature(self):
        _LOGGER.debug("target temperature is %s", self._active_mode.target_temperature)
        return self._active_mode.target_temperature

    @property
    def temperature(self):
        _LOGGER.debug("current temperature is %s", self._system.hot_water.current_temperature)
        return self._system.hot_water.current_temperature

    @property
    def min_temp(self):
        return HotWater.MIN_TEMP

    @property
    def max_temp(self):
        return HotWater.MAX_TEMP

    @property
    def current_operation(self):
        _LOGGER.debug("current_operation is %s", self._active_mode.current_mode)
        return self._active_mode.current_mode.name

    @property
    def operation_list(self):
        return self._operation_list

    @property
    def is_away_mode_on(self):
        return self._active_mode.current_mode == HeatingMode.OFF or self._system.holiday_mode.active

    def set_temperature(self, **kwargs):
        target_temp = float(kwargs.get(ATTR_TEMPERATURE))
        _LOGGER.debug("Trying to set target temp to %s", target_temp)
        # HUB will call sync update
        HUB.set_hot_water_target_temperature(self, self._system.hot_water, target_temp)

    def set_operation_mode(self, operation_mode):
        _LOGGER.debug("Will set new operation_mode %s", operation_mode)
        # HUB will call sync update
        HUB.set_hot_water_operation_mode(self, self._system.hot_water, operation_mode)

    def turn_away_mode_on(self):
        HUB.set_hot_water_operation_mode(self, self._system.hot_water, HeatingMode.OFF.name)

    def turn_away_mode_off(self):
        HUB.set_hot_water_operation_mode(self, self._system.hot_water, HeatingMode.AUTO.name)

    async def vaillant_update(self):
        self._refresh(HUB.system)

    def _refresh(self, system):
        self._system = system
        self._active_mode = self._system.get_active_mode_hot_water()
