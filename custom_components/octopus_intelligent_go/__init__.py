"""Home Assistant integration for Octopus Intelligent Go."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuthToken, OctopusIntelligentGoClient
from .const import (
    CONF_REFRESH_EXPIRES_IN,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import OctopusIntelligentGoCoordinator


@dataclass
class OctopusIntelligentGoRuntimeData:
    """Runtime data stored on the config entry."""

    client: OctopusIntelligentGoClient
    coordinator: OctopusIntelligentGoCoordinator


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
