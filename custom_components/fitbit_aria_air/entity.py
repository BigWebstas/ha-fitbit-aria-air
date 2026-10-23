"""Shared base for Fitbit Aria Air entities."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import AriaAirCoordinator


class AriaAirEntity(Entity):
    """An entity that updates whenever the coordinator reports a change."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: AriaAirCoordinator) -> None:
        """Attach to the scale's device."""
        self.coordinator = coordinator
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            name=coordinator.entry.title,
            manufacturer="Fitbit",
            model="Aria Air (FB203)",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
