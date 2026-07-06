"""Number entities for Octopus Intelligent Go."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError
from .coordinator import OctopusIntelligentGoCoordinator
from .entity import OctopusIntelligentGoEntity

TARGET_CHARGE_DESCRIPTION = EntityDescription(
    key="target_charge_percentage",
    name="Target charge percentage",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Octopus Intelligent Go number entities."""
    coordinator: OctopusIntelligentGoCoordinator = entry.runtime_data.coordinator
    if coordinator.data and coordinator.data.target_charge_percentage is not None:
        async_add_entities([OctopusIntelligentGoTargetChargeNumber(coordinator)])


class OctopusIntelligentGoTargetChargeNumber(OctopusIntelligentGoEntity, NumberEntity):
    """Target/max charge percentage number entity."""

    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: OctopusIntelligentGoCoordinator) -> None:
        super().__init__(coordinator, TARGET_CHARGE_DESCRIPTION)

    @property
    def native_value(self) -> float | None:
        """Return the current target charge percentage."""
        return self.coordinator.data.target_charge_percentage

    async def async_set_native_value(self, value: float) -> None:
        """Set the target charge percentage."""
        try:
            await self.coordinator.client.async_set_max_percentage(
                device_id=self.coordinator.device_id,
                percent=value,
                schedules=self.coordinator.data.schedules,
            )
        except (OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError) as err:
            raise HomeAssistantError(f"Could not set target charge percentage: {err}") from err

        await self.coordinator.async_request_refresh()
