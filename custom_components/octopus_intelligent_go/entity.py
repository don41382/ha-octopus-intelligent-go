"""Base entities for Octopus Intelligent Go."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OctopusIntelligentGoCoordinator


class OctopusIntelligentGoEntity(CoordinatorEntity[OctopusIntelligentGoCoordinator]):
    """Base Octopus Intelligent Go entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OctopusIntelligentGoCoordinator,
        entity_description: EntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = f"{coordinator.device_id}_{entity_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            name=coordinator.device_name,
            manufacturer=coordinator.provider or "Octopus Energy",
            model=coordinator.device_type or "Intelligent Go device",
        )
