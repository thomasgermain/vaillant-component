"""Interfaces with Multimatic binary sensors."""

import logging

from pymultimatic.model import (
    Device,
    OperatingModes,
    QuickModes,
    Room,
    SettingModes,
    SystemInfo,
)

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
    if hub.system:
        if hub.system.dhw and hub.system.dhw.circulation:
            sensors.append(CirculationSensor(hub))

        if hub.system.boiler_status:
            sensors.append(BoilerStatus(hub))

        if hub.system.info:
            sensors.append(BoxOnline(hub, hub.system.info))
            sensors.append(BoxUpdate(hub, hub.system.info))

        for room in hub.system.rooms:
            sensors.append(RoomWindow(hub, room))
            for device in room.devices:
                if device.device_type == "VALVE":
                    sensors.append(RoomDeviceChildLock(hub, device, room))

                sensors.append(RoomDeviceBattery(hub, device, room))
                sensors.append(RoomDeviceConnectivity(hub, device, room))

        entity = HolidayModeSensor(hub)
        sensors.append(entity)

        entity = QuickModeSensor(hub)
        sensors.append(entity)

        entity = MultimaticErrors(hub)
        sensors.append(entity)

    _LOGGER.info("Adding %s binary sensor entities", len(sensors))

    async_add_entities(sensors, True)
    return True


class CirculationSensor(MultimaticEntity, BinarySensorEntity):
    """Binary sensor for circulation running on or not."""

    def __init__(self, hub: ApiHub):
        """Initialize entity."""
        self._circulation = hub.system.dhw.circulation
        super().__init__(
            hub,
            DOMAIN,
            self._circulation.id,
            self._circulation.name,
            DEVICE_CLASS_POWER,
            False,
        )
        self._active_mode = None

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""

        return (
            self._active_mode.current == OperatingModes.ON
            or self._active_mode.sub == SettingModes.ON
            or self._active_mode.current == QuickModes.HOTWATER_BOOST
        )

    @property
    def available(self):
        """Return True if entity is available."""
        return self._circulation is not None

    async def async_custom_update(self):
        """Update specific for multimatic."""
        self._circulation = self.coordinator.system.dhw.circulation
        self._active_mode = self.coordinator.system.get_active_mode_circulation()


class RoomWindow(MultimaticEntity, BinarySensorEntity):
    """multimatic window binary sensor."""

    def __init__(self, hub: ApiHub, room: Room):
        """Initialize entity."""
        super().__init__(hub, DOMAIN, room.name, room.name, DEVICE_CLASS_WINDOW)
        self._room = room

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self._room.window_open

    @property
    def available(self):
        """Return True if entity is available."""
        return self._room is not None

    async def async_custom_update(self):
        """Update specific for multimatic."""
        new_room: Room = self.coordinator.find_component(self._room)

        if new_room:
            _LOGGER.debug(
                "New / old state: %s / %s", new_room.child_lock, self._room.child_lock
            )
        else:
            _LOGGER.debug("Room %s doesn't exist anymore", self._room.id)
        self._room = new_room


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

    # pylint: disable=no-self-use
    def _find_device(self, new_room: Room, sgtin: str):
        """Find a device in a room."""
        if new_room:
            for device in new_room.devices:
                if device.sgtin == sgtin:
                    return device

    @property
    def available(self):
        """Return True if entity is available."""
        return self.device is not None

    async def async_custom_update(self):
        """Update specific for multimatic."""
        new_room: Room = self.coordinator.find_component(self.room)
        new_device: Device = self._find_device(new_room, self.device.sgtin)

        if new_room:
            if new_device:
                _LOGGER.debug(
                    "New / old state: %s / %s",
                    new_device.battery_low,
                    self.device.battery_low,
                )
            else:
                _LOGGER.debug("Device %s doesn't exist anymore", self.device.sgtin)
        else:
            _LOGGER.debug("Room %s doesn't exist anymore", self.room.id)
        self.room = new_room
        self.device = new_device


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
        return not self.room.child_lock


class RoomDeviceBattery(RoomDeviceEntity):
    """Represent a device battery."""

    def __init__(self, hub: ApiHub, device: Device, room: Room):
        """Initialize entity."""
        super().__init__(hub, device, room, DEVICE_CLASS_BATTERY)

    @property
    def is_on(self):
        """According to the doc, true means normal, false low."""
        return self.device.battery_low


class RoomDeviceConnectivity(RoomDeviceEntity):
    """Device in room is out of reach or not."""

    def __init__(self, hub: ApiHub, device: Device, room: Room):
        """Initialize entity."""
        super().__init__(hub, device, room, DEVICE_CLASS_CONNECTIVITY)

    @property
    def is_on(self):
        """According to the doc, true means connected, false disconnected."""
        return not self.device.radio_out_of_reach


class VRBoxEntity(MultimaticEntity, BinarySensorEntity):
    """multimatic gateway device (ex: VR920)."""

    def __init__(self, hub: ApiHub, info: SystemInfo, device_class, name, comp_id):
        """Initialize entity."""
        MultimaticEntity.__init__(self, hub, DOMAIN, comp_id, name, device_class, False)
        self.system_info = info

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
        return self.system_info is not None

    async def async_custom_update(self):
        """Update specific for multimatic."""
        system_info: SystemInfo = self.coordinator.system.info

        if system_info:
            _LOGGER.debug(
                "Found new system status " "online? %s, up to date? %s",
                system_info.is_online,
                system_info.is_up_to_date,
            )
        else:
            _LOGGER.debug("System status doesn't exist anymore")
        self.system_info = system_info


class BoxUpdate(VRBoxEntity):
    """Update binary sensor."""

    def __init__(self, hub: ApiHub, info: SystemInfo):
        """Init."""
        super().__init__(
            hub,
            info,
            DEVICE_CLASS_POWER,
            "Multimatic system update",
            "multimatic_system_update",
        )

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return not self.system_info.is_up_to_date


class BoxOnline(VRBoxEntity):
    """Check if box is online."""

    def __init__(self, hub: ApiHub, info: SystemInfo):
        """Init."""
        super().__init__(
            hub,
            info,
            DEVICE_CLASS_CONNECTIVITY,
            "multimatic_system_online",
            "Multimatic system Online",
        )

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.system_info.is_online


class BoilerStatus(MultimaticEntity, BinarySensorEntity):
    """Check if there is some error."""

    def __init__(self, hub: ApiHub):
        """Initialize entity."""
        self._boiler_status = hub.system.boiler_status
        MultimaticEntity.__init__(
            self,
            hub,
            DOMAIN,
            self._boiler_status.device_name,
            self._boiler_status.device_name,
            DEVICE_CLASS_PROBLEM,
            False,
        )
        self._boiler_id = slugify(self._boiler_status.device_name)

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self._boiler_status is not None and self._boiler_status.is_error

    @property
    def state_attributes(self):
        """Return the state attributes."""
        if self._boiler_status is not None:
            return {
                "status_code": self._boiler_status.status_code,
                "title": self._boiler_status.title,
                "timestamp": self._boiler_status.timestamp,
            }
        return None

    async def async_custom_update(self):
        """Update specific for multimatic."""
        _LOGGER.debug("new boiler status is %s", self.coordinator.system.boiler_status)
        self._boiler_status = self.coordinator.system.boiler_status

    @property
    def device_info(self):
        """Return device specific attributes."""
        if self._boiler_status is not None:
            return {
                "identifiers": {(MULTIMATIC, self._boiler_id)},
                "name": self._boiler_status.device_name,
                "manufacturer": "Vaillant",
                "model": self._boiler_status.device_name,
            }
        return None

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        if self._boiler_status is not None:
            return {"device_id": self._boiler_id, "error": self._boiler_status.is_error}
        return None


class MultimaticErrors(MultimaticEntity, BinarySensorEntity):
    """Check if there is any error message from system."""

    def __init__(self, hub: ApiHub):
        """Init."""
        self._errors = hub.system.errors
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
        return len(self._errors) > 0

    async def async_custom_update(self):
        """Update specific for multimatic."""
        self._errors = self.coordinator.system.errors

    @property
    def state_attributes(self):
        """Return the state attributes."""
        state_attributes = {}
        for error in self._errors:
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
        self._holiday = hub.system.holiday

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self._holiday is not None and self._holiday.is_applied

    @property
    def state_attributes(self):
        """Return the state attributes."""
        if self.is_on:
            return {
                "start_date": self._holiday.start_date.isoformat(),
                "end_date": self._holiday.end_date.isoformat(),
                "temperature": self._holiday.target,
            }
        return {}

    async def async_custom_update(self):
        """Update specific for multimatic."""
        self._holiday = self.coordinator.system.holiday

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
        self._quick_mode = hub.system.quick_mode

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self._quick_mode is not None

    @property
    def state_attributes(self):
        """Return the state attributes."""
        if self.is_on:
            return {"quick_mode": self._quick_mode.name}
        return {}

    async def async_custom_update(self):
        """Update specific for multimatic."""
        self._quick_mode = self.coordinator.system.quick_mode

    @property
    def listening(self):
        """Return whether this entity is listening for system changes or not."""
        return True
