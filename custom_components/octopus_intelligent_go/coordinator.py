"""Coordinator for Octopus Intelligent Go entities."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    OctopusIntelligentGoApiError,
    OctopusIntelligentGoAuthError,
    OctopusIntelligentGoClient,
)
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_PROVIDER,
    DOMAIN,
)
from .data import IntelligentGoData

_LOGGER = logging.getLogger(__name__)


class OctopusIntelligentGoCoordinator(DataUpdateCoordinator[IntelligentGoData]):
    """DataUpdateCoordinator for one Intelligent Go device."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: OctopusIntelligentGoClient,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=120),
            always_update=False,
        )
        self.client = client
        self.account_number = entry.data[CONF_ACCOUNT_NUMBER]
        self.device_id = entry.data[CONF_DEVICE_ID]
        self.device_name = entry.data.get(CONF_DEVICE_NAME) or "Intelligent Go device"
        self.device_type = entry.data.get(CONF_DEVICE_TYPE)
        self.provider = entry.data.get(CONF_PROVIDER)

    async def _async_update_data(self) -> IntelligentGoData:
        try:
            preferences_device, state_device, capability_device = await asyncio.gather(
                self.client.async_get_device_preferences(self.account_number, self.device_id),
                self.client.async_get_device_state(self.account_number, self.device_id),
                self.client.async_get_device_charge_capability(self.account_number, self.device_id),
            )
        except OctopusIntelligentGoAuthError as err:
            raise ConfigEntryAuthFailed from err
        except OctopusIntelligentGoApiError as err:
            raise UpdateFailed(str(err)) from err

        return IntelligentGoData(
            preferences_device=preferences_device,
            state_device=state_device,
            charge_capability_device=capability_device,
        )
