"""Button entities for immediate Octopus Intelligent Go charging commands."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError
from .const import DOMAIN
from .coordinator import OctopusIntelligentGoCoordinator
from .entity import OctopusIntelligentGoEntity


@dataclass(frozen=True, kw_only=True)
class OctopusIntelligentGoButtonDescription(ButtonEntityDescription):
    """Describe an immediate-charging command button."""

    action: str


BUTTON_DESCRIPTIONS = (
    OctopusIntelligentGoButtonDescription(
        key="start_immediate_charge",
        name="Start charging now",
        icon="mdi:play-circle-outline",
        action="BOOST",
    ),
    OctopusIntelligentGoButtonDescription(
        key="cancel_immediate_charge",
        name="Stop charging",
        icon="mdi:stop-circle-outline",
        action="CANCEL",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up immediate-charging command buttons."""
    coordinator: OctopusIntelligentGoCoordinator = entry.runtime_data.coordinator
    _remove_superseded_immediate_charge_entities(hass, coordinator.device_id)
    async_add_entities(
        OctopusIntelligentGoChargingButton(coordinator, description)
        for description in BUTTON_DESCRIPTIONS
    )


class OctopusIntelligentGoChargingButton(OctopusIntelligentGoEntity, ButtonEntity):
    """Send a deterministic immediate-charging command."""

    entity_description: OctopusIntelligentGoButtonDescription

    def __init__(
        self,
        coordinator: OctopusIntelligentGoCoordinator,
        entity_description: OctopusIntelligentGoButtonDescription,
    ) -> None:
        super().__init__(coordinator, entity_description)

    async def async_press(self) -> None:
        """Start or stop immediate charging."""
        try:
            await self.coordinator.client.async_update_boost_charge(
                device_id=self.coordinator.device_id,
                action=self.entity_description.action,
            )
        except (OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError) as err:
            raise HomeAssistantError(str(err)) from err

        await self.coordinator.async_request_refresh()


def _remove_superseded_immediate_charge_entities(
    hass: HomeAssistant,
    device_id: str,
) -> None:
    """Remove entities replaced by the two command buttons."""
    entity_registry = er.async_get(hass)
    superseded_entities = (
        ("switch", f"{device_id}_immediate_charge"),
        ("button", f"{device_id}_immediate_charge"),
        ("button", f"{device_id}_smart_immediate_charge"),
        ("button", f"{device_id}_start_stop_immediate_charge"),
    )

    for platform, unique_id in superseded_entities:
        entity_id = entity_registry.async_get_entity_id(platform, DOMAIN, unique_id)
        if entity_id:
            entity_registry.async_remove(entity_id)
