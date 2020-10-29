"""Interfaces with Vaillant binary sensors."""

import logging

from pymultimatic.model import (
    Device,
    Error,
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
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import slugify

from . import ApiHub
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN as VAILLANT
from .entities import VaillantEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Vaillant binary sensor platform."""
    sensors = []
    hub: ApiHub = hass.data[VAILLANT]
    if hub.system:
        if hub.system.dhw and hub.system.dhw.circulation:
            sensors.append(CirculationSensor(hub))

        if hub.system.boiler_status:
            sensors.append(BoilerError(hub))

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

        handler = SystemErrorHandler(hub, hass, async_add_entities)
        async_track_time_interval(hass, handler.update, DEFAULT_SCAN_INTERVAL)
        await handler.update(None)

    _LOGGER.info("Adding %s binary sensor entities", len(sensors))

    async_add_entities(sensors, True)
    return True


class CirculationSensor(VaillantEntity, BinarySensorEntity):
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

    async def vaillant_update(self):
        """Update specific for vaillant."""
        self._circulation = self.hub.system.dhw.circulation
        self._active_mode = self.hub.system.get_active_mode_circulation()


class RoomWindow(VaillantEntity, BinarySensorEntity):
    """Vaillant window binary sensor."""

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

    async def vaillant_update(self):
        """Update specific for vaillant."""
        new_room: Room = self.hub.find_component(self._room)

        if new_room:
            _LOGGER.debug(
                "New / old state: %s / %s", new_room.child_lock, self._room.child_lock
            )
        else:
            _LOGGER.debug("Room %s doesn't exist anymore", self._room.id)
        self._room = new_room


class RoomDeviceEntity(VaillantEntity, BinarySensorEntity):
    """Base class for ambisense device."""

    def __init__(self, hub: ApiHub, device: Device, room: Room, device_class) -> None:
        """Initialize device."""
        VaillantEntity.__init__(
            self, hub, DOMAIN, device.sgtin, device.name, device_class
        )
        self.room = room
        self.device = device

    @property
    def device_info(self):
        """Return device specific attributes."""
        return {
            "identifiers": {(VAILLANT, self.device.sgtin)},
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

    async def vaillant_update(self):
        """Update specific for vaillant."""
        new_room: Room = self.hub.find_component(self.room)
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

    At vaillant API, the lock is set at a room level, but it applies to all
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


class VRBoxEntity(VaillantEntity, BinarySensorEntity):
    """Vaillant gateway device (ex: VR920)."""

    def __init__(self, hub: ApiHub, info: SystemInfo, device_class, name, comp_id):
        """Initialize entity."""
        VaillantEntity.__init__(self, hub, DOMAIN, comp_id, name, device_class, False)
        self.system_info = info

    @property
    def device_info(self):
        """Return device specific attributes."""
        return {
            "identifiers": {(VAILLANT, self.system_info.serial_number)},
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

    async def vaillant_update(self):
        """Update specific for vaillant."""
        system_info: SystemInfo = self.hub.system.info

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
            hub, info, DEVICE_CLASS_POWER, "System update", "system_update"
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
            hub, info, DEVICE_CLASS_CONNECTIVITY, "System Online", "system_online"
        )

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return self.system_info.is_online


class BoilerError(VaillantEntity, BinarySensorEntity):
    """Check if there is some error."""

    def __init__(self, hub: ApiHub):
        """Initialize entity."""
        self._boiler_status = hub.system.boiler_status
        VaillantEntity.__init__(
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

    async def vaillant_update(self):
        """Update specific for vaillant."""
        _LOGGER.debug("new boiler status is %s", self.hub.system.boiler_status)
        self._boiler_status = self.hub.system.boiler_status

    @property
    def device_info(self):
        """Return device specific attributes."""
        if self._boiler_status is not None:
            return {
                "identifiers": {(VAILLANT, self._boiler_id)},
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


class SystemErrorHandler:
    """Handler responsible for creating dynamically error binary sensor."""

    def __init__(self, hub: ApiHub, hass, async_add_entities) -> None:
        """Init."""
        self.hub = hub
        self._hass = hass
        self._async_add_entities = async_add_entities

    async def update(self, time):
        """Check for error. It doesn't do IO."""
        if self.hub.system.errors:
            reg = await self._hass.helpers.entity_registry.async_get_registry()

            sensors = []
            for error in self.hub.system.errors:
                binary_sensor = VaillantSystemError(self.hub, error)
                if not reg.async_is_registered(binary_sensor.entity_id):
                    sensors.append(binary_sensor)

            if sensors:
                self._async_add_entities(sensors)


class VaillantSystemError(VaillantEntity, BinarySensorEntity):
    """Check if there is any error message from system."""

    def __init__(self, hub: ApiHub, error: Error):
        """Init."""
        self._error = error
        super().__init__(
            hub,
            DOMAIN,
            "error_" + error.status_code,
            error.title,
            DEVICE_CLASS_PROBLEM,
            False,
        )

    @property
    def state_attributes(self):
        """Return the state attributes."""
        return {
            "status_code": self._error.status_code,
            "title": self._error.title,
            "timestamp": self._error.timestamp,
            "description": self._error.description,
            "device_name": self._error.device_name,
        }

    async def vaillant_update(self):
        """Update specific for vaillant.

        Special attention during the update, the entity can remove itself
        from registry if the error disappear from vaillant system.
        """
        errors = {e.status_code: e for e in self.hub.system.errors}

        if self._error.status_code in [e.status_code for e in list(errors.values())]:
            self._error = errors.get(self._error.status_code)
        else:
            async_call_later(self.hass, 0.1, self._remove)

    async def _remove(self, *_):
        """Remove entity itself."""
        await self.async_remove()

        reg = await self.hass.helpers.entity_registry.async_get_registry()
        entity_id = reg.async_get_entity_id(DOMAIN, VAILLANT, self.unique_id)
        if entity_id:
            reg.async_remove(entity_id)

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return True


class HolidayModeSensor(VaillantEntity, BinarySensorEntity):
    """Binary sensor for holiday mode."""

    def __init__(self, hub: ApiHub):
        """Init."""
        super().__init__(hub, DOMAIN, "holiday", "holiday", DEVICE_CLASS_POWER, False)
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

    async def vaillant_update(self):
        """Update specific for vaillant."""
        self._holiday = self.hub.system.holiday


class QuickModeSensor(VaillantEntity, BinarySensorEntity):
    """Binary sensor for holiday mode."""

    def __init__(self, hub: ApiHub):
        """Init."""
        super().__init__(
            hub, DOMAIN, "quick_mode", "quick_mode", DEVICE_CLASS_POWER, False
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

    async def vaillant_update(self):
        """Update specific for vaillant."""
        self._quick_mode = self.hub.system.quick_mode
