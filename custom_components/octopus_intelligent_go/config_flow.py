"""Config flow for Octopus Intelligent Go."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import (
    AuthToken,
    OctopusIntelligentGoApiError,
    OctopusIntelligentGoAuthError,
    OctopusIntelligentGoClient,
)
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_API_KEY,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_PROVIDER,
    CONF_REFRESH_EXPIRES_IN,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class NoAccountsError(Exception):
    """No Octopus accounts were found for the login."""


class NoDevicesError(Exception):
    """No compatible Intelligent Go devices were found for the account."""


class OctopusIntelligentGoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Octopus Intelligent Go config flow."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                auth, api_key, account_number, device = (
                    await self._async_login_and_discover(user_input)
                )
            except OctopusIntelligentGoAuthError:
                errors["base"] = "invalid_auth"
            except NoAccountsError:
                errors["base"] = "no_accounts"
            except NoDevicesError:
                errors["base"] = "no_devices"
            except OctopusIntelligentGoApiError as err:
                _LOGGER.debug("Octopus Intelligent Go setup failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected Octopus Intelligent Go setup error")
                errors["base"] = "unknown"
            else:
                device_id = device["id"]
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_entry_title(device),
                    data=_entry_data(
                        auth,
                        api_key,
                        account_number,
                        device,
                    ),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_credentials_schema(),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> config_entries.ConfigFlowResult:
        """Handle reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Obtain a fresh refresh token using a one-time account login."""
        entry = self.hass.config_entries.async_get_entry(
            str(self.context.get("entry_id") or "")
        )
        if entry is None:
            return self.async_abort(reason="unknown")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                auth, api_key = await self._async_validate_credentials_for_entry(
                    user_input,
                    entry.data,
                )
            except OctopusIntelligentGoAuthError:
                errors["base"] = "invalid_auth"
            except NoDevicesError:
                errors["base"] = "no_devices"
            except OctopusIntelligentGoApiError as err:
                _LOGGER.debug("Octopus Intelligent Go reconfigure failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected Octopus Intelligent Go reconfigure error")
                errors["base"] = "unknown"
            else:
                data = _updated_auth_data(entry.data, api_key, auth)
                self.hass.config_entries.async_update_entry(entry, data=data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_credentials_schema(),
            errors=errors,
        )

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Confirm reauthentication credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(
                str(self.context.get("entry_id") or "")
            )
            if entry is None:
                return self.async_abort(reason="unknown")

            try:
                auth, api_key = await self._async_validate_credentials_for_entry(
                    user_input,
                    entry.data,
                )
            except OctopusIntelligentGoAuthError:
                errors["base"] = "invalid_auth"
            except NoDevicesError:
                errors["base"] = "no_devices"
            except OctopusIntelligentGoApiError as err:
                _LOGGER.debug("Octopus Intelligent Go reauth failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected Octopus Intelligent Go reauth error")
                errors["base"] = "unknown"
            else:
                data = _updated_auth_data(entry.data, api_key, auth)
                self.hass.config_entries.async_update_entry(entry, data=data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_credentials_schema(),
            errors=errors,
        )

    async def _async_login_and_discover(
        self,
        user_input: dict[str, Any],
    ) -> tuple[AuthToken, str | None, str, dict[str, Any]]:
        client = OctopusIntelligentGoClient(async_get_clientsession(self.hass))
        auth = await client.async_login_email_password(
            user_input[CONF_EMAIL],
            user_input[CONF_PASSWORD],
        )
        if not auth.refresh_token:
            raise OctopusIntelligentGoAuthError("login response did not include a refresh token")
        api_key = client.api_key

        accounts = await client.async_get_account_numbers()
        if not accounts:
            raise NoAccountsError

        account_number = accounts[0]
        devices = await client.async_get_intelligent_go_devices(account_number)
        if not devices:
            raise NoDevicesError

        device = devices[0]
        if not isinstance(device.get("id"), str):
            raise OctopusIntelligentGoApiError("first compatible device did not include an id")
        return auth, api_key, account_number, device

    async def _async_validate_credentials_for_entry(
        self,
        user_input: dict[str, Any],
        entry_data: dict[str, Any],
    ) -> tuple[AuthToken, str | None]:
        client = OctopusIntelligentGoClient(async_get_clientsession(self.hass))
        auth = await client.async_login_email_password(
            user_input[CONF_EMAIL],
            user_input[CONF_PASSWORD],
        )
        if not auth.refresh_token:
            raise OctopusIntelligentGoAuthError(
                "login response did not include a refresh token"
            )
        api_key = client.api_key

        devices = await client.async_get_intelligent_go_devices(
            entry_data[CONF_ACCOUNT_NUMBER],
            entry_data[CONF_DEVICE_ID],
        )
        if not devices:
            raise NoDevicesError
        return auth, api_key


def _credentials_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_EMAIL): str,
            vol.Required(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }
    )


def _entry_title(device: dict[str, Any]) -> str:
    name = device.get("name")
    if isinstance(name, str) and name:
        return name
    provider = device.get("provider")
    device_type = device.get("deviceType")
    if isinstance(provider, str) and isinstance(device_type, str):
        return f"{provider} {device_type}".replace("_", " ").title()
    return "Octopus Intelligent Go"


def _entry_data(
    auth: AuthToken,
    api_key: str | None,
    account_number: str,
    device: dict[str, Any],
) -> dict[str, Any]:
    if not auth.refresh_token:
        raise OctopusIntelligentGoAuthError("login response did not include a refresh token")
    data = {
        CONF_REFRESH_TOKEN: auth.refresh_token,
        CONF_REFRESH_EXPIRES_IN: auth.refresh_expires_in,
        CONF_ACCOUNT_NUMBER: account_number,
        CONF_DEVICE_ID: device["id"],
        CONF_DEVICE_NAME: device.get("name"),
        CONF_DEVICE_TYPE: device.get("deviceType"),
        CONF_PROVIDER: device.get("provider"),
    }
    if api_key:
        data[CONF_API_KEY] = api_key
    return data


def _updated_auth_data(
    entry_data: dict[str, Any],
    api_key: str | None,
    auth: AuthToken,
) -> dict[str, Any]:
    if not auth.refresh_token:
        raise OctopusIntelligentGoAuthError("login response did not include a refresh token")
    data = dict(entry_data)
    if api_key:
        data[CONF_API_KEY] = api_key
    data[CONF_REFRESH_TOKEN] = auth.refresh_token
    data[CONF_REFRESH_EXPIRES_IN] = auth.refresh_expires_in
    return data
