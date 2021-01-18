"""Common entities."""
from abc import ABC, abstractmethod
import logging
from typing import Optional

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from . import ApiHub
from .const import DOMAIN as MULTIMATIC, REFRESH_ENTITIES_EVENT

_LOGGER = logging.getLogger(__name__)


class MultimaticEntity(CoordinatorEntity, ABC):
    """Define base class for multimatic entities."""

    def __init__(
        self, hub: ApiHub, domain, device_id, name, dev_class=None, class_id=True
    ):
        """Initialize entity."""
        super().__init__(hub)
        self._device_class = dev_class
        if dev_class and class_id:
            id_format = domain + ".{}_" + dev_class
            unique_id_format = domain + "." + MULTIMATIC + "_{}_" + dev_class
        else:
            id_format = domain + ".{}"
            unique_id_format = domain + "." + MULTIMATIC + "_{}"

        self.entity_id = id_format.format(slugify(device_id)).lower()
        self._unique_id = unique_id_format.format(slugify(device_id)).lower()
        self._entity_name = name
        self._remove_listener = None

    @property
    def name(self) -> Optional[str]:
        """Return the name of the entity."""
        return self._entity_name

    @property
    def unique_id(self) -> Optional[str]:
        """Return a unique ID."""
        return self._unique_id

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state."""
        return True

    async def async_update(self):
        """Update the entity."""
        _LOGGER.debug("Time to update %s", self.entity_id)
        await super().async_update()
        await self.async_custom_update()

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._device_class

    @abstractmethod
    async def async_custom_update(self):
        """Update specific for multimatic."""

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
