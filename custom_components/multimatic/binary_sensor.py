"""Interfaces with Multimatic binary sensors."""

import logging

from pymultimatic.model import Device, OperatingModes, QuickModes, Room, SettingModes

from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_CONNECTIVITY,
    DEVICE_CLASS_LOCK,
    DEVICE_CLASS_PROBLEM,
    DEVICE_CLASS_WINDOW,
    DOMAIN,
    BinarySensorEntity,
)
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.util import slugify

from . import MultimaticDataUpdateCoordinator
from .const import COORDINATOR, DOMAIN as MULTIMATIC
from .entities import MultimaticEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the multimatic binary sensor platform."""
    sensors = []
    coordinator: MultimaticDataUpdateCoordinator = hass.data[MULTIMATIC][
        entry.unique_id
    ][COORDINATOR]
    if coordinator.data:
        if coordinator.data.dhw and coordinator.data.dhw.circulation:
            sensors.append(CirculationSensor(coordinator))

        if coordinator.data.boiler_status:
            sensors.append(BoilerStatus(coordinator))

        if coordinator.data.info:
            sensors.append(BoxOnline(coordinator))
            sensors.append(BoxUpdate(coordinator))

        for room in coordinator.data.rooms:
            sensors.append(RoomWindow(coordinator, room))
            for device in room.devices:
                if device.device_type == "VALVE":
                    sensors.append(RoomDeviceChildLock(coordinator, device, room))

                sensors.append(RoomDeviceBattery(coordinator, device))
                sensors.append(RoomDeviceConnectivity(coordinator, device))

        sensors.extend(
            [
                HolidayModeSensor(coordinator),
                QuickModeSensor(coordinator),
                MultimaticErrors(coordinator),
            ]
        )

    _LOGGER.info("Adding %s binary sensor entities", len(sensors))

    async_add_entities(sensors)
    return True


class CirculationSensor(MultimaticEntity, BinarySensorEntity):
    """Binary sensor for circulation running on or not."""

    def __init__(self, coordinator: MultimaticDataUpdateCoordinator) -> None:
        """Initialize entity."""
        super().__init__(coordinator, DOMAIN, "dhw_circulation")
        self._name = coordinator.data.dhw.circulation.name

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        a_mode = self.active_mode
        return (
            a_mode.current in (OperatingModes.ON, QuickModes.HOTWATER_BOOST)
            or a_mode.sub == SettingModes.ON
        )

    @property
    def available(self):
        """Return True if entity is available."""
        return (
            super().available
            and self.coordinator.data.dhw is not None
            and self.coordinator.data.dhw.circulation is not None
        )

    @property
    def active_mode(self):
        """Return the active mode of the circulation."""
        return self.coordinator.data.get_active_mode_circulation()

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name


class RoomWindow(MultimaticEntity, BinarySensorEntity):
    """multimatic window binary sensor."""

    def __init__(
        self, coordinator: MultimaticDataUpdateCoordinator, room: Room
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator, DOMAIN, f"{room.name}_{DEVICE_CLASS_WINDOW}")
        self._room_id = room.id

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.room.window_open

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.room is not None

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_WINDOW

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self.room.name if self.room else None

    @property
    def room(self):
        """Return the room."""
        return self.coordinator.get_room(self._room_id)


class RoomDeviceEntity(MultimaticEntity, BinarySensorEntity):
    """Base class for ambisense device."""

    def __init__(
        self, coordinator: MultimaticDataUpdateCoordinator, device: Device, extra_id
    ) -> None:
        """Initialize device."""
        MultimaticEntity.__init__(
            self, coordinator, DOMAIN, f"{device.sgtin}_{extra_id}"
        )
        self._sgtin = device.sgtin

    @property
    def device_info(self):
        """Return device specific attributes."""
        device = self.device
        return {
            "identifiers": {(MULTIMATIC, device.sgtin)},
            "name": device.name,
            "manufacturer": "Vaillant",
            "model": device.device_type,
        }

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        device = self.device
        return {
            "device_id": device.sgtin,
            "battery_low": device.battery_low,
            "connected": not device.radio_out_of_reach,
        }

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.device is not None

    @property
    def device(self):
        """Return the device."""
        return self.coordinator.get_room_device(self._sgtin)


class RoomDeviceChildLock(RoomDeviceEntity):
    """Binary sensor for valve child lock.

    At multimatic API, the lock is set at a room level, but it applies to all
    devices inside a room.
    """

    def __init__(
        self, coordinator: MultimaticDataUpdateCoordinator, device: Device, room: Room
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator, device, DEVICE_CLASS_LOCK)
        self._room_id = room.id

    @property
    def is_on(self):
        """According to the doc, true means unlock, false lock."""
        return not self.room.child_lock

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.room is not None

    @property
    def room(self):
        """Return the room."""
        return self.coordinator.get_room(self._room_id)

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_LOCK


class RoomDeviceBattery(RoomDeviceEntity):
    """Represent a device battery."""

    def __init__(
        self, coordinator: MultimaticDataUpdateCoordinator, device: Device
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator, device, DEVICE_CLASS_BATTERY)

    @property
    def is_on(self):
        """According to the doc, true means normal, false low."""
        return self.device.battery_low

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_BATTERY


class RoomDeviceConnectivity(RoomDeviceEntity):
    """Device in room is out of reach or not."""

    def __init__(
        self, coordinator: MultimaticDataUpdateCoordinator, device: Device
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator, device, DEVICE_CLASS_CONNECTIVITY)

    @property
    def is_on(self):
        """According to the doc, true means connected, false disconnected."""
        return not self.device.radio_out_of_reach

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_CONNECTIVITY


class VRBoxEntity(MultimaticEntity, BinarySensorEntity):
    """multimatic gateway device (ex: VR920)."""

    def __init__(self, coordinator: MultimaticDataUpdateCoordinator, comp_id):
        """Initialize entity."""
        MultimaticEntity.__init__(self, coordinator, DOMAIN, comp_id)

    @property
    def device_info(self):
        """Return device specific attributes."""
        return {
            "identifiers": {(MULTIMATIC, self.system_info.serial_number)},
            "connections": {(CONNECTION_NETWORK_MAC, self.system_info.mac_ethernet)},
            "name": self.system_info.gateway,
            "manufacturer": "Vaillant",
            "model": self.system_info.gateway,
            "sw_version": self.system_info.firmware,
        }

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {
            "serial_number": self.system_info.serial_number,
            "connected": self.system_info.is_online,
            "up_to_date": self.system_info.is_up_to_date,
        }

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.system_info is not None

    @property
    def system_info(self):
        """Return the system information."""
        return self.coordinator.data.info


class BoxUpdate(VRBoxEntity):
    """Update binary sensor."""

    def __init__(self, coordinator: MultimaticDataUpdateCoordinator) -> None:
        """Init."""
        super().__init__(
            coordinator,
            "Multimatic_system_update",
        )

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return not self.coordinator.data.info.is_up_to_date


class BoxOnline(VRBoxEntity):
    """Check if box is online."""

    def __init__(self, coordinator: MultimaticDataUpdateCoordinator) -> None:
        """Init."""
        super().__init__(coordinator, "multimatic_system_online")

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.coordinator.data.info.is_online

    @property
    def name(self):
        """Return the name of the entity."""
        return "Multimatic system Online"

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_CONNECTIVITY


class BoilerStatus(MultimaticEntity, BinarySensorEntity):
    """Check if there is some error."""

    def __init__(self, coordinator: MultimaticDataUpdateCoordinator) -> None:
        """Initialize entity."""
        MultimaticEntity.__init__(
            self,
            coordinator,
            DOMAIN,
            coordinator.data.boiler_status.device_name,
        )
        self._boiler_id = slugify(coordinator.data.boiler_status.device_name)
        self._name = coordinator.data.boiler_status.device_name

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.boiler_status is not None and self.boiler_status.is_error

    @property
    def state_attributes(self):
        """Return the state attributes."""
        return {
            "status_code": self.boiler_status.status_code,
            "title": self.boiler_status.title,
            "timestamp": self.boiler_status.timestamp,
        }

    @property
    def device_info(self):
        """Return device specific attributes."""
        return {
            "identifiers": {
                (MULTIMATIC, self._boiler_id, self.coordinator.data.info.serial_number)
            },
            "name": self._name,
            "manufacturer": "Vaillant",
            "model": self._name,
        }

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        if self.available:
            return {"device_id": self._boiler_id, "error": self.boiler_status.is_error}
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.boiler_status is not None

    @property
    def name(self):
        """Return the name of the entity."""
        return self._name

    @property
    def boiler_status(self):
        """Return the boiler status."""
        return self.coordinator.data.boiler_status

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_PROBLEM


class MultimaticErrors(MultimaticEntity, BinarySensorEntity):
    """Check if there is any error message from system."""

    def __init__(self, coordinator: MultimaticDataUpdateCoordinator) -> None:
        """Init."""
        super().__init__(
            coordinator,
            DOMAIN,
            "multimatic_errors",
        )

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return len(self.coordinator.data.errors) > 0

    @property
    def state_attributes(self):
        """Return the state attributes."""
        state_attributes = {}
        for error in self.coordinator.data.errors:
            state_attributes.update(
                {
                    error.status_code: {
                        "status_code": error.status_code,
                        "title": error.title,
                        "timestamp": error.timestamp,
                        "description": error.description,
                        "device_name": error.device_name,
                    }
                }
            )
        return state_attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data.errors is not None

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_PROBLEM

    @property
    def name(self):
        """Return the name of the entity."""
        return "Multimatic Errors"


class HolidayModeSensor(MultimaticEntity, BinarySensorEntity):
    """Binary sensor for holiday mode."""

    def __init__(self, coordinator: MultimaticDataUpdateCoordinator) -> None:
        """Init."""
        super().__init__(coordinator, DOMAIN, "multimatic_holiday")

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return (
            self.coordinator.data.holiday and self.coordinator.data.holiday.is_applied
        )

    @property
    def state_attributes(self):
        """Return the state attributes."""
        if self.is_on:
            return {
                "start_date": self.coordinator.data.holiday.start_date.isoformat(),
                "end_date": self.coordinator.data.holiday.end_date.isoformat(),
                "temperature": self.coordinator.data.holiday.target,
            }

    @property
    def listening(self):
        """Return whether this entity is listening for system changes or not."""
        return True

    @property
    def name(self):
        """Return the name of the entity."""
        return "Multimatic holiday"


class QuickModeSensor(MultimaticEntity, BinarySensorEntity):
    """Binary sensor for holiday mode."""

    def __init__(self, coordinator: MultimaticDataUpdateCoordinator) -> None:
        """Init."""
        super().__init__(coordinator, DOMAIN, "multimatic_quick_mode")

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.coordinator.data.quick_mode is not None

    @property
    def state_attributes(self):
        """Return the state attributes."""
        if self.is_on:
            return {"quick_mode": self.coordinator.data.quick_mode.name}

    @property
    def listening(self):
        """Return whether this entity is listening for system changes or not."""
        return True

    @property
    def name(self):
        """Return the name of the entity."""
        return "Multimatic quick mode"
