"""The multimatic integration."""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant

from .const import DOMAIN, HUB, PLATFORMS, SERVICES_HANDLER
from .hub import ApiHub
from .service import SERVICES, MultimaticServiceHandler

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the multimatic integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up multimatic from a config entry."""

    api: ApiHub = ApiHub(hass, entry)
    await api.authenticate()
    await api.async_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.unique_id, {})
    hass.data[DOMAIN][entry.unique_id][HUB] = api

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    async def logout(param):
        await api.logout()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, logout)

    await async_setup_service(api, hass)

    return True


async def async_setup_service(api: ApiHub, hass):
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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
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
