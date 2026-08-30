"""Switch entities for Octopus Intelligent Go charging controls."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError
from .const import DOMAIN
from .coordinator import OctopusIntelligentGoCoordinator
from .entity import OctopusIntelligentGoEntity

IMMEDIATE_CHARGE_DESCRIPTION = SwitchEntityDescription(
    key="immediate_charge",
    name="Immediate charging",
    icon="mdi:ev-station",
)

SMART_CHARGING_DESCRIPTION = SwitchEntityDescription(
    key="smart_charging",
    name="Smart charging",
    icon="mdi:calendar-clock",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Octopus Intelligent Go switch entities."""
    coordinator: OctopusIntelligentGoCoordinator = entry.runtime_data.coordinator
    _remove_legacy_immediate_charge_buttons(hass, coordinator.device_id)
    async_add_entities(
        [
            OctopusIntelligentGoImmediateChargeSwitch(coordinator),
            OctopusIntelligentGoSmartChargingSwitch(coordinator),
        ]
    )


class OctopusIntelligentGoImmediateChargeSwitch(
    OctopusIntelligentGoEntity,
    SwitchEntity,
):
    """Start or cancel immediate boost charging."""

    def __init__(self, coordinator: OctopusIntelligentGoCoordinator) -> None:
        super().__init__(coordinator, IMMEDIATE_CHARGE_DESCRIPTION)

    @property
    def is_on(self) -> bool | None:
        """Return whether immediate boost charging is active."""
        return self.coordinator.data.immediate_charge_active

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start immediate boost charging."""
        await self._async_update("BOOST")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Cancel immediate boost charging."""
        await self._async_update("CANCEL")

    async def _async_update(self, action: str) -> None:
        try:
            await self.coordinator.client.async_update_boost_charge(
                device_id=self.coordinator.device_id,
                action=action,
            )
        except (OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError) as err:
            raise HomeAssistantError(str(err)) from err

        await self.coordinator.async_request_refresh()


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


def _remove_legacy_immediate_charge_buttons(
    hass: HomeAssistant,
    device_id: str,
) -> None:
    """Remove button entities superseded by the immediate-charging switch."""
    entity_registry = er.async_get(hass)
    legacy_unique_ids = (
        f"{device_id}_start_immediate_charge",
        f"{device_id}_cancel_immediate_charge",
        f"{device_id}_immediate_charge",
        f"{device_id}_smart_immediate_charge",
        f"{device_id}_start_stop_immediate_charge",
    )

    for unique_id in legacy_unique_ids:
        entity_id = entity_registry.async_get_entity_id(
            "button",
            DOMAIN,
            unique_id,
        )
        if entity_id:
            entity_registry.async_remove(entity_id)
