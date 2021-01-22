"""Interfaces with multimatic sensors."""
import logging

from pymultimatic.model import Report

from homeassistant.components.sensor import (
    DEVICE_CLASS_PRESSURE,
    DEVICE_CLASS_TEMPERATURE,
    DOMAIN,
)
from homeassistant.const import TEMP_CELSIUS

from . import ApiHub
from .const import DOMAIN as MULTIMATIC, HUB
from .entities import MultimaticEntity

_LOGGER = logging.getLogger(__name__)

UNIT_TO_DEVICE_CLASS = {
    "bar": DEVICE_CLASS_PRESSURE,
    "ppm": "",
    "°C": DEVICE_CLASS_TEMPERATURE,
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the multimatic sensors."""
    sensors = []
    hub = hass.data[MULTIMATIC][entry.unique_id][HUB]

    if hub.system:
        if hub.system.outdoor_temperature:
            sensors.append(OutdoorTemperatureSensor(hub))

        for report in hub.system.reports:
            sensors.append(ReportSensor(hub, report))

    _LOGGER.info("Adding %s sensor entities", len(sensors))

    async_add_entities(sensors)
    return True


class OutdoorTemperatureSensor(MultimaticEntity):
    """Outdoor temperature sensor."""

    def __init__(self, hub: ApiHub):
        """Initialize entity."""
        super().__init__(hub, DOMAIN, "outdoor", "Outdoor", DEVICE_CLASS_TEMPERATURE)
        self._outdoor_temp = hub.system.outdoor_temperature

    @property
    def state(self):
        """Return the state of the entity."""
        return self._outdoor_temp

    @property
    def available(self):
        """Return True if entity is available."""
        return self._outdoor_temp is not None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return TEMP_CELSIUS

    async def async_custom_update(self):
        """Update specific for multimatic."""
        _LOGGER.debug(
            "New / old temperature: %s / %s",
            self.coordinator.system.outdoor_temperature,
            self._outdoor_temp,
        )
        self._outdoor_temp = self.coordinator.system.outdoor_temperature


class ReportSensor(MultimaticEntity):
    """Report sensor."""

    def __init__(self, hub: ApiHub, report: Report):
        """Init entity."""
        device_class = UNIT_TO_DEVICE_CLASS.get(report.unit, None)
        if not device_class:
            _LOGGER.warning("No device class for %s", report.unit)
        MultimaticEntity.__init__(
            self, hub, DOMAIN, report.id, report.name, device_class, False
        )
        self.report = report
        self._report_id = report.id

    async def async_custom_update(self):
        """Update specific for multimatic."""
        self.report = self._find_report()

    def _find_report(self):
        for report in self.coordinator.system.reports:
            if self._report_id == report.id:
                return report
        return None

    @property
    def state(self):
        """Return the state of the entity."""
        return self.report.value

    @property
    def available(self):
        """Return True if entity is available."""
        return self.report is not None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self.report.unit

    @property
    def device_info(self):
        """Return device specific attributes."""
        if self.report is not None:
            return {
                "identifiers": {
                    (DOMAIN, self.report.device_id, self.coordinator.serial)
                },
                "name": self.report.device_name,
                "manufacturer": "Vaillant",
            }
        return None
