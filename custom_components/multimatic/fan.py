"""Interfaces with Multimatic fan."""

from __future__ import annotations

import logging
from typing import Any

from pymultimatic.model import OperatingModes, QuickModes

from homeassistant.components.fan import DOMAIN, SUPPORT_PRESET_MODE, FanEntity

from . import MultimaticDataUpdateCoordinator
from .const import COORDINATOR, DOMAIN as MULTIMATIC
from .entities import MultimaticEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the multimatic fan platform."""

    coordinator: MultimaticDataUpdateCoordinator = hass.data[MULTIMATIC][
        entry.unique_id
    ][COORDINATOR]

    if coordinator.data.ventilation:
        _LOGGER.debug("Adding fan entity")
        async_add_entities([MultimaticFan(coordinator)])


class MultimaticFan(MultimaticEntity, FanEntity):
    """Representation of a multimatic fan."""

    def __init__(self, coordinator: MultimaticDataUpdateCoordinator) -> None:
        """Initialize entity."""

        super().__init__(
            coordinator,
            DOMAIN,
            coordinator.data.ventilation.id,
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

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return (
            self.coordinator.data.ventilation.name
            if self.coordinator.data.ventilation
            else None
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        return await self.coordinator.set_fan_operating_mode(
            self, OperatingModes.get(preset_mode.upper())
        )

    async def async_turn_on(
        self,
        speed: str | None = None,
        percentage: int | None = None,
        preset_mode: str | None = None,
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
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        return self.coordinator.data.get_active_mode_ventilation().current.name

    @property
    def preset_modes(self) -> list[str] | None:
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
