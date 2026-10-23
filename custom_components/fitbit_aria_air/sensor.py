"""Sensors for the Fitbit Aria Air."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import UNIT_LB
from .coordinator import AriaAirCoordinator
from .entity import AriaAirEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[AriaAirCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the weight and last-weigh-in sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            AriaAirWeightSensor(coordinator),
            AriaAirLastWeighInSensor(coordinator),
            AriaAirConnectionSensor(coordinator),
        ]
    )


class AriaAirWeightSensor(AriaAirEntity, RestoreSensor):
    """The most recent weight the scale reported."""

    _attr_translation_key = "weight"
    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: AriaAirCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_weight"
        self._restored: float | None = None

    @property
    def native_unit_of_measurement(self) -> str:
        """Unit the scale reports in (chosen in the integration settings)."""
        if self.coordinator.unit == UNIT_LB:
            return UnitOfMass.POUNDS
        return UnitOfMass.KILOGRAMS

    @property
    def native_value(self) -> float | None:
        """Latest reading, or the last one seen before a restart."""
        if self.coordinator.weight is not None:
            return self.coordinator.weight
        return self._restored

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Expose the scale's raw unit flag to help verify the unit setting."""
        if self.coordinator.unit_flag is None:
            return None
        return {"unit_flag": self.coordinator.unit_flag}

    async def async_added_to_hass(self) -> None:
        """Restore the last value so the sensor isn't empty after a restart."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is None:
            return
        if last.native_unit_of_measurement != self.native_unit_of_measurement:
            return  # the unit setting changed; the old number would be misleading
        try:
            self._restored = float(last.native_value)
        except (TypeError, ValueError):
            self._restored = None


class AriaAirLastWeighInSensor(AriaAirEntity, RestoreSensor):
    """When the last weigh-in was received."""

    _attr_translation_key = "last_weigh_in"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: AriaAirCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_last_weigh_in"
        self._restored: datetime | None = None

    @property
    def native_value(self) -> datetime | None:
        """Time of the latest reading."""
        return self.coordinator.last_weigh_in or self._restored

    async def async_added_to_hass(self) -> None:
        """Restore the previous timestamp after a restart."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is None:
            return
        if isinstance(last.native_value, datetime):
            self._restored = last.native_value


class AriaAirConnectionSensor(AriaAirEntity, SensorEntity):
    """What the Bluetooth connection is doing; helps work out missed weigh-ins."""

    _attr_translation_key = "connection"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AriaAirCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_connection"

    @property
    def native_value(self) -> str:
        """Current connection state in words."""
        return self.coordinator.status

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Counts since Home Assistant started."""
        return {
            "sessions": self.coordinator.sessions,
            "failed_sessions": self.coordinator.failed_sessions,
            "readings": self.coordinator.readings,
        }
