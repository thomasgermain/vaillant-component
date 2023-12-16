"""The multimatic integration."""
import asyncio
from datetime import datetime, timedelta
import logging

from pymultimatic.api import ApiError, defaults
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_APPLICATION,
    CONF_SERIAL_NUMBER,
    COORDINATOR_LIST,
    COORDINATORS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FORCE_RELOGIN_TIMEDELTA,
    MULTIMATIC,
    PLATFORMS,
    RELOGIN_TASK_CLEAN,
    SENSO,
    SERVICES_HANDLER,
)
from .coordinator import MultimaticApi, MultimaticCoordinator
from .service import SERVICES, MultimaticServiceHandler

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_SERIAL_NUMBER): cv.string,
        vol.Required(CONF_APPLICATION, default=MULTIMATIC): vol.In([MULTIMATIC, SENSO]),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: DATA_SCHEMA},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the multimatic integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up multimatic from a config entry."""

    api: MultimaticApi = MultimaticApi(hass, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {})
    hass.data[DOMAIN][entry.entry_id].setdefault(COORDINATORS, {})

    _LOGGER.debug(
        "Setting up multimatic for serial  %s, id is %s",
        entry.data.get(CONF_SERIAL_NUMBER),
        entry.entry_id,
    )

    for coord in COORDINATOR_LIST.items():
        update_interval = (
            coord[1]
            if coord[1]
            else timedelta(
                minutes=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            )
        )
        m_coord = MultimaticCoordinator(
            hass,
            name=f"{DOMAIN}_{coord[0]}",
            api=api,
            method="get_" + coord[0],
            update_interval=update_interval,
        )
        hass.data[DOMAIN][entry.entry_id][COORDINATORS][coord[0]] = m_coord
        _LOGGER.debug("Adding %s coordinator", m_coord.name)
        await m_coord.async_refresh()

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    async def logout(event):
        await api.logout()

    async def force_relogin(time: datetime):
        try:
            _LOGGER.debug("Periodic relogin")
            await api.login(True)
        except ApiError:
            _LOGGER.debug("Error during periodic login", exc_info=True)

    hass.data[DOMAIN][entry.entry_id][RELOGIN_TASK_CLEAN] = async_track_time_interval(
        hass, force_relogin, FORCE_RELOGIN_TIMEDELTA
    )
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, logout)

    await async_setup_service(hass, api, entry)

    return True


async def async_setup_service(
    hass: HomeAssistant, api: MultimaticApi, entry: ConfigEntry
):
    """Set up services."""
    serial = api.serial if api.fixed_serial else None

    if not hass.data[DOMAIN][entry.entry_id].get(SERVICES_HANDLER):
        service_handler = MultimaticServiceHandler(api, hass)
        for service_key, data in SERVICES.items():
            schema = data["schema"]
            if not data.get("entity", False):
                key = service_key
                if serial:
                    key += f"_{serial}"
                hass.services.async_register(
                    DOMAIN, key, getattr(service_handler, service_key), schema=schema
                )
        hass.data[DOMAIN][entry.entry_id][SERVICES_HANDLER] = service_handler


async def async_unload_services(hass: HomeAssistant, entry: ConfigEntry):
    """Remove services when integration is removed."""
    service_handler = hass.data[DOMAIN][entry.entry_id].get(SERVICES_HANDLER, None)
    if service_handler:
        serial = (
            service_handler.api.serial if service_handler.api.fixed_serial else None
        )
        for service_key in SERVICES:
            key = service_key
            if serial:
                key += f"_{serial}"
            if hass.services.has_service(DOMAIN, key):
                hass.services.async_remove(DOMAIN, key)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *(
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            )
        )
    )

    relogin_task_clean = hass.data[DOMAIN][entry.entry_id][RELOGIN_TASK_CLEAN]
    if relogin_task_clean:
        relogin_task_clean()

    if unload_ok:
        await async_unload_services(hass, entry)
        hass.data[DOMAIN].pop(entry.entry_id)

    _LOGGER.debug("Remaining data for multimatic %s", hass.data[DOMAIN])

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)
    if config_entry.version == 1:
        new = {**config_entry.data, CONF_APPLICATION: defaults.MULTIMATIC}

        config_entry.version = 2
        hass.config_entries.async_update_entry(config_entry, data=new)

    _LOGGER.debug("Migration to version %s successful", config_entry.version)

    return True
