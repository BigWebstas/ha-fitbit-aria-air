"""The Fitbit Aria Air integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import AriaAirCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type AriaAirConfigEntry = ConfigEntry[AriaAirCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AriaAirConfigEntry) -> bool:
    """Start watching the scale for weigh-ins."""
    coordinator = AriaAirCoordinator(hass, entry)
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_start())
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AriaAirConfigEntry) -> bool:
    """Stop watching and remove the entities."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_on_options(hass: HomeAssistant, entry: AriaAirConfigEntry) -> None:
    """Apply changed options (such as the unit) by reloading."""
    await hass.config_entries.async_reload(entry.entry_id)
