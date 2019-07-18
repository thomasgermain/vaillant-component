"""
Interfaces with Vaillant sensors.
"""
import logging
from abc import ABC

from vr900connector.model import BoilerStatus, Room, Component

from homeassistant.const import TEMP_CELSIUS
from homeassistant.components.sensor import DEVICE_CLASS_TEMPERATURE, DOMAIN, DEVICE_CLASS_PRESSURE

from . import HUB, BaseVaillantEntity, CONF_SENSOR_ROOM_TEMPERATURE,  CONF_SENSOR_ZONE_TEMPERATURE,\
    CONF_SENSOR_OUTDOOR_TEMPERATURE, CONF_SENSOR_HOT_WATER_TEMPERATURE, CONF_SENSOR_BOILER_WATER_TEMPERATURE, \
    CONF_SENSOR_BOILER_WATER_PRESSURE

PRESSURE_BAR = 'bar'

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Vaillant sensor platform."""
    sensors = []
    HUB.update_system()

    if HUB.system:
        if HUB.system.outdoor_temperature and HUB.config[CONF_SENSOR_OUTDOOR_TEMPERATURE]:
            sensors.append(VaillantOutdoorTemperatureSensor(HUB.system.outdoor_temperature))

        if HUB.system.boiler_status:
            if HUB.config[CONF_SENSOR_BOILER_WATER_TEMPERATURE]:
                sensors.append(VaillantBoilerTemperatureSensor(HUB.system.boiler_status))
            if HUB.config[CONF_SENSOR_BOILER_WATER_PRESSURE]:
                sensors.append(VaillantBoilerWaterPressureSensor(HUB.system.boiler_status))

        if HUB.config[CONF_SENSOR_ZONE_TEMPERATURE]:
            for zone in HUB.system.zones:
                if not zone.rbr:
                    sensors.append(VaillantTemperatureSensor(zone))

        if HUB.config[CONF_SENSOR_ROOM_TEMPERATURE]:
            for room in HUB.system.rooms:
                sensors.append(VaillantTemperatureSensor(room))

        if HUB.system.hot_water and HUB.config[CONF_SENSOR_HOT_WATER_TEMPERATURE]:
            sensors.append(VaillantTemperatureSensor(HUB.system.hot_water))

    _LOGGER.info("Adding %s sensor entities", len(sensors))

    async_add_entities(sensors)


class BaseVaillantTemperatureSensor(BaseVaillantEntity, ABC):

    @property
    def unit_of_measurement(self):
        return TEMP_CELSIUS


class VaillantTemperatureSensor(BaseVaillantTemperatureSensor):
    """Temperature sensor of a vaillant component (HotWater, Zone or Room)"""

    def __init__(self, component):
        if isinstance(component, Room):
            super().__init__(DOMAIN, DEVICE_CLASS_TEMPERATURE, component.name, component.name)
        else:
            super().__init__(DOMAIN, DEVICE_CLASS_TEMPERATURE, component.id, component.name)
        self._component: Component = component

    @property
    def state(self):
        return self._component.current_temperature

    @property
    def available(self):
        return self._component is not None

    async def vaillant_update(self):
        new_component = HUB.find_component(self._component)
        if new_component:
            _LOGGER.debug("New / old temperature: %s / %s", new_component.current_temperature,
                          self._component.current_temperature)
        else:
            _LOGGER.debug("Component with id %s doesn't exist anymore", self._component.id)

        self._component = new_component


class VaillantOutdoorTemperatureSensor(BaseVaillantTemperatureSensor):
    """Outdoor temperature sensor"""

    def __init__(self, outdoor_temp):
        super().__init__(DOMAIN, DEVICE_CLASS_TEMPERATURE, 'outdoor', 'Outdoor')
        self._outdoor_temp = outdoor_temp

    @property
    def state(self):
        return self._outdoor_temp

    @property
    def available(self):
        return HUB.system.outdoor_temperature is not None

    async def vaillant_update(self):
        _LOGGER.debug("New / old temperature: %s / %s", HUB.system.outdoor_temperature, self._outdoor_temp)
        self._outdoor_temp = HUB.system.outdoor_temperature


class VaillantBoilerWaterPressureSensor(BaseVaillantEntity):

    def __init__(self, boiler_status: BoilerStatus):
        super().__init__(DOMAIN, DEVICE_CLASS_PRESSURE, boiler_status.device_name, boiler_status.device_name)
        self._boiler_status = boiler_status

    @property
    def state(self):
        return self._boiler_status.water_pressure

    @property
    def available(self):
        return self._boiler_status is not None

    @property
    def unit_of_measurement(self):
        return PRESSURE_BAR

    async def vaillant_update(self):
        self._boiler_status = HUB.system.boiler_status


class VaillantBoilerTemperatureSensor(BaseVaillantTemperatureSensor):

    def __init__(self, boiler_status: BoilerStatus):
        super().__init__(DOMAIN, DEVICE_CLASS_TEMPERATURE, boiler_status.device_name, boiler_status.device_name)
        self._boiler_status = boiler_status

    @property
    def state(self):
        return self._boiler_status.current_temperature

    @property
    def available(self):
        return self._boiler_status is not None

    async def vaillant_update(self):
        self._boiler_status = HUB.system.boiler_status
