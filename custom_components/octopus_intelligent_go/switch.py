"""Switch entity for Octopus Intelligent Go scheduled charging."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError
from .coordinator import OctopusIntelligentGoCoordinator
from .entity import OctopusIntelligentGoEntity

SMART_CHARGING_DESCRIPTION = SwitchEntityDescription(
    key="smart_charging",
    name="Allow scheduled charging",
    icon="mdi:calendar-clock",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Octopus Intelligent Go scheduled-charging switch."""
    coordinator: OctopusIntelligentGoCoordinator = entry.runtime_data.coordinator
    async_add_entities([OctopusIntelligentGoSmartChargingSwitch(coordinator)])


class OctopusIntelligentGoSmartChargingSwitch(
    OctopusIntelligentGoEntity,
    SwitchEntity,
):
    """Allow or suspend Octopus smart charging."""

    def __init__(self, coordinator: OctopusIntelligentGoCoordinator) -> None:
        super().__init__(coordinator, SMART_CHARGING_DESCRIPTION)

    @property
    def is_on(self) -> bool | None:
        """Return whether Octopus smart charging is enabled."""
        return self.coordinator.data.smart_control_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Allow Octopus to plan and execute smart charging."""
        await self._async_update("UNSUSPEND")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Suspend Octopus smart charging."""
        await self._async_update("SUSPEND")

    async def _async_update(self, action: str) -> None:
        try:
            await self.coordinator.client.async_update_device_smart_control(
                device_id=self.coordinator.device_id,
                action=action,
            )
        except (OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError) as err:
            raise HomeAssistantError(str(err)) from err

        await self.coordinator.async_request_refresh()
