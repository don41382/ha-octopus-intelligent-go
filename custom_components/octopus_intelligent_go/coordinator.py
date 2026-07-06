"""Coordinator for Octopus Intelligent Go entities."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

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

_LOGGER = logging.getLogger(__name__)


@dataclass
class IntelligentGoData:
    """Normalized Intelligent Go data shared by all entities."""

    preferences_device: dict[str, Any]
    state_device: dict[str, Any]
    charge_capability_device: dict[str, Any]

    @property
    def preferences(self) -> dict[str, Any]:
        preferences = self.preferences_device.get("preferences") or {}
        return preferences if isinstance(preferences, dict) else {}

    @property
    def schedules(self) -> list[dict[str, Any]]:
        schedules = self.preferences.get("schedules") or []
        return [schedule for schedule in schedules if isinstance(schedule, dict)]

    @property
    def target_charge_percentage(self) -> float | None:
        for schedule in self.schedules:
            value = _as_float(schedule.get("max"))
            if value is not None:
                return value
        return None

    @property
    def current_state(self) -> str | None:
        status = self.state_device.get("status") or {}
        if not isinstance(status, dict):
            return None
        value = status.get("currentState") or status.get("current")
        return value if isinstance(value, str) else None

    @property
    def state_of_charge(self) -> float | None:
        status = self.charge_capability_device.get("status") or {}
        if not isinstance(status, dict):
            return None
        state_of_charge = status.get("stateOfCharge") or {}
        if not isinstance(state_of_charge, dict):
            return None
        return _as_float(state_of_charge.get("value"))

    @property
    def vehicle_charge_limit(self) -> float | None:
        status = self.charge_capability_device.get("status") or {}
        if not isinstance(status, dict):
            return None
        charge_limit = status.get("stateOfChargeLimit") or {}
        if not isinstance(charge_limit, dict):
            return None
        return _as_float(charge_limit.get("upperSocLimit"))


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


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
