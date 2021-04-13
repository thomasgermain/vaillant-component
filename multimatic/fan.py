"""Interfaces with Multimatic fan."""

import logging
from typing import Any, List, Optional

from pymultimatic.model import OperatingModes, QuickModes

from homeassistant.components.fan import DOMAIN, SUPPORT_PRESET_MODE, FanEntity

from . import ApiHub
from .const import DOMAIN as MULTIMATIC, HUB
from .entities import MultimaticEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the multimatic fan platform."""

    hub: ApiHub = hass.data[MULTIMATIC][entry.unique_id][HUB]

    if hub.data.ventilation:
        _LOGGER.debug("Adding fan entity")
        async_add_entities([MultimaticFan(hub)])


class MultimaticFan(MultimaticEntity, FanEntity):
    """Representation of a multimatic fan."""

    def __init__(self, hub: ApiHub):
        """Initialize entity."""

        super().__init__(
            hub,
            DOMAIN,
            hub.data.ventilation.id,
            hub.data.ventilation.name,
            None,
            False,
        )

        self._preset_modes = [
            OperatingModes.AUTO.name,
            OperatingModes.DAY.name,
            OperatingModes.NIGHT.name,
        ]

    @property
    def component(self):
        """Return the ventilation."""
        return self.coordinator.data.ventilation

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        return await self.coordinator.set_fan_operating_mode(
            self, OperatingModes.get(preset_mode.upper())
        )

    async def async_turn_on(
        self,
        speed: Optional[str] = None,
        percentage: Optional[int] = None,
        preset_mode: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Turn on the fan."""
        if preset_mode:
            mode = OperatingModes.get(preset_mode.upper())
        elif speed:
            mode = OperatingModes.get(speed.upper())
        else:
            mode = OperatingModes.AUTO
        return await self.coordinator.set_fan_operating_mode(self, mode)

    async def async_turn_off(self, **kwargs: Any):
        """Turn on the fan."""
        return await self.coordinator.set_fan_operating_mode(self, OperatingModes.NIGHT)

    @property
    def is_on(self):
        """Return true if the entity is on."""
        return (
            self.coordinator.data.get_active_mode_ventilation().current
            != OperatingModes.NIGHT
        )

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_PRESET_MODE

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        return self.coordinator.data.get_active_mode_ventilation().current.name

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes.

        Requires SUPPORT_SET_SPEED.
        """
        if (
            self.coordinator.data.get_active_mode_ventilation().current
            == QuickModes.VENTILATION_BOOST
        ):
            return self._preset_modes + [QuickModes.VENTILATION_BOOST.name]
        return self._preset_modes

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.component is not None
