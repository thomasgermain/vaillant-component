"""Interfaces with multimatic sensors."""

from __future__ import annotations

import logging

from pymultimatic.model import EmfReport, Report

from homeassistant.components.sensor import (
    DOMAIN,
    SensorStateClass,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.const import (
    ENERGY_WATT_HOUR,
    TEMP_CELSIUS,
)
from homeassistant.helpers.typing import StateType

from .const import EMF_REPORTS, OUTDOOR_TEMP, REPORTS
from .coordinator import MultimaticCoordinator
from .entities import MultimaticEntity
from .utils import get_coordinator
from homeassistant.helpers.entity import EntityCategory

_LOGGER = logging.getLogger(__name__)

UNIT_TO_DEVICE_CLASS = {
    "bar": SensorDeviceClass.PRESSURE,
    "ppm": SensorDeviceClass.CO2,
    "Wh": SensorDeviceClass.ENERGY,
    "°C": SensorDeviceClass.TEMPERATURE,
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the multimatic sensors."""
    sensors = []
    outdoor_temp_coo = get_coordinator(hass, OUTDOOR_TEMP, entry.unique_id)
    reports_coo = get_coordinator(hass, REPORTS, entry.unique_id)
    emf_reports_coo = get_coordinator(hass, EMF_REPORTS, entry.unique_id)

    if outdoor_temp_coo.data:
        sensors.append(OutdoorTemperatureSensor(outdoor_temp_coo))

    if reports_coo.data:
        sensors.extend(ReportSensor(reports_coo, report) for report in reports_coo.data)

    if emf_reports_coo.data:
        sensors.extend(
            EmfReportSensor(emf_reports_coo, report) for report in emf_reports_coo.data
        )

    _LOGGER.info("Adding %s sensor entities", len(sensors))

    async_add_entities(sensors)
    return True


class OutdoorTemperatureSensor(MultimaticEntity, SensorEntity):
    """Outdoor temperature sensor."""

    def __init__(self, coordinator: MultimaticCoordinator) -> None:
        """Initialize entity."""
        super().__init__(coordinator, DOMAIN, "outdoor_temperature")

    @property
    def native_value(self) -> StateType:
        """Return the state of the entity."""
        return self.coordinator.data

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.coordinator.data is not None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of this entity, if any."""
        return TEMP_CELSIUS

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Outdoor temperature"

    @property
    def device_class(self) -> str:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return SensorDeviceClass.TEMPERATURE

    @property
    def state_class(self) -> str | None:
        """Return the state class of this entity."""
        return SensorStateClass.MEASUREMENT

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return the category of the entity, if any."""
        return EntityCategory.DIAGNOSTIC


class ReportSensor(MultimaticEntity, SensorEntity):
    """Report sensor."""

    def __init__(self, coordinator: MultimaticCoordinator, report: Report) -> None:
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
        return next(
            (
                report
                for report in self.coordinator.data
                if report.id == self._report_id
            ),
            None,
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the entity."""
        return self.report.value

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.report is not None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of this entity, if any."""
        return self._unit

    @property
    def device_info(self):
        """Return device specific attributes."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "Vaillant",
            "model": self.report.device_id,
        }

    @property
    def state_class(self) -> str | None:
        """Return the state class of this entity, from STATE_CLASSES, if any."""
        return SensorStateClass.MEASUREMENT

    @property
    def device_class(self) -> str | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._class

    @property
    def name(self) -> str | None:
        """Return the name of the entity."""
        return self._name

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return the category of the entity, if any."""
        return EntityCategory.DIAGNOSTIC


class EmfReportSensor(MultimaticEntity, SensorEntity):
    """Emf Report sensor."""

    def __init__(self, coordinator: MultimaticCoordinator, report: EmfReport) -> None:
        """Init entity."""
        self._device_id = f"{report.device_id}_{report.function}_{report.energyType}"
        self._name = f"{report.device_name} {report.function} {report.energyType}"
        MultimaticEntity.__init__(self, coordinator, DOMAIN, self._device_id)

    @property
    def report(self):
        """Get the current report based on the id."""
        return next(
            (
                report
                for report in self.coordinator.data
                if f"{report.device_id}_{report.function}_{report.energyType}"
                == self._device_id
            ),
            None,
        )

    @property
    def native_value(self):
        """Return the state of the entity."""
        return self.report.value

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.report is not None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of this entity, if any."""
        return ENERGY_WATT_HOUR

    @property
    def device_info(self):
        """Return device specific attributes."""
        return {
            "identifiers": {(DOMAIN, self.report.device_id)},
            "name": self.report.device_name,
            "manufacturer": "Vaillant",
            "model": self.report.device_id,
        }

    @property
    def device_class(self) -> str | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return SensorDeviceClass.ENERGY

    @property
    def name(self) -> str | None:
        """Return the name of the entity."""
        return self._name

    @property
    def state_class(self) -> str:
        """Return the state class of this entity."""
        return SensorStateClass.TOTAL_INCREASING

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return the category of the entity, if any."""
        return EntityCategory.DIAGNOSTIC
