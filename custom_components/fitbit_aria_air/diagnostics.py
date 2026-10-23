"""Diagnostics for the Fitbit Aria Air (secrets redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .const import CONF_KEY
from .coordinator import AriaAirCoordinator

TO_REDACT = {CONF_KEY, CONF_ADDRESS}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[AriaAirCoordinator]
) -> dict[str, Any]:
    """Return state useful for debugging, without the key or address."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "state": {
            "weight": coordinator.weight,
            "unit_flag": coordinator.unit_flag,
            "last_weigh_in": coordinator.last_weigh_in.isoformat()
            if coordinator.last_weigh_in
            else None,
            "in_use": coordinator.in_use,
            "session_running": coordinator.session_running,
        },
    }
