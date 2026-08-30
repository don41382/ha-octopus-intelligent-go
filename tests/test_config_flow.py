"""Tests for Octopus Intelligent Go config-flow credential handling."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.octopus_intelligent_go.api import AuthToken
from custom_components.octopus_intelligent_go import config_flow as config_flow_module
from custom_components.octopus_intelligent_go.config_flow import (
    NoDevicesError,
    OctopusIntelligentGoConfigFlow,
)
from custom_components.octopus_intelligent_go.const import (
    CONF_ACCOUNT_NUMBER,
    CONF_DEVICE_ID,
)


class _ClientWithoutDevices:
    """Fake client that records whether API-key creation was attempted."""

    def __init__(self) -> None:
        self.api_key_requested = False

    async def async_login_email_password(
        self,
        email: str,
        password: str,
    ) -> AuthToken:
        return AuthToken("access-token", "refresh-token", 123)

    async def async_get_account_numbers(self) -> list[str]:
        return ["A-123"]

    async def async_get_intelligent_go_devices(
        self,
        account_number: str,
        device_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return []

    async def async_get_or_create_api_key(self) -> str:
        self.api_key_requested = True
        return "generated-api-key"


def test_setup_does_not_create_api_key_without_compatible_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run_test() -> None:
        client = _ClientWithoutDevices()
        monkeypatch.setattr(
            config_flow_module,
            "OctopusIntelligentGoClient",
            lambda session: client,
        )
        flow = OctopusIntelligentGoConfigFlow()
        flow.hass = object()

        with pytest.raises(NoDevicesError):
            await flow._async_login_and_discover(
                {"email": "customer@example.com", "password": "password"}
            )

        assert client.api_key_requested is False

    asyncio.run(run_test())


def test_reauth_does_not_create_api_key_when_device_was_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run_test() -> None:
        client = _ClientWithoutDevices()
        monkeypatch.setattr(
            config_flow_module,
            "OctopusIntelligentGoClient",
            lambda session: client,
        )
        flow = OctopusIntelligentGoConfigFlow()
        flow.hass = object()

        with pytest.raises(NoDevicesError):
            await flow._async_validate_credentials_for_entry(
                {"email": "customer@example.com", "password": "password"},
                {CONF_ACCOUNT_NUMBER: "A-123", CONF_DEVICE_ID: "device-123"},
            )

        assert client.api_key_requested is False

    asyncio.run(run_test())
