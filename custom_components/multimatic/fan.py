"""Interfaces with Multimatic fan."""

from __future__ import annotations

import logging
from typing import Any

from pymultimatic.model import OperatingModes, QuickModes

from homeassistant.components.fan import DOMAIN, SUPPORT_PRESET_MODE, FanEntity
from homeassistant.helpers import entity_platform

from .const import VENTILATION
from .coordinator import MultimaticCoordinator
from .entities import MultimaticEntity
from .service import (
    SERVICE_SET_VENTILATION_DAY_LEVEL,
    SERVICE_SET_VENTILATION_NIGHT_LEVEL,
    SERVICES,
)
from .utils import get_coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the multimatic fan platform."""

    coordinator = get_coordinator(hass, VENTILATION, entry.unique_id)

    if coordinator.data:
        _LOGGER.debug("Adding fan entity")
        async_add_entities([MultimaticFan(coordinator)])

        _LOGGER.debug("Adding fan services")
        platform = entity_platform.current_platform.get()
        platform.async_register_entity_service(
            SERVICE_SET_VENTILATION_DAY_LEVEL,
            SERVICES[SERVICE_SET_VENTILATION_DAY_LEVEL]["schema"],
            SERVICE_SET_VENTILATION_DAY_LEVEL,
        )
        platform.async_register_entity_service(
            SERVICE_SET_VENTILATION_NIGHT_LEVEL,
            SERVICES[SERVICE_SET_VENTILATION_NIGHT_LEVEL]["schema"],
            SERVICE_SET_VENTILATION_NIGHT_LEVEL,
        )


class MultimaticFan(MultimaticEntity, FanEntity):
    """Representation of a multimatic fan."""

    def __init__(self, coordinator: MultimaticCoordinator) -> None:
        """Initialize entity."""

        super().__init__(
            coordinator,
            DOMAIN,
            coordinator.data.id,
        )

        self._preset_modes = [
            OperatingModes.AUTO.name,
            OperatingModes.DAY.name,
            OperatingModes.NIGHT.name,
        ]

    @property
    def component(self):
        """Return the ventilation."""
        return self.coordinator.data

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self.component.name if self.component else None

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        return await self.coordinator.api.set_fan_operating_mode(
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
        return await self.coordinator.api.set_fan_operating_mode(self, mode)

    async def async_turn_off(self, **kwargs: Any):
        """Turn on the fan."""
        return await self.coordinator.api.set_fan_operating_mode(
            self, OperatingModes.NIGHT
        )

    @property
    def is_on(self):
        """Return true if the entity is on."""
        return self.active_mode.current != OperatingModes.NIGHT

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return SUPPORT_PRESET_MODE

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode, e.g., auto, smart, interval, favorite."""
        return self.active_mode.current.name

    @property
    def preset_modes(self) -> list[str] | None:
        """Return a list of available preset modes.

        Requires SUPPORT_SET_SPEED.
        """
        if self.active_mode.current == QuickModes.VENTILATION_BOOST:
            return self._preset_modes + [QuickModes.VENTILATION_BOOST.name]
        return self._preset_modes

    @property
    def available(self):
        """Return True if entity is available."""
        return super().available and self.component

    @property
    def active_mode(self):
        """Return the active mode."""
        return self.coordinator.api.get_active_mode(self.component)
