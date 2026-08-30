"""Sensor entities for Octopus Intelligent Go."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import OctopusIntelligentGoCoordinator
from .data import IntelligentGoData
from .entity import OctopusIntelligentGoEntity


@dataclass(frozen=True, kw_only=True)
class OctopusIntelligentGoSensorDescription(SensorEntityDescription):
    """Sensor description with a value callback."""

    value_fn: Callable[[IntelligentGoData], str | float | None]


SENSOR_DESCRIPTIONS = (
    OctopusIntelligentGoSensorDescription(
        key="immediate_charge_status",
        translation_key="immediate_charge_status",
        icon="mdi:ev-station",
        device_class=SensorDeviceClass.ENUM,
        options=("stopped", "starting", "running", "stopping", "failed"),
        value_fn=lambda data: data.immediate_charge_status,
    ),
    OctopusIntelligentGoSensorDescription(
        key="state",
        name="State",
        value_fn=lambda data: data.current_state,
    ),
    OctopusIntelligentGoSensorDescription(
        key="state_of_charge",
        name="State of charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.state_of_charge,
    ),
    OctopusIntelligentGoSensorDescription(
        key="vehicle_charge_limit",
        name="Vehicle charge limit",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.vehicle_charge_limit,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Octopus Intelligent Go sensor entities."""
    coordinator: OctopusIntelligentGoCoordinator = entry.runtime_data.coordinator
    entities = [
        OctopusIntelligentGoSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
        if coordinator.data and description.value_fn(coordinator.data) is not None
    ]
    async_add_entities(entities)


class OctopusIntelligentGoSensor(OctopusIntelligentGoEntity, SensorEntity):
    """Octopus Intelligent Go sensor entity."""

    entity_description: OctopusIntelligentGoSensorDescription

    def __init__(
        self,
        coordinator: OctopusIntelligentGoCoordinator,
        entity_description: OctopusIntelligentGoSensorDescription,
    ) -> None:
        super().__init__(coordinator, entity_description)

    @property
    def native_value(self) -> str | float | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
