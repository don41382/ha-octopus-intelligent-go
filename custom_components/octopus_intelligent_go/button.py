"""Button entities for Octopus Intelligent Go."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError
from .const import DOMAIN
from .coordinator import OctopusIntelligentGoCoordinator
from .data import immediate_charge_action, immediate_charge_icon, immediate_charge_name
from .entity import OctopusIntelligentGoEntity

IMMEDIATE_CHARGE_DESCRIPTION = ButtonEntityDescription(
    key="start_stop_immediate_charge",
    name="Start/Stop Immediate",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Octopus Intelligent Go button entities."""
    coordinator: OctopusIntelligentGoCoordinator = entry.runtime_data.coordinator
    _remove_legacy_immediate_charge_entities(hass, coordinator.device_id)
    async_add_entities([OctopusIntelligentGoImmediateChargeButton(coordinator)])


class OctopusIntelligentGoImmediateChargeButton(OctopusIntelligentGoEntity, ButtonEntity):
    """Start or cancel immediate charging depending on current state."""

    def __init__(self, coordinator: OctopusIntelligentGoCoordinator) -> None:
        super().__init__(coordinator, IMMEDIATE_CHARGE_DESCRIPTION)

    @property
    def name(self) -> str:
        """Return an action-oriented name."""
        return immediate_charge_name(self._immediate_charge_active)

    @property
    def icon(self) -> str:
        """Return a play/stop icon matching the next action."""
        return immediate_charge_icon(self._immediate_charge_active)

    async def async_press(self) -> None:
        """Start or cancel immediate charging."""
        action = immediate_charge_action(self._immediate_charge_active)
        try:
            await self.coordinator.client.async_update_boost_charge(
                device_id=self.coordinator.device_id,
                action=action,
            )
        except (OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError) as err:
            raise HomeAssistantError(str(err)) from err

        await self.coordinator.async_request_refresh()

    @property
    def _immediate_charge_active(self) -> bool:
        return self.coordinator.data.immediate_charge_active is True


def _remove_legacy_immediate_charge_entities(hass: HomeAssistant, device_id: str) -> None:
    """Remove entities superseded by the dynamic immediate charge button."""
    entity_registry = er.async_get(hass)
    legacy_entities = (
        ("button", f"{device_id}_start_immediate_charge"),
        ("button", f"{device_id}_cancel_immediate_charge"),
        ("button", f"{device_id}_immediate_charge"),
        ("button", f"{device_id}_smart_immediate_charge"),
        ("switch", f"{device_id}_immediate_charge"),
    )

    for platform, unique_id in legacy_entities:
        entity_id = entity_registry.async_get_entity_id(
            platform,
            DOMAIN,
            unique_id,
        )
        if entity_id:
            entity_registry.async_remove(entity_id)
