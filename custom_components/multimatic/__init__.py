"""The multimatic integration."""
import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_SERIAL_NUMBER,
    COORDINATOR_LIST,
    COORDINATORS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SERVICES_HANDLER,
)
from .coordinator import MultimaticApi, MultimaticCoordinator
from .service import SERVICES, MultimaticServiceHandler

_LOGGER = logging.getLogger(__name__)


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

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, logout)

    await async_setup_service(hass, api, entry)

    return True


async def async_setup_service(hass, api: MultimaticApi, entry: ConfigEntry):
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


async def async_unload_services(hass, entry: ConfigEntry):
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
    if unload_ok:
        await async_unload_services(hass, entry)
        hass.data[DOMAIN].pop(entry.entry_id)

    _LOGGER.debug("Remaining data for multimatic %s", hass.data[DOMAIN])

    return unload_ok
