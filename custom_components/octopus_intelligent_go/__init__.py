"""Home Assistant integration for Octopus Intelligent Go."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    AuthToken,
    OctopusIntelligentGoApiError,
    OctopusIntelligentGoAuthError,
    OctopusIntelligentGoClient,
)
from .const import (
    CONF_DEVICE_ID,
    CONF_REFRESH_EXPIRES_IN,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    PLATFORMS,
    SERVICE_CANCEL_IMMEDIATE_CHARGE,
    SERVICE_START_IMMEDIATE_CHARGE,
)
from .coordinator import OctopusIntelligentGoCoordinator

IMMEDIATE_CHARGE_SERVICE_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): str})


@dataclass
class OctopusIntelligentGoRuntimeData:
    """Runtime data stored on the config entry."""

    client: OctopusIntelligentGoClient
    coordinator: OctopusIntelligentGoCoordinator


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up Octopus Intelligent Go services."""

    async def start_immediate_charge(call: ServiceCall) -> None:
        await _async_update_immediate_charge(hass, call, "BOOST")

    async def cancel_immediate_charge(call: ServiceCall) -> None:
        await _async_update_immediate_charge(hass, call, "CANCEL")

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_IMMEDIATE_CHARGE,
        start_immediate_charge,
        schema=IMMEDIATE_CHARGE_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_IMMEDIATE_CHARGE,
        cancel_immediate_charge,
        schema=IMMEDIATE_CHARGE_SERVICE_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Octopus Intelligent Go from a config entry."""

    def store_auth(auth: AuthToken) -> None:
        if not auth.refresh_token:
            return
        data = dict(entry.data)
        if (
            data.get(CONF_REFRESH_TOKEN) == auth.refresh_token
            and data.get(CONF_REFRESH_EXPIRES_IN) == auth.refresh_expires_in
        ):
            return
        data[CONF_REFRESH_TOKEN] = auth.refresh_token
        data[CONF_REFRESH_EXPIRES_IN] = auth.refresh_expires_in
        hass.config_entries.async_update_entry(entry, data=data)

    client = OctopusIntelligentGoClient(
        async_get_clientsession(hass),
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        on_auth_updated=store_auth,
    )
    coordinator = OctopusIntelligentGoCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = OctopusIntelligentGoRuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Octopus Intelligent Go config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_immediate_charge(
    hass: HomeAssistant,
    call: ServiceCall,
    action: str,
) -> None:
    device_id = call.data[ATTR_DEVICE_ID]
    entry = _entry_for_device_id(hass, device_id)
    if entry is None:
        raise HomeAssistantError(f"No Octopus Intelligent Go device found for {device_id}")

    runtime_data = getattr(entry, "runtime_data", None)
    if runtime_data is None:
        raise HomeAssistantError("Octopus Intelligent Go config entry is not loaded")

    try:
        await runtime_data.client.async_update_boost_charge(
            device_id=runtime_data.coordinator.device_id,
            action=action,
        )
    except (OctopusIntelligentGoApiError, OctopusIntelligentGoAuthError) as err:
        raise HomeAssistantError(str(err)) from err

    await runtime_data.coordinator.async_request_refresh()


def _entry_for_device_id(hass: HomeAssistant, device_id: str) -> ConfigEntry | None:
    """Return the entry matching a Home Assistant or Kraken device ID."""
    device = dr.async_get(hass).async_get(device_id)
    if device is not None:
        for domain, identifier in device.identifiers:
            if domain == DOMAIN:
                return _entry_for_kraken_device_id(hass, identifier)

    return _entry_for_kraken_device_id(hass, device_id)


def _entry_for_kraken_device_id(hass: HomeAssistant, device_id: str) -> ConfigEntry | None:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_DEVICE_ID) == device_id:
            return entry
    return None
