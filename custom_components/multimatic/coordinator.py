"""Api hub and integration data."""
from __future__ import annotations

from datetime import timedelta
import logging

from pymultimatic.api import ApiError, defaults
from pymultimatic.model import (
    Circulation,
    Component,
    HolidayMode,
    HotWater,
    Mode,
    OperatingModes,
    QuickMode,
    QuickModes,
    QuickVeto,
    Room,
    Ventilation,
    Zone,
    ZoneCooling,
    ZoneHeating,
)
import pymultimatic.systemmanager
import pymultimatic.utils as multimatic_utils

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_APPLICATION,
    CONF_SERIAL_NUMBER,
    DEFAULT_QUICK_VETO_DURATION,
    HOLIDAY_MODE,
    QUICK_MODE,
    REFRESH_EVENT,
    SENSO, DEFAULT_QUICK_VETO_DURATION_HOURS,
)
from .utils import (
    holiday_mode_from_json,
    holiday_mode_to_json,
    quick_mode_from_json,
    quick_mode_to_json,
)

_LOGGER = logging.getLogger(__name__)


class MultimaticApi:
    """Utility to interact with multimatic API."""

    def __init__(self, hass, entry: ConfigEntry):
        """Init."""

        self.serial = entry.data.get(CONF_SERIAL_NUMBER)
        self.fixed_serial = self.serial is not None

        username = entry.data[CONF_USERNAME]
        password = entry.data[CONF_PASSWORD]
        systemApplication = defaults.SENSO if entry.data[CONF_APPLICATION] == SENSO else defaults.MULTIMATIC

        self._manager = pymultimatic.systemmanager.SystemManager(
            user=username,
            password=password,
            session=async_create_clientsession(hass),
            serial=self.serial,
            application=systemApplication,
        )

        self._quick_mode: QuickMode | None = None
        self._holiday_mode: HolidayMode | None = None
        self._hass = hass

    async def login(self, force):
        """Login to the API."""
        return await self._manager.login(force)

    async def logout(self):
        """Logout from te API."""
        return await self._manager.logout()

    async def get_gateway(self):
        """Get the gateway."""
        return await self._manager.get_gateway()

    async def get_facility_detail(self):
        """Get facility detail."""
        detail = await self._manager.get_facility_detail(self.serial)
        if detail and not self.fixed_serial and not self.serial:
            self.serial = detail.serial_number
        return detail

    async def get_zones(self):
        """Get the zones."""
        _LOGGER.debug("Will get zones")
        return await self._manager.get_zones()

    async def get_outdoor_temperature(self):
        """Get outdoor temperature."""
        _LOGGER.debug("Will get outdoor temperature")
        return await self._manager.get_outdoor_temperature()

    async def get_rooms(self):
        """Get rooms."""
        _LOGGER.debug("Will get rooms")
        return await self._manager.get_rooms()

    async def get_ventilation(self):
        """Get ventilation."""
        _LOGGER.debug("Will get ventilation")
        return await self._manager.get_ventilation()

    async def get_dhw(self):
        """Get domestic hot water.

        There is a 2 queries here, one to ge the dhw and a second one to get the current temperature if
        there is a water tank.
        """
        _LOGGER.debug("Will get dhw")
        dhw = await self._manager.get_dhw()
        if dhw and dhw.hotwater and dhw.hotwater.time_program:
            _LOGGER.debug("Will get temperature report")
            report = await self._manager.get_live_report(
                "DomesticHotWaterTankTemperature", "Control_DHW"
            )
            dhw.hotwater.temperature = report.value if report else None
        return dhw

    async def get_live_reports(self):
        """Get reports."""
        _LOGGER.debug("Will get reports")
        return await self._manager.get_live_reports()

    async def get_quick_mode(self):
        """Get quick modes."""
        _LOGGER.debug("Will get quick_mode")
        self._quick_mode = await self._manager.get_quick_mode()
        return self._quick_mode

    async def get_holiday_mode(self):
        """Get holiday mode."""
        _LOGGER.debug("Will get holiday_mode")
        self._holiday_mode = await self._manager.get_holiday_mode()
        return self._holiday_mode

    async def get_hvac_status(self):
        """Get the status of the HVAC."""
        _LOGGER.debug("Will get hvac status")
        return await self._manager.get_hvac_status()

    async def get_emf_reports(self):
        """Get emf reports."""
        _LOGGER.debug("Will get emf reports")
        return await self._manager.get_emf_devices()

    async def request_hvac_update(self):
        """Request is not on the classic update since it won't fetch data.

        The request update will trigger something at multimatic API and it will
        ask data to your system.
        """
        try:
            _LOGGER.debug("Will request_hvac_update")
            await self._manager.request_hvac_update()
        except ApiError as err:
            if err.status >= 500:
                raise
            _LOGGER.warning("Request_hvac_update is done too often", exc_info=True)

    def get_active_mode(self, comp: Component):
        """Get active mode for room, zone, circulation, ventilaton or hotwater, no IO."""
        return multimatic_utils.active_mode_for(
            comp, self._holiday_mode, self._quick_mode
        )

    async def set_hot_water_target_temperature(self, entity, target_temp):
        """Set hot water target temperature.

        * If there is a quick mode that impact dhw running on or holiday mode,
        remove it.

        * If dhw is ON or AUTO, modify the target temperature

        * If dhw is OFF, change to ON and set target temperature
        """

        hotwater = entity.component
        touch_system = await self._remove_quick_mode_or_holiday(entity)
        current_mode = self.get_active_mode(hotwater).current

        if current_mode == OperatingModes.OFF:
            await self._manager.set_hot_water_operating_mode(
                hotwater.id, OperatingModes.ON
            )
            hotwater.operating_mode = OperatingModes.ON
        await self._manager.set_hot_water_setpoint_temperature(hotwater.id, target_temp)
        hotwater.target_high = target_temp

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
        current_mode = self.get_active_mode(room).current

        if current_mode == OperatingModes.MANUAL:
            await self._manager.set_room_setpoint_temperature(room.id, target_temp)
            room.target_temperature = target_temp
        else:
            if current_mode == OperatingModes.QUICK_VETO:
                await self._manager.remove_room_quick_veto(room.id)

            qveto = QuickVeto(self._default_quick_veto_duration(), target_temp)
            await self._manager.set_room_quick_veto(room.id, qveto)
            room.quick_veto = qveto

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

        current_mode = self.get_active_mode(zone).current

        if current_mode == OperatingModes.QUICK_VETO:
            await self._manager.remove_zone_quick_veto(zone.id)

        # Senso needs a duration, applying the same duration as the Multimatic default.
        veto = QuickVeto(self._default_quick_veto_duration(), target_temp)
        await self._manager.set_zone_quick_veto(zone.id, veto)
        zone.quick_veto = veto

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
            await self._hard_set_quick_mode(mode)
            self._quick_mode = mode
            touch_system = True
        else:
            await self._manager.set_room_operating_mode(room.id, mode)
            room.operating_mode = mode

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
            await self._hard_set_quick_mode(mode)
            self._quick_mode = mode
            touch_system = True
        else:
            if zone.heating and mode in ZoneHeating.MODES:
                await self._manager.set_zone_heating_operating_mode(zone.id, mode)
                zone.heating.operating_mode = mode
            if zone.cooling and mode in ZoneCooling.MODES:
                await self._manager.set_zone_cooling_operating_mode(zone.id, mode)
                zone.cooling.operating_mode = mode

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
        self._holiday_mode = HolidayMode(True, start_date, end_date, temperature)
        await self._refresh_entities()

    async def set_quick_mode(self, mode, duration):
        """Set quick mode (remove previous one)."""
        await self._remove_quick_mode_no_refresh()
        self._quick_mode = await self._hard_set_quick_mode(mode, duration)
        await self._refresh_entities()

    async def set_quick_veto(self, entity, temperature, duration=None):
        """Set quick veto for the given entity."""
        comp = entity.component

        q_duration = duration if duration else DEFAULT_QUICK_VETO_DURATION
        # For senso, the duration is in hours
        if self._manager._application == defaults.SENSO:
            q_duration = round(q_duration / 60 / 0.5) * 0.5
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
        comp = entity.component

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
            await self._hard_set_quick_mode(mode)
            self._quick_mode = mode
            touch_system = True
        else:
            await self._manager.set_ventilation_operating_mode(
                entity.component.id, mode
            )
            entity.component.operating_mode = mode
        await self._refresh(touch_system, entity)

    async def set_fan_day_level(self, entity, level):
        """Set fan day level."""
        await self._manager.set_ventilation_day_level(entity.component.id, level)

    async def set_fan_night_level(self, entity, level):
        """Set fan night level."""
        await self._manager.set_ventilation_night_level(entity.component.id, level)

    async def set_datetime(self, datetime):
        """Set datetime."""
        await self._manager.set_datetime(datetime)

    async def _remove_quick_mode_no_refresh(self, entity=None):
        removed = False

        qmode = self._quick_mode
        if entity and qmode:
            if qmode.is_for(entity.component):
                await self._hard_remove_quick_mode()
                removed = True
        else:  # coming from service call
            await self._hard_remove_quick_mode()
            removed = True

        return removed

    async def _hard_remove_quick_mode(self):
        await self._manager.remove_quick_mode()
        self._quick_mode = None

    async def _hard_set_quick_mode(
        self, mode: str | QuickMode, duration: int | None = None
    ) -> QuickMode:
        new_mode: QuickMode

        if isinstance(mode, QuickMode):
            new_mode = mode
            if (
                mode.name == QuickModes.COOLING_FOR_X_DAYS.name
                and mode.duration is None
            ):
                new_mode = QuickModes.get(mode.name, 1)
        else:
            new_duration = duration
            if mode == QuickModes.COOLING_FOR_X_DAYS.name and duration is None:
                new_duration = 1
            new_mode = QuickModes.get(mode, new_duration)

        await self._manager.set_quick_mode(new_mode)
        return new_mode

    async def _remove_holiday_mode_no_refresh(self):
        await self._manager.remove_holiday_mode()
        self._holiday_mode = HolidayMode(False)
        return True

    async def _remove_quick_mode_or_holiday(self, entity):
        return (
            await self._remove_holiday_mode_no_refresh()
            | await self._remove_quick_mode_no_refresh(entity)
        )

    async def _refresh_entities(self):
        """Fetch multimatic data and force refresh of all listening entities."""
        data = {
            QUICK_MODE: quick_mode_to_json(self._quick_mode),
            HOLIDAY_MODE: holiday_mode_to_json(self._holiday_mode),
        }
        self._hass.bus.async_fire(REFRESH_EVENT, data)

    async def _refresh(self, touch_system, entity):
        if touch_system:
            await self._refresh_entities()
        entity.async_schedule_update_ha_state(True)

    def _default_quick_veto_duration(self):
        return DEFAULT_QUICK_VETO_DURATION_HOURS if self._manager._application == defaults.SENSO else DEFAULT_QUICK_VETO_DURATION


class MultimaticCoordinator(DataUpdateCoordinator):
    """Multimatic coordinator."""

    def __init__(
        self,
        hass,
        name,
        api: MultimaticApi,
        method: str,
        update_interval: timedelta | None,
    ):
        """Init."""

        self._api_listeners: set = set()
        self._method = method
        self.api: MultimaticApi = api

        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=update_interval,
            update_method=self._first_fetch_data,
        )

        self._remove_listener = self.hass.bus.async_listen(
            REFRESH_EVENT, self._handle_event
        )

    def find_component(
        self, comp_id
    ) -> Room | Zone | Ventilation | HotWater | Circulation | None:
        """Find component by its id."""
        for comp in self.data:
            if comp.id == comp_id:
                return comp
        return None

    def remove_api_listener(self, unique_id: str):
        """Remove entity from listening to the api."""
        if unique_id in self._api_listeners:
            self.logger.debug("Removing %s from %s", unique_id, self._method)
            self._api_listeners.remove(unique_id)

    def add_api_listener(self, unique_id: str):
        """Make an entity listen to API."""
        if unique_id not in self._api_listeners:
            self.logger.debug("Adding %s to key %s", unique_id, self._method)
            self._api_listeners.add(unique_id)

    async def _handle_event(self, event):
        if isinstance(self.data, QuickMode):
            quick_mode = quick_mode_from_json(event.data.get(QUICK_MODE))
            self.async_set_updated_data(quick_mode)
        elif isinstance(self.data, HolidayMode):
            holiday_mode = holiday_mode_from_json(event.data.get(HOLIDAY_MODE))
            self.async_set_updated_data(holiday_mode)
        else:
            self.async_set_updated_data(
                self.data
            )  # Fake refresh for climates and water heater and fan

    async def _fetch_data(self):
        try:
            self.logger.debug("calling %s", self._method)
            return await getattr(self.api, self._method)()
        except ApiError as err:
            if err.status == 401:
                await self._safe_logout()
            raise

    async def _fetch_data_if_needed(self):
        if self._api_listeners and len(self._api_listeners) > 0:
            return await self._fetch_data()

    async def _first_fetch_data(self):
        try:
            result = await self._fetch_data()
            self.update_method = self._fetch_data_if_needed
            return result
        except ApiError as err:
            if err.status in (400, 409):
                self.update_method = self._fetch_data_if_needed
                _LOGGER.debug(
                    "Received %s %s when calling %s for the first time",
                    err.response,
                    err.message,
                    self.name,
                    exc_info=True,
                )
                return None
            raise

    async def _safe_logout(self):
        try:
            await self.api.logout()
        except ApiError:
            self.logger.debug("Error during logout", exc_info=True)
