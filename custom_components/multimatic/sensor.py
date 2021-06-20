"""Interfaces with multimatic sensors."""

from __future__ import annotations

import logging

from pymultimatic.model import Report

from homeassistant.components.sensor import (
    DEVICE_CLASS_PRESSURE,
    DEVICE_CLASS_TEMPERATURE,
    DOMAIN,
)
from homeassistant.const import TEMP_CELSIUS

from . import MultimaticDataUpdateCoordinator
from .const import COORDINATOR, DOMAIN as MULTIMATIC
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
    coordinator = hass.data[MULTIMATIC][entry.unique_id][COORDINATOR]

    if coordinator.data:
        if coordinator.data.outdoor_temperature:
            sensors.append(OutdoorTemperatureSensor(coordinator))

        sensors.extend(
            ReportSensor(coordinator, report) for report in coordinator.data.reports
        )

    _LOGGER.info("Adding %s sensor entities", len(sensors))

    async_add_entities(sensors)
    return True


class OutdoorTemperatureSensor(MultimaticEntity):
    """Outdoor temperature sensor."""

    def __init__(self, coordinator: MultimaticDataUpdateCoordinator) -> None:
        """Initialize entity."""
        super().__init__(coordinator, DOMAIN, "outdoor_temperature")

    @property
    def state(self):
        """Return the state of the entity."""
        return self.coordinator.data.outdoor_temperature

    @property
    def available(self):
        """Return True if entity is available."""
        return (
            super().available and self.coordinator.data.outdoor_temperature is not None
        )

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return TEMP_CELSIUS

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Outdoor temperature"

    @property
    def device_class(self) -> str:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_TEMPERATURE


class ReportSensor(MultimaticEntity):
    """Report sensor."""

    def __init__(
        self, coordinator: MultimaticDataUpdateCoordinator, report: Report
    ) -> None:
        """Init entity."""
        MultimaticEntity.__init__(self, coordinator, DOMAIN, report.id)
        self._report_id = report.id
        self._unit = report.unit
        self._name = report.name
        self._class = UNIT_TO_DEVICE_CLASS.get(report.unit, None)
        self._device_name = report.device_name
        self._device_id = report.device_id

    @property
    def report(self):
        """Get the current report based on the id."""
        return self.coordinator.get_report(self._report_id)

    @property
    def state(self):
        """Return the state of the entity."""
        return self.report.value

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.report is not None

    @property
    def unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of this entity, if any."""
        return self._unit

    @property
    def device_info(self):
        """Return device specific attributes."""
        return {
            "identifiers": {
                (
                    DOMAIN,
                    self._device_id,
                    self.coordinator.data.info.serial_number,
                )
            },
            "name": self._device_name,
            "manufacturer": "Vaillant",
        }

    @property
    def device_class(self) -> str | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._class

    @property
    def name(self) -> str | None:
        """Return the name of the entity."""
        return self._name
