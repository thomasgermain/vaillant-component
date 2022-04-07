"""The multimatic integration."""
import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant

from .const import (
    COORDINATOR_LIST,
    COORDINATORS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SERVICES_HANDLER,
)
from .coordinator import MultimaticApi, MultimaticCoordinator
from .service import SERVICES, MultimaticServiceHandler
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the multimatic integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up multimatic from a config entry."""

    api: MultimaticApi = MultimaticApi(hass, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.unique_id, {})
    hass.data[DOMAIN][entry.unique_id].setdefault(COORDINATORS, {})

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
        hass.data[DOMAIN][entry.unique_id][COORDINATORS][coord[0]] = m_coord
        _LOGGER.debug("Adding %s coordinator", m_coord.name)
        await m_coord.async_refresh()

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    async def logout(event):
        await api.logout()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, logout)

    await async_setup_service(api, hass)

    return True


async def async_setup_service(api: MultimaticApi, hass):
    """Set up services."""
    if not hass.data.get(SERVICES_HANDLER):
        service_handler = MultimaticServiceHandler(api, hass)
        for service_key in SERVICES:
            schema = SERVICES[service_key]["schema"]
            if not SERVICES[service_key].get("entity", False):
                hass.services.async_register(
                    DOMAIN, service_key, service_handler.service_call, schema=schema
                )
        hass.data[DOMAIN][SERVICES_HANDLER] = service_handler


async def async_unload_services(hass):
    """Remove service when integration is removed."""
    service_handler = hass.data[DOMAIN].get(SERVICES_HANDLER, None)
    if service_handler:
        for service_name in SERVICES:
            hass.services.async_remove(DOMAIN, service_name)


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
        hass.data[DOMAIN].pop(entry.unique_id)

    _LOGGER.debug("Remaining data for multimatic %s", hass.data[DOMAIN])

    if (
        len(hass.data[DOMAIN]) == 1
        and hass.data[DOMAIN].get(SERVICES_HANDLER, None) is not None
    ):
        await async_unload_services(hass)
        hass.data[DOMAIN].pop(SERVICES_HANDLER)

    return unload_ok
