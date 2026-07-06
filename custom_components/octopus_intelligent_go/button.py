"""Button entities for Octopus Intelligent Go."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError
from .coordinator import OctopusIntelligentGoCoordinator
from .entity import OctopusIntelligentGoEntity


@dataclass(frozen=True, kw_only=True)
class OctopusIntelligentGoButtonDescription(ButtonEntityDescription):
    """Button entity description with a boost action."""

    action: str


BUTTON_DESCRIPTIONS = (
    OctopusIntelligentGoButtonDescription(
        key="start_immediate_charge",
        name="Start immediate charge",
        action="BOOST",
    ),
    OctopusIntelligentGoButtonDescription(
        key="cancel_immediate_charge",
        name="Cancel immediate charge",
        action="CANCEL",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Octopus Intelligent Go button entities."""
    coordinator: OctopusIntelligentGoCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        OctopusIntelligentGoBoostButton(coordinator, description)
        for description in BUTTON_DESCRIPTIONS
    )


class OctopusIntelligentGoBoostButton(OctopusIntelligentGoEntity, ButtonEntity):
    """Immediate charging command button."""

    entity_description: OctopusIntelligentGoButtonDescription

    def __init__(
        self,
        coordinator: OctopusIntelligentGoCoordinator,
        entity_description: OctopusIntelligentGoButtonDescription,
    ) -> None:
        super().__init__(coordinator, entity_description)

    async def async_press(self) -> None:
        """Send the boost/cancel command."""
        try:
            await self.coordinator.client.async_update_boost_charge(
                device_id=self.coordinator.device_id,
                action=self.entity_description.action,
            )
        except (OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError) as err:
            raise HomeAssistantError(str(err)) from err

        await self.coordinator.async_request_refresh()
