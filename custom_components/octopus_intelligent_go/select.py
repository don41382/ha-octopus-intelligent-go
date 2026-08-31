"""Combined charging-mode select for Octopus Intelligent Go."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError
from .coordinator import OctopusIntelligentGoCoordinator
from .data import (
    CHARGING_MODE_CHARGE_NOW,
    CHARGING_MODE_PAUSED,
    CHARGING_MODE_SCHEDULED,
    CHARGING_MODES,
    CHARGING_OPERATION_BOOST,
    CHARGING_OPERATION_SMART_CONTROL,
    charging_mode_actions,
)
from .entity import OctopusIntelligentGoEntity

CHARGING_MODE_DESCRIPTION = SelectEntityDescription(
    key="charging_mode",
    translation_key="charging_mode",
)

CHARGING_MODE_ICONS = {
    CHARGING_MODE_SCHEDULED: "mdi:calendar-clock",
    CHARGING_MODE_CHARGE_NOW: "mdi:battery-charging",
    CHARGING_MODE_PAUSED: "mdi:pause-circle-outline",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the combined charging-mode select."""
    coordinator: OctopusIntelligentGoCoordinator = entry.runtime_data.coordinator
    async_add_entities([OctopusIntelligentGoChargingModeSelect(coordinator)])


class OctopusIntelligentGoChargingModeSelect(
    OctopusIntelligentGoEntity,
    SelectEntity,
):
    """Orchestrate immediate and scheduled charging as one mode."""

    _attr_options = list(CHARGING_MODES)

    def __init__(self, coordinator: OctopusIntelligentGoCoordinator) -> None:
        super().__init__(coordinator, CHARGING_MODE_DESCRIPTION)

    @property
    def available(self) -> bool:
        """Return whether both required Kraken states are available."""
        return super().available and self.current_option is not None

    @property
    def current_option(self) -> str | None:
        """Return the mode derived from Kraken readback."""
        return self.coordinator.data.charging_mode

    @property
    def icon(self) -> str:
        """Return an icon for the current charging mode."""
        return CHARGING_MODE_ICONS.get(
            self.current_option,
            "mdi:ev-station",
        )

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Expose the immediate-charging lifecycle for compact dashboard cards."""
        status = self.coordinator.data.immediate_charge_status
        return {"charging_status": status.capitalize() if status else None}

    async def async_select_option(self, option: str) -> None:
        """Apply the minimum ordered mutations needed for the selected mode."""
        try:
            actions = charging_mode_actions(
                option,
                self.coordinator.data.immediate_charge_status,
                self.coordinator.data.smart_control_enabled,
            )
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

        if not actions:
            return

        try:
            for action in actions:
                if action.operation == CHARGING_OPERATION_BOOST:
                    await self.coordinator.client.async_update_boost_charge(
                        device_id=self.coordinator.device_id,
                        action=action.action,
                    )
                elif action.operation == CHARGING_OPERATION_SMART_CONTROL:
                    await self.coordinator.client.async_update_device_smart_control(
                        device_id=self.coordinator.device_id,
                        action=action.action,
                    )
        except (OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError) as err:
            await self.coordinator.async_request_refresh()
            raise HomeAssistantError(str(err)) from err

        await self.coordinator.async_request_refresh()
