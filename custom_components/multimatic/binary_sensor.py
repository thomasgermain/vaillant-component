"""Interfaces with Multimatic binary sensors."""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from pymultimatic.model import Device, OperatingModes, QuickModes, Room, SettingModes

from homeassistant.components.binary_sensor import (
    DOMAIN,
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import (
    ATTR_DURATION,
    DHW,
    DOMAIN as MULTIMATIC,
    FACILITY_DETAIL,
    GATEWAY,
    HOLIDAY_MODE,
    HVAC_STATUS,
    QUICK_MODE,
    ROOMS,
)
from .coordinator import MultimaticCoordinator
from .entities import MultimaticEntity
from .utils import get_coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the multimatic binary sensor platform."""
    sensors: list[MultimaticEntity] = []

    dhw_coo = get_coordinator(hass, DHW, entry.entry_id)
    if dhw_coo.data and dhw_coo.data.circulation:
        sensors.append(CirculationSensor(dhw_coo))

    hvac_coo = get_coordinator(hass, HVAC_STATUS, entry.entry_id)
    detail_coo = get_coordinator(hass, FACILITY_DETAIL, entry.entry_id)
    gw_coo = get_coordinator(hass, GATEWAY, entry.entry_id)
    if hvac_coo.data:
        sensors.append(BoxOnline(hvac_coo, detail_coo, gw_coo))
        sensors.append(BoxUpdate(hvac_coo, detail_coo, gw_coo))
        sensors.append(MultimaticErrors(hvac_coo))

        if hvac_coo.data.boiler_status:
            sensors.append(BoilerStatus(hvac_coo))

    rooms_coo = get_coordinator(hass, ROOMS, entry.entry_id)
    if rooms_coo.data:
        for room in rooms_coo.data:
            sensors.append(RoomWindow(rooms_coo, room))
            for device in room.devices:
                if device.device_type in ("VALVE", "THERMOSTAT"):
                    sensors.append(RoomDeviceChildLock(rooms_coo, device, room))
                sensors.append(RoomDeviceBattery(rooms_coo, device))
                sensors.append(RoomDeviceConnectivity(rooms_coo, device))

    sensors.extend(
        [
            HolidayModeSensor(get_coordinator(hass, HOLIDAY_MODE, entry.entry_id)),
            QuickModeSensor(get_coordinator(hass, QUICK_MODE, entry.entry_id)),
        ]
    )

    _LOGGER.info("Adding %s binary sensor entities", len(sensors))

    async_add_entities(sensors)


class CirculationSensor(MultimaticEntity, BinarySensorEntity):
    """Binary sensor for circulation running on or not."""

    def __init__(self, coordinator: MultimaticCoordinator) -> None:
        """Initialize entity."""
        super().__init__(coordinator, DOMAIN, "dhw_circulation")

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        a_mode = self.active_mode
        return a_mode.current in (
            OperatingModes.ON,
            QuickModes.HOTWATER_BOOST,
        ) or a_mode.sub in (SettingModes.ON, SettingModes.DAY)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            super().available
            and self.coordinator.data
            and self.coordinator.data.circulation
        )

    @property
    def active_mode(self):
        """Return the active mode of the circulation."""
        return self.coordinator.api.get_active_mode(self.coordinator.data.circulation)

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self.coordinator.data.circulation.name

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return BinarySensorDeviceClass.RUNNING


class RoomWindow(MultimaticEntity, BinarySensorEntity):
    """multimatic window binary sensor."""

    def __init__(self, coordinator: MultimaticCoordinator, room: Room) -> None:
        """Initialize entity."""
        super().__init__(
            coordinator, DOMAIN, f"{room.name}_{BinarySensorDeviceClass.WINDOW}"
        )
        self._room_id = room.id

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self.room.window_open

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return super().available and self.room

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return BinarySensorDeviceClass.WINDOW

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self.room.name if self.room else None

    @property
    def room(self) -> Room:
        """Return the room."""
        return self.coordinator.find_component(self._room_id)


class RoomDeviceEntity(MultimaticEntity, BinarySensorEntity):
    """Base class for ambisense device."""

    def __init__(
        self, coordinator: MultimaticCoordinator, device: Device, extra_id
    ) -> None:
        """Initialize device."""
        MultimaticEntity.__init__(
            self, coordinator, DOMAIN, f"{device.sgtin}_{extra_id}"
        )
        self._sgtin = device.sgtin

    @property
    def device_info(self) -> DeviceInfo:
        """Return device specific attributes."""
        device = self.device
        return DeviceInfo(
            identifiers={(MULTIMATIC, device.sgtin)},
            name=device.name,
            manufacturer="Vaillant",
            model=device.device_type,
        )

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the state attributes."""
        device = self.device
        return {
            "device_id": device.sgtin,
            "battery_low": device.battery_low,
            "connected": not device.radio_out_of_reach,
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return super().available and self.device

    @property
    def device(self):
        """Return the device."""
        for room in self.coordinator.data:
            for device in room.devices:
                if device.sgtin == self._sgtin:
                    return device
        return None

    @property
    def name(self) -> str | None:
        """Return the name of the entity."""
        return f"{self.device.name} {self.device_class}"


class RoomDeviceChildLock(RoomDeviceEntity):
    """Binary sensor for valve child lock.

    At multimatic API, the lock is set at a room level, but it applies to all
    devices inside a room.
    """

    def __init__(
        self, coordinator: MultimaticCoordinator, device: Device, room: Room
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator, device, BinarySensorDeviceClass.LOCK)
        self._room_id = room.id

    @property
    def is_on(self) -> bool:
        """According to the doc, true means unlock, false lock."""
        return not self.room.child_lock

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return super().available and self.room

    @property
    def room(self) -> Room:
        """Return the room."""
        return self.coordinator.find_component(self._room_id)

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return BinarySensorDeviceClass.LOCK


class RoomDeviceBattery(RoomDeviceEntity):
    """Represent a device battery."""

    def __init__(self, coordinator: MultimaticCoordinator, device: Device) -> None:
        """Initialize entity."""
        super().__init__(coordinator, device, BinarySensorDeviceClass.BATTERY)

    @property
    def is_on(self) -> bool:
        """According to the doc, true means normal, false low."""
        return self.device.battery_low

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return BinarySensorDeviceClass.BATTERY

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return the category of the entity, if any."""
        return EntityCategory.DIAGNOSTIC


class RoomDeviceConnectivity(RoomDeviceEntity):
    """Device in room is out of reach or not."""

    def __init__(self, coordinator: MultimaticCoordinator, device: Device) -> None:
        """Initialize entity."""
        super().__init__(coordinator, device, BinarySensorDeviceClass.CONNECTIVITY)

    @property
    def is_on(self) -> bool:
        """According to the doc, true means connected, false disconnected."""
        return not self.device.radio_out_of_reach

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return BinarySensorDeviceClass.CONNECTIVITY

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return the category of the entity, if any."""
        return EntityCategory.DIAGNOSTIC


class VRBoxEntity(MultimaticEntity, BinarySensorEntity):
    """multimatic gateway device (ex: VR920)."""

    def __init__(
        self,
        coord: MultimaticCoordinator,
        detail_coo: MultimaticCoordinator,
        gw_coo: MultimaticCoordinator,
        comp_id,
    ) -> None:
        """Initialize entity."""
        MultimaticEntity.__init__(self, coord, DOMAIN, comp_id)
        self._detail_coo = detail_coo
        self._gw_coo = gw_coo

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device specific attributes."""
        if self._detail_coo.data:
            detail = self._detail_coo.data
            return DeviceInfo(
                identifiers={(MULTIMATIC, detail.serial_number)},
                connections={(CONNECTION_NETWORK_MAC, detail.ethernet_mac)},
                name=self._gw_coo.data,
                manufacturer="Vaillant",
                model=self._gw_coo.data,
                sw_version=detail.firmware_version,
            )
        return None


class BoxUpdate(VRBoxEntity):
    """Update binary sensor."""

    def __init__(
        self,
        coord: MultimaticCoordinator,
        detail_coo: MultimaticCoordinator,
        gw_coo: MultimaticCoordinator,
    ) -> None:
        """Init."""
        super().__init__(
            coord,
            detail_coo,
            gw_coo,
            "Multimatic_system_update",
        )

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return not self.coordinator.data.is_up_to_date

    @property
    def name(self) -> str | None:
        """Return the name of the entity."""
        return "Multimatic system update"

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return the category of the entity, if any."""
        return EntityCategory.DIAGNOSTIC

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return BinarySensorDeviceClass.UPDATE


class BoxOnline(VRBoxEntity):
    """Check if box is online."""

    def __init__(
        self,
        coord: MultimaticCoordinator,
        detail_coo: MultimaticCoordinator,
        gw_coo: MultimaticCoordinator,
    ) -> None:
        """Init."""
        super().__init__(coord, detail_coo, gw_coo, "multimatic_system_online")

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self.coordinator.data.is_online

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Multimatic system Online"

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return BinarySensorDeviceClass.CONNECTIVITY


class BoilerStatus(MultimaticEntity, BinarySensorEntity):
    """Check if there is some error."""

    def __init__(self, coordinator: MultimaticCoordinator) -> None:
        """Initialize entity."""
        MultimaticEntity.__init__(
            self,
            coordinator,
            DOMAIN,
            coordinator.data.boiler_status.device_name,
        )
        self._name = coordinator.data.boiler_status.device_name
        self._boiler_id = slugify(self._name)

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self.boiler_status and self.boiler_status.is_error

    @property
    def state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if self.boiler_status:
            return {
                "status_code": self.boiler_status.status_code,
                "title": self.boiler_status.title,
                "timestamp": self.boiler_status.timestamp,
            }
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device specific attributes."""
        return DeviceInfo(
            identifiers={(MULTIMATIC, self._boiler_id)},
            name=self._name,
            manufacturer="Vaillant",
            model=self._name,
        )

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the state attributes."""
        if self.available:
            return {"device_id": self._boiler_id, "error": self.boiler_status.is_error}
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.boiler_status

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def boiler_status(self):
        """Return the boiler status."""
        return self.coordinator.data.boiler_status if self.coordinator.data else None

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return BinarySensorDeviceClass.PROBLEM


class MultimaticErrors(MultimaticEntity, BinarySensorEntity):
    """Check if there is any error message from system."""

    def __init__(self, coordinator: MultimaticCoordinator) -> None:
        """Init."""
        super().__init__(
            coordinator,
            DOMAIN,
            "multimatic_errors",
        )

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        if self.coordinator.data.errors:
            return len(self.coordinator.data.errors) > 0
        return False

    @property
    def state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        state_attributes = {}
        if self.coordinator.data.errors:
            errors = []
            for error in self.coordinator.data.errors:
                errors.append(
                    {
                        "status_code": error.status_code,
                        "title": error.title,
                        "timestamp": error.timestamp,
                        "description": error.description,
                        "device_name": error.device_name,
                    }
                )
            state_attributes["errors"] = errors
        return state_attributes

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return BinarySensorDeviceClass.PROBLEM

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Multimatic Errors"


class HolidayModeSensor(MultimaticEntity, BinarySensorEntity):
    """Binary sensor for holiday mode."""

    def __init__(self, coordinator: MultimaticCoordinator) -> None:
        """Init."""
        super().__init__(coordinator, DOMAIN, "multimatic_holiday")

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self.coordinator.data is not None and self.coordinator.data.is_applied

    @property
    def state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if self.is_on:
            return {
                "start_date": self.coordinator.data.start_date.isoformat(),
                "end_date": self.coordinator.data.end_date.isoformat(),
                "temperature": self.coordinator.data.target,
            }
        return None

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Multimatic holiday"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return BinarySensorDeviceClass.OCCUPANCY


class QuickModeSensor(MultimaticEntity, BinarySensorEntity):
    """Binary sensor for holiday mode."""

    def __init__(self, coordinator: MultimaticCoordinator) -> None:
        """Init."""
        super().__init__(coordinator, DOMAIN, "multimatic_quick_mode")

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self.coordinator.data is not None

    @property
    def state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        attrs = {}
        if self.is_on:
            attrs = {"quick_mode": self.coordinator.data.name}
            if self.coordinator.data.duration:
                attrs.update({ATTR_DURATION: self.coordinator.data.duration})
        return attrs

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Multimatic quick mode"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return BinarySensorDeviceClass.RUNNING
