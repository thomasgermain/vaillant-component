"""Interfaces with Multimatic fan."""

import logging
from typing import Any, Optional

from pymultimatic.model import OperatingModes, QuickModes

from homeassistant.components.fan import DOMAIN, SUPPORT_SET_SPEED, FanEntity

from . import ApiHub
from .const import DOMAIN as MULTIMATIC, HUB
from .entities import MultimaticEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the multimatic fan platform."""

    hub: ApiHub = hass.data[MULTIMATIC][entry.unique_id][HUB]

    if hub.system.ventilation:
        _LOGGER.debug("Adding fan entity")
        async_add_entities([MultimaticFan(hub)], True)


class MultimaticFan(MultimaticEntity, FanEntity):
    """Representation of a multimatic fan."""

    def __init__(self, hub: ApiHub):
        """Initialize entity."""
        self.component = hub.system.ventilation
        super().__init__(
            hub,
            DOMAIN,
            self.component.id,
            self.component.name,
            None,
            False,
        )
        self._speed_list = [
            OperatingModes.AUTO.name,
            OperatingModes.DAY.name,
            OperatingModes.NIGHT.name,
        ]

    async def async_custom_update(self):
        """Update specific for multimatic."""
        self.component = self.coordinator.system.ventilation

    async def async_set_speed(self, speed: str):
        """Set the speed of the fan."""
        return await self.coordinator.set_fan_operating_mode(
            self, OperatingModes.get(speed.upper())
        )

    async def async_turn_on(self, speed: Optional[str] = None, **kwargs):
        """Turn on the fan."""
        mode = OperatingModes.get(speed.upper()) if speed else OperatingModes.AUTO
        return await self.coordinator.set_fan_operating_mode(self, mode)

    async def async_turn_off(self, **kwargs: Any):
        """Turn on the fan."""
        return await self.coordinator.set_fan_operating_mode(self, OperatingModes.NIGHT)

    @property
    def is_on(self):
        """Return true if the entity is on."""
        return (
            self.coordinator.system.get_active_mode_ventilation().current
            != OperatingModes.NIGHT
        )

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_SET_SPEED

    @property
    def speed_list(self) -> list:
        """Get the list of available speeds."""
        if (
            self.coordinator.system.get_active_mode_ventilation().current
            == QuickModes.VENTILATION_BOOST
        ):
            return self._speed_list + [QuickModes.VENTILATION_BOOST.name]
        return self._speed_list

    @property
    def speed(self) -> Optional[str]:
        """Return the current speed."""
        return self.coordinator.system.get_active_mode_ventilation().current.name
