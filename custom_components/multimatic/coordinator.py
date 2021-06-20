"""Api hub and integration data."""
from datetime import timedelta
import logging

from pymultimatic.api import ApiError
from pymultimatic.model import (
    Circulation,
    HolidayMode,
    HotWater,
    Mode,
    OperatingModes,
    QuickMode,
    QuickModes,
    QuickVeto,
    Room,
    System,
    Zone,
    ZoneCooling,
    ZoneHeating,
)
import pymultimatic.systemmanager

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_SERIAL_NUMBER,
    DEFAULT_QUICK_VETO_DURATION,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SMART_PHONE_ID,
    DOMAIN,
    REFRESH_ENTITIES_EVENT,
)

_LOGGER = logging.getLogger(__name__)


async def check_authentication(hass, username, password, serial):
    """Check if provided username an password are corrects."""
    return await pymultimatic.systemmanager.SystemManager(
        username,
        password,
        async_get_clientsession(hass),
        DEFAULT_SMART_PHONE_ID,
        serial,
    ).login(True)


class MultimaticDataUpdateCoordinator(DataUpdateCoordinator[System]):
    """multimatic entry point for home-assistant."""

    def __init__(self, hass, entry: ConfigEntry):
        """Initialize hub."""

        username = entry.data[CONF_USERNAME]
        password = entry.data[CONF_PASSWORD]
        serial = entry.data.get(CONF_SERIAL_NUMBER)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
            update_method=self._fetch_data,
        )

        self._manager = pymultimatic.systemmanager.SystemManager(
            user=username,
            password=password,
            session=async_get_clientsession(hass),
            serial=serial,
        )

        self.fixed_serial = serial is not None

    async def authenticate(self):
        """Try to authenticate to the API."""
        try:
            return await self._manager.login(True)
        except ApiError as err:
            await self._log_error(err)
            return False

    async def request_hvac_update(self):
        """Request is not on the classic update since it won't fetch data.

        The request update will trigger something at multimatic API and it will
        ask data to your system.
        """
        try:
            _LOGGER.debug("Will request_hvac_update")
            await self._manager.request_hvac_update()
        except ApiError as err:
            if err.status == 409:
                _LOGGER.warning("Request_hvac_update is done too often")
            else:
                await self._log_error(err)
                await self.authenticate()

    async def _fetch_data(self):
        """Fetch multimatic system."""

        try:
            system = await self._manager.get_system()
            _LOGGER.debug("fetch_data successful")
            return system
        except ApiError as err:
            await self._log_error(err)
            if err.status < 500:
                await self._manager.logout()
                await self.authenticate()
            raise

    async def logout(self):
        """Logout from API."""

        try:
            await self._manager.logout()
        except ApiError:
            _LOGGER.warning("Cannot logout from multimatic API", exc_info=True)
            return False
        return True

    @staticmethod
    async def _log_error(api_err, exec_info=True):
        if api_err.status == 409:
            _LOGGER.warning(
                "Multimatic API: %s, status: %s, response: %s",
                api_err.message,
                api_err.status,
                api_err.response,
            )
        else:
            _LOGGER.error(
                "Error with multimatic API: %s, status: %s, response: %s",
                api_err.message,
                api_err.status,
                api_err.response,
                exc_info=exec_info,
            )

    def find_component(self, comp):
        """Find a component in the system with the given id, no IO is done."""

        if isinstance(comp, Zone):
            return self.get_zone(comp.id)
        if isinstance(comp, Room):
            return self.get_room(comp.id)
        if isinstance(comp, HotWater):
            if self.data.dhw.hotwater and self.data.dhw.hotwater.id == comp.id:
                return self.data.dhw.hotwater
        if isinstance(comp, Circulation):
            if self.data.dhw.circulation and self.data.dhw.circulation.id == comp.id:
                return self.data.dhw.circulation

        return None

    def get_room(self, room_id):
        """Get room by id."""
        return next((room for room in self.data.rooms if room.id == room_id), None)

    def get_room_device(self, sgtin):
        """Get device of a room."""
        for room in self.data.rooms:
            for device in room.devices:
                if device.sgtin == sgtin:
                    return device

    def get_report(self, report_id):
        """Get report id."""
        return next(
            (report for report in self.data.reports if report.id == report_id), None
        )

    def get_zone(self, zone_id):
        """Get zone by id."""
        return next((zone for zone in self.data.zones if zone.id == zone_id), None)

    async def set_hot_water_target_temperature(self, entity, target_temp):
        """Set hot water target temperature.

        * If there is a quick mode that impact dhw running on or holiday mode,
        remove it.

        * If dhw is ON or AUTO, modify the target temperature

        * If dhw is OFF, change to ON and set target temperature
        """

        hotwater = entity.component

        touch_system = await self._remove_quick_mode_or_holiday(entity)

        current_mode = self.data.get_active_mode_hot_water(hotwater).current

        if current_mode == OperatingModes.OFF:
            await self._manager.set_hot_water_operating_mode(
                hotwater.id, OperatingModes.ON
            )
        await self._manager.set_hot_water_setpoint_temperature(hotwater.id, target_temp)

        self.data.hot_water = hotwater
        await self._refresh(touch_system, entity)

    async def set_room_target_temperature(self, entity, target_temp):
        """Set target temperature for a room.

        * If there is a quick mode that impact room running on or holiday mode,
        remove it.

        * If the room is in MANUAL mode, simply modify the target temperature.

        * if the room is not in MANUAL mode, create à quick veto.
        """

        touch_system = await self._remove_quick_mode_or_holiday(entity)

        room = entity.component
        current_mode = self.data.get_active_mode_room(room).current

        if current_mode == OperatingModes.MANUAL:
            await self._manager.set_room_setpoint_temperature(room.id, target_temp)
            room.target_temperature = target_temp
        else:
            if current_mode == OperatingModes.QUICK_VETO:
                await self._manager.remove_room_quick_veto(room.id)

            qveto = QuickVeto(DEFAULT_QUICK_VETO_DURATION, target_temp)
            await self._manager.set_room_quick_veto(room.id, qveto)
            room.quick_veto = qveto
        self.data.set_room(room.id, room)

        await self._refresh(touch_system, entity)

    async def set_zone_target_temperature(self, entity, target_temp):
        """Set target temperature for a zone.

        * If there is a quick mode related to zone running or holiday mode,
        remove it.

        * If quick veto running on, remove it and create a new one with the
            new target temp

        * If any other mode, create a quick veto
        """

        touch_system = await self._remove_quick_mode_or_holiday(entity)
        zone = entity.component
        current_mode = self.data.get_active_mode_zone(zone).current

        if current_mode == OperatingModes.QUICK_VETO:
            await self._manager.remove_zone_quick_veto(zone.id)

        veto = QuickVeto(None, target_temp)
        await self._manager.set_zone_quick_veto(zone.id, veto)
        zone.quick_veto = veto

        self.data.set_zone(zone.id, zone)
        await self._refresh(touch_system, entity)

    async def set_hot_water_operating_mode(self, entity, mode):
        """Set hot water operation mode.

        If there is a quick mode that impact hot warter running on or holiday
        mode, remove it.
        """
        hotwater = entity.component
        touch_system = await self._remove_quick_mode_or_holiday(entity)

        await self._manager.set_hot_water_operating_mode(hotwater.id, mode)
        hotwater.operating_mode = mode

        self.data.dhw.hotwater = hotwater
        await self._refresh(touch_system, entity)

    async def set_room_operating_mode(self, entity, mode):
        """Set room operation mode.

        If there is a quick mode that impact room running on or holiday mode,
        remove it.
        """
        touch_system = await self._remove_quick_mode_or_holiday(entity)
        room = entity.component
        if room.quick_veto is not None:
            await self._manager.remove_room_quick_veto(room.id)
            room.quick_veto = None

        if isinstance(mode, QuickMode):
            await self._manager.set_quick_mode(mode)
            self.data.quick_mode = mode
            touch_system = True
        else:
            await self._manager.set_room_operating_mode(room.id, mode)
            room.operating_mode = mode

        self.data.set_room(room.id, room)
        await self._refresh(touch_system, entity)

    async def set_zone_operating_mode(self, entity, mode):
        """Set zone operation mode.

        If there is a quick mode that impact zone running on or holiday mode,
        remove it.
        """
        touch_system = await self._remove_quick_mode_or_holiday(entity)
        zone = entity.component

        if zone.quick_veto is not None:
            await self._manager.remove_zone_quick_veto(zone.id)
            zone.quick_veto = None

        if isinstance(mode, QuickMode):
            await self._manager.set_quick_mode(mode)
            self.data.quick_mode = mode
            touch_system = True
        else:
            if zone.heating and mode in ZoneHeating.MODES:
                await self._manager.set_zone_heating_operating_mode(zone.id, mode)
                zone.heating.operating_mode = mode
            if zone.cooling and mode in ZoneCooling.MODES:
                await self._manager.set_zone_cooling_operating_mode(zone.id, mode)
                zone.cooling.operating_mode = mode

        self.data.set_zone(zone.id, zone)
        await self._refresh(touch_system, entity)

    async def remove_quick_mode(self, entity=None):
        """Remove quick mode.

        If entity is not None, only remove if the quick mode applies to the
        given entity.
        """
        if await self._remove_quick_mode_no_refresh(entity):
            await self._refresh_entities()

    async def remove_holiday_mode(self):
        """Remove holiday mode."""
        if await self._remove_holiday_mode_no_refresh():
            await self._refresh_entities()

    async def set_holiday_mode(self, start_date, end_date, temperature):
        """Set holiday mode."""
        await self._manager.set_holiday_mode(start_date, end_date, temperature)
        self.data.holiday = HolidayMode(True, start_date, end_date, temperature)
        await self._refresh_entities()

    async def set_quick_mode(self, mode):
        """Set quick mode (remove previous one)."""
        try:
            await self._remove_quick_mode_no_refresh()
            qmode = QuickModes.get(mode)
            await self._manager.set_quick_mode(qmode)
            self.data.quick_mode = qmode
            await self._refresh_entities()
        except ApiError as err:
            await self._log_error(err)

    async def set_quick_veto(self, entity, temperature, duration=None):
        """Set quick veto for the given entity."""
        comp = self.find_component(entity.component)

        q_duration = duration if duration else DEFAULT_QUICK_VETO_DURATION
        qveto = QuickVeto(q_duration, temperature)

        if isinstance(comp, Zone):
            if comp.quick_veto:
                await self._manager.remove_zone_quick_veto(comp.id)
            await self._manager.set_zone_quick_veto(comp.id, qveto)
        else:
            if comp.quick_veto:
                await self._manager.remove_room_quick_veto(comp.id)
            await self._manager.set_room_quick_veto(comp.id, qveto)
        comp.quick_veto = qveto
        await self._refresh(False, entity)

    async def remove_quick_veto(self, entity):
        """Remove quick veto for the given entity."""
        comp = self.find_component(entity.component)

        if comp and comp.quick_veto:
            if isinstance(comp, Zone):
                await self._manager.remove_zone_quick_veto(comp.id)
            else:
                await self._manager.remove_room_quick_veto(comp.id)
            comp.quick_veto = None
            await self._refresh(False, entity)

    async def set_fan_operating_mode(self, entity, mode: Mode):
        """Set fan operating mode."""

        touch_system = await self._remove_quick_mode_or_holiday(entity)

        if isinstance(mode, QuickMode):
            await self._manager.set_quick_mode(mode)
            self.data.quick_mode = mode
            touch_system = True
        else:
            await self._manager.set_ventilation_operating_mode(
                self.data.ventilation.id, mode
            )
            self.data.ventilation.operating_mode = mode
        await self._refresh(touch_system, entity)

    async def _remove_quick_mode_no_refresh(self, entity=None):
        removed = False

        qmode = self.data.quick_mode
        if entity and qmode:
            if qmode.is_for(entity.component):
                await self._hard_remove_quick_mode()
                removed = True
        else:
            await self._hard_remove_quick_mode()
            removed = True

        return removed

    async def _hard_remove_quick_mode(self):
        await self._manager.remove_quick_mode()
        self.data.quick_mode = None

    async def _remove_holiday_mode_no_refresh(self):
        removed = False

        if self.data.holiday is not None and self.data.holiday.is_applied:
            removed = True
            await self._manager.remove_holiday_mode()
            self.data.holiday = HolidayMode(False)
        return removed

    async def _remove_quick_mode_or_holiday(self, entity):
        return (
            await self._remove_holiday_mode_no_refresh()
            | await self._remove_quick_mode_no_refresh(entity)
        )

    async def _refresh_entities(self):
        """Fetch multimatic data and force refresh of all listening entities."""
        self.hass.bus.async_fire(REFRESH_ENTITIES_EVENT, {})

    async def _refresh(self, touch_system, entity):
        if touch_system:
            await self._refresh_entities()
        if entity and not entity.listening:
            entity.async_schedule_update_ha_state(True)
