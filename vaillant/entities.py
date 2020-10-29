"""Common entities."""
from abc import ABC, abstractmethod
import logging
from typing import Optional

from homeassistant.helpers.entity import Entity
from homeassistant.util import slugify

from . import ApiHub
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class VaillantEntity(Entity, ABC):
    """Define base class for vaillant."""

    def __init__(
        self, hub: ApiHub, domain, device_id, name, dev_class=None, class_id=True
    ):
        """Initialize entity."""
        self._device_class = dev_class
        if dev_class and class_id:
            id_format = domain + "." + DOMAIN + "_{}_" + dev_class
        else:
            id_format = domain + "." + DOMAIN + "_{}"

        self.entity_id = id_format.format(slugify(device_id)).lower()
        self._vaillant_name = name
        self.hub = hub
        self._unique_id = self.entity_id

    @property
    def name(self) -> Optional[str]:
        """Return the name of the entity."""
        return self._vaillant_name

    @property
    def unique_id(self) -> Optional[str]:
        """Return a unique ID."""
        return self._unique_id

    async def async_update(self):
        """Update the entity."""
        _LOGGER.debug("Time to update %s", self.entity_id)
        await self.hub.update_system()
        await self.vaillant_update()

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._device_class

    @abstractmethod
    async def vaillant_update(self):
        """Update specific for vaillant."""

    @property
    def listening(self):
        """Return whether this entity is listening for system changes or not.

        System changes are quick mode or holiday mode.
        """
        return False

    async def async_added_to_hass(self):
        """Call when entity is added to hass."""
        _LOGGER.debug("Adding %s to entities list", self.entity_id)
        self.hub.entities.append(self)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        _LOGGER.debug("Removing %s from entities list", self.entity_id)
        self.hub.entities.remove(self)
