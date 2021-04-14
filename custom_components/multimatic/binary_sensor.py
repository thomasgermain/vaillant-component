"""Interfaces with Multimatic binary sensors."""

import logging

from pymultimatic.model import Device, OperatingModes, QuickModes, Room, SettingModes

from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_CONNECTIVITY,
    DEVICE_CLASS_LOCK,
    DEVICE_CLASS_POWER,
    DEVICE_CLASS_PROBLEM,
    DEVICE_CLASS_WINDOW,
    DOMAIN,
    BinarySensorEntity,
)
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.util import slugify

from . import ApiHub
from .const import DOMAIN as MULTIMATIC, HUB
from .entities import MultimaticEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the multimatic binary sensor platform."""
    sensors = []
    hub: ApiHub = hass.data[MULTIMATIC][entry.unique_id][HUB]
    if hub.data:
        if hub.data.dhw and hub.data.dhw.circulation:
            sensors.append(CirculationSensor(hub))

        if hub.data.boiler_status:
            sensors.append(BoilerStatus(hub))

        if hub.data.info:
            sensors.append(BoxOnline(hub))
            sensors.append(BoxUpdate(hub))

        for room in hub.data.rooms:
            sensors.append(RoomWindow(hub, room))
            for device in room.devices:
                if device.device_type == "VALVE":
                    sensors.append(RoomDeviceChildLock(hub, device, room))

                sensors.append(RoomDeviceBattery(hub, device, room))
                sensors.append(RoomDeviceConnectivity(hub, device, room))

        sensors.extend(
            [HolidayModeSensor(hub), QuickModeSensor(hub), MultimaticErrors(hub)]
        )

    _LOGGER.info("Adding %s binary sensor entities", len(sensors))

    async_add_entities(sensors)
    return True


class CirculationSensor(MultimaticEntity, BinarySensorEntity):
    """Binary sensor for circulation running on or not."""

    def __init__(self, hub: ApiHub):
        """Initialize entity."""
        super().__init__(
            hub,
            DOMAIN,
            "dhw circulation",
            "Circulation",
            DEVICE_CLASS_POWER,
            False,
        )

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""

        return (
            self.active_mode.current == OperatingModes.ON
            or self.active_mode.sub == SettingModes.ON
            or self.active_mode.current == QuickModes.HOTWATER_BOOST
        )

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.component is not None

    @property
    def active_mode(self):
        """Return the active mode of the circulation."""
        return self.coordinator.data.get_active_mode_circulation()

    @property
    def component(self):
        """Return the circulation."""
        return self.coordinator.data.dhw.circulation


class RoomWindow(MultimaticEntity, BinarySensorEntity):
    """multimatic window binary sensor."""

    def __init__(self, hub: ApiHub, room: Room):
        """Initialize entity."""
        super().__init__(hub, DOMAIN, room.name, room.name, DEVICE_CLASS_WINDOW)
        self._room = room

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.coordinator.find_component(self._room).window_open

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self._room is not None


class RoomDeviceEntity(MultimaticEntity, BinarySensorEntity):
    """Base class for ambisense device."""

    def __init__(self, hub: ApiHub, device: Device, room: Room, device_class) -> None:
        """Initialize device."""
        MultimaticEntity.__init__(
            self, hub, DOMAIN, device.sgtin, device.name, device_class
        )
        self.room = room
        self.device = device

    @property
    def device_info(self):
        """Return device specific attributes."""
        return {
            "identifiers": {(MULTIMATIC, self.device.sgtin)},
            "name": self.device.name,
            "manufacturer": "Vaillant",
            "model": self.device.device_type,
        }

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {
            "device_id": self.device.sgtin,
            "battery_low": self.device.battery_low,
            "connected": not self.device.radio_out_of_reach,
        }

    def find_device(self):
        """Find a device in a room."""
        if self.room:
            for device in self.coordinator.find_component(self.room).devices:
                if device.sgtin == self.device.sgtin:
                    return device

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.find_device() is not None


class RoomDeviceChildLock(RoomDeviceEntity):
    """Binary sensor for valve child lock.

    At multimatic API, the lock is set at a room level, but it applies to all
    devices inside a room.
    """

    def __init__(self, hub: ApiHub, device: Device, room: Room):
        """Initialize entity."""
        super().__init__(hub, device, room, DEVICE_CLASS_LOCK)

    @property
    def is_on(self):
        """According to the doc, true means unlock, false lock."""
        return not self.coordinator.find_component(self.room).child_lock


class RoomDeviceBattery(RoomDeviceEntity):
    """Represent a device battery."""

    def __init__(self, hub: ApiHub, device: Device, room: Room):
        """Initialize entity."""
        super().__init__(hub, device, room, DEVICE_CLASS_BATTERY)

    @property
    def is_on(self):
        """According to the doc, true means normal, false low."""
        return self.find_device().battery_low


class RoomDeviceConnectivity(RoomDeviceEntity):
    """Device in room is out of reach or not."""

    def __init__(self, hub: ApiHub, device: Device, room: Room):
        """Initialize entity."""
        super().__init__(hub, device, room, DEVICE_CLASS_CONNECTIVITY)

    @property
    def is_on(self):
        """According to the doc, true means connected, false disconnected."""
        return not self.find_device().radio_out_of_reach


class VRBoxEntity(MultimaticEntity, BinarySensorEntity):
    """multimatic gateway device (ex: VR920)."""

    def __init__(self, hub: ApiHub, device_class, name, comp_id):
        """Initialize entity."""
        MultimaticEntity.__init__(self, hub, DOMAIN, comp_id, name, device_class, False)

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

    def __init__(self, hub: ApiHub):
        """Init."""
        super().__init__(
            hub,
            DEVICE_CLASS_POWER,
            "Multimatic system update",
            "multimatic_system_update",
        )

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return not self.coordinator.data.info.is_up_to_date


class BoxOnline(VRBoxEntity):
    """Check if box is online."""

    def __init__(self, hub: ApiHub):
        """Init."""
        super().__init__(
            hub,
            DEVICE_CLASS_CONNECTIVITY,
            "multimatic_system_online",
            "Multimatic system Online",
        )

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.coordinator.data.info.is_online


class BoilerStatus(MultimaticEntity, BinarySensorEntity):
    """Check if there is some error."""

    def __init__(self, hub: ApiHub):
        """Initialize entity."""
        MultimaticEntity.__init__(
            self,
            hub,
            DOMAIN,
            hub.data.boiler_status.device_name,
            hub.data.boiler_status.device_name,
            DEVICE_CLASS_PROBLEM,
            False,
        )
        self._boiler_id = slugify(hub.data.boiler_status.device_name)

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.boiler_status is not None and self.boiler_status.is_error

    @property
    def state_attributes(self):
        """Return the state attributes."""
        if self.boiler_status is not None:
            return {
                "status_code": self.boiler_status.status_code,
                "title": self.boiler_status.title,
                "timestamp": self.boiler_status.timestamp,
            }
        return None

    @property
    def device_info(self):
        """Return device specific attributes."""
        if self.boiler_status is not None:
            return {
                "identifiers": {(MULTIMATIC, self._boiler_id, self.coordinator.serial)},
                "name": self.boiler_status.device_name,
                "manufacturer": "Vaillant",
                "model": self.boiler_status.device_name,
            }
        return None

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        if self.boiler_status is not None:
            return {"device_id": self._boiler_id, "error": self.boiler_status.is_error}
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.boiler_status is not None

    @property
    def boiler_status(self):
        """Return the boiler status."""
        return self.coordinator.data.boiler_status


class MultimaticErrors(MultimaticEntity, BinarySensorEntity):
    """Check if there is any error message from system."""

    def __init__(self, hub: ApiHub):
        """Init."""
        super().__init__(
            hub,
            DOMAIN,
            "multimatic_errors",
            "Multimatic Errors",
            DEVICE_CLASS_PROBLEM,
            False,
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


class HolidayModeSensor(MultimaticEntity, BinarySensorEntity):
    """Binary sensor for holiday mode."""

    def __init__(self, hub: ApiHub):
        """Init."""
        super().__init__(
            hub,
            DOMAIN,
            "multimatic_holiday",
            "Multimatic holiday",
            DEVICE_CLASS_POWER,
            False,
        )

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
        return {}

    @property
    def listening(self):
        """Return whether this entity is listening for system changes or not."""
        return True


class QuickModeSensor(MultimaticEntity, BinarySensorEntity):
    """Binary sensor for holiday mode."""

    def __init__(self, hub: ApiHub):
        """Init."""
        super().__init__(
            hub,
            DOMAIN,
            "multimatic_quick_mode",
            "Multimatic quick mode",
            DEVICE_CLASS_POWER,
            False,
        )

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.coordinator.data.quick_mode is not None

    @property
    def state_attributes(self):
        """Return the state attributes."""
        if self.is_on:
            return {"quick_mode": self.coordinator.data.quick_mode.name}
        return {}

    @property
    def listening(self):
        """Return whether this entity is listening for system changes or not."""
        return True
