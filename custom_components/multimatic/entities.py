"""Common entities."""
from __future__ import annotations

from abc import ABC
import logging

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN as MULTIMATIC
from .coordinator import MultimaticCoordinator

_LOGGER = logging.getLogger(__name__)


class MultimaticEntity(CoordinatorEntity, ABC):
    """Define base class for multimatic entities."""

    coordinator: MultimaticCoordinator

    def __init__(self, coordinator: MultimaticCoordinator, domain, device_id):
        """Initialize entity."""
        super().__init__(coordinator)

        id_part = slugify(
            device_id
            + (f"_{coordinator.api.serial}" if coordinator.api.fixed_serial else "")
        )

        self.entity_id = f"{domain}.{id_part}"
        self._unique_id = slugify(f"{MULTIMATIC}_{coordinator.api.serial}_{device_id}")
        self._remove_listener = None

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._unique_id

    async def async_added_to_hass(self):
        """Call when entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug("%s added", self.entity_id)
        self.coordinator.add_api_listener(self.unique_id)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        await super().async_will_remove_from_hass()
        self.coordinator.remove_api_listener(self.unique_id)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data
