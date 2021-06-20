"""Common entities."""
from __future__ import annotations

from abc import ABC
import logging

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from . import MultimaticDataUpdateCoordinator
from .const import DOMAIN as MULTIMATIC, REFRESH_ENTITIES_EVENT

_LOGGER = logging.getLogger(__name__)


class MultimaticEntity(CoordinatorEntity, ABC):
    """Define base class for multimatic entities."""

    coordinator: MultimaticDataUpdateCoordinator

    def __init__(self, coordinator: MultimaticDataUpdateCoordinator, domain, device_id):
        """Initialize entity."""
        super().__init__(coordinator)

        id_part = slugify(
            device_id
            + (
                f"_{coordinator.data.info.serial_number}"
                if coordinator.fixed_serial
                else ""
            )
        )

        self.entity_id = f"{domain}.{id_part}"
        self._unique_id = slugify(
            f"{MULTIMATIC}_{coordinator.data.info.serial_number}_{device_id}"
        )
        self._remove_listener = None

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._unique_id

    @property
    def listening(self):
        """Return whether this entity is listening for system changes or not.

        System changes are quick mode or holiday mode.
        """
        return False

    async def async_added_to_hass(self):
        """Call when entity is added to hass."""
        await super().async_added_to_hass()
        _LOGGER.debug("%s added", self.entity_id)
        if self.listening:

            def handle_event(event):
                _LOGGER.debug("%s received event", self.entity_id)
                self.async_schedule_update_ha_state(True)

            _LOGGER.debug(
                "%s Will listen to %s", self.entity_id, REFRESH_ENTITIES_EVENT
            )
            self._remove_listener = self.hass.bus.async_listen(
                REFRESH_ENTITIES_EVENT, handle_event
            )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        await super().async_will_remove_from_hass()
        if self._remove_listener:
            self._remove_listener()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data
