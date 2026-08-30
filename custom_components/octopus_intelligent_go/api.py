"""Async Kraken GraphQL client for Octopus Intelligent Go."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import json
import secrets
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import (
    DAYS,
    DEFAULT_READY_TIME,
    DEFAULT_USER_AGENT,
    GRAPHQL_URL,
)

LOGIN_MUTATION = """
mutation Login($input: ObtainJSONWebTokenInput!) {
  obtainKrakenToken(input: $input) {
    __typename
    refreshExpiresIn
    refreshToken
    token
  }
}
""".strip()

REGENERATE_SECRET_KEY_MUTATION = """
mutation RegenerateSecretKey {
  regenerateSecretKey {
    __typename
    key
  }
}
""".strip()

GET_ACCOUNT_LIST_QUERY = """
query GetAccountList {
  viewer {
    __typename
    liveSecretKey
    accounts {
      __typename
      number
    }
  }
}
""".strip()

GET_SMART_FLEX_DEVICES_QUERY = """
query GetSmartFlexDevices($accountNumber: String!, $deviceId: String) {
  devices(accountNumber: $accountNumber, deviceId: $deviceId) {
    __typename
    id
    name
    deviceType
    provider
    propertyId
    integrationDeviceId
    status {
      __typename
      current
      isSuspended
    }
    preferences {
      __typename
      gridExport
    }
    ... on SmartFlexVehicle {
      make
    }
  }
}
""".strip()

GET_SMART_FLEX_DEVICE_PREFERENCES_QUERY = """
query GetSmartFlexDevicePreferences($accountNumber: String!, $deviceId: String) {
  viewer {
    __typename
    liveSecretKey
  }
  devices(accountNumber: $accountNumber, deviceId: $deviceId) {
    __typename
    id
    status {
      __typename
      isSuspended
    }
    preferences {
      __typename
      targetType
      unit
      mode
      gridExport
      schedules {
        __typename
        dayOfWeek
        time
        min
        max
        upperLimit
      }
      isChargingDurationCapped
    }
  }
}
""".strip()

GET_SMART_FLEX_DEVICE_STATE_QUERY = """
query GetSmartFlexDeviceState($accountNumber: String!, $deviceID: String!) {
  devices(accountNumber: $accountNumber, deviceId: $deviceID) {
    __typename
    id
    status {
      __typename
      currentState
    }
  }
}
""".strip()

GET_SMART_FLEX_DEVICE_CHARGE_CAPABILITY_QUERY = """
query GetSmartFlexDeviceChargeCapability($deviceId: String, $accountNumber: String!) {
  devices(deviceId: $deviceId, accountNumber: $accountNumber) {
    __typename
    id
    ... on SmartFlexVehicle {
      chargePointPowerOutput
      vehicleBatterySize
      status {
        __typename
        ... on SmartFlexVehicleStatus {
          stateOfCharge {
            __typename
            value
          }
          stateOfChargeLimit {
            __typename
            upperSocLimit
          }
        }
      }
    }
    ... on SmartFlexChargePoint {
      chargePointPowerOutput
      vehicleBatterySize
    }
  }
}
""".strip()

SET_DEVICE_PREFERENCES_MUTATION = """
mutation SetSmartFlexDevicePreferences($input: SmartFlexDevicePreferencesInput!) {
  setDevicePreferences(input: $input) {
    __typename
    id
    preferences {
      __typename
      targetType
      unit
      mode
      schedules {
        __typename
        dayOfWeek
        time
        min
        max
      }
    }
  }
}
""".strip()

BOOST_CHARGE_MUTATION = """
mutation FlexUpdateBoostCharge($input: UpdateBoostChargeInput!) {
  updateBoostCharge(input: $input) {
    __typename
    id
    provider
    deviceType
  }
}
""".strip()

UPDATE_DEVICE_SMART_CONTROL_MUTATION = """
mutation UpdateDeviceSmartControl($input: SmartControlInput!) {
  updateDeviceSmartControl(input: $input) {
    __typename
    id
    status {
      __typename
      isSuspended
    }
  }
}
""".strip()

BOOST_CHARGE_REFUSAL_REASONS = {
    "BC_DEVICE_DISCONNECTED": "the vehicle is not plugged in",
    "BC_DEVICE_NOT_AT_HOME": "the vehicle is not at home",
    "BC_DEVICE_SUSPENDED": "smart charging is suspended",
}


class OctopusIntelligentGoError(Exception):
    """Base error for Octopus Intelligent Go API failures."""


class OctopusIntelligentGoAuthError(OctopusIntelligentGoError):
    """Authentication or authorization failed."""


class OctopusIntelligentGoApiError(OctopusIntelligentGoError):
    """The Kraken API returned an unexpected or failed response."""


@dataclass(frozen=True)
class AuthToken:
    """Kraken auth token response."""

    token: str
    refresh_token: str | None = None
    refresh_expires_in: int | None = None


AuthUpdatedCallback = Callable[[AuthToken], None]
ApiKeyUpdatedCallback = Callable[[str], None]


class OctopusIntelligentGoClient:
    """Small async client for the Kraken GraphQL SmartFlex API."""

    def __init__(
        self,
        session: ClientSession,
        *,
        api_key: str | None = None,
        refresh_token: str | None = None,
        access_token: str | None = None,
        graphql_url: str = GRAPHQL_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        on_auth_updated: AuthUpdatedCallback | None = None,
        on_api_key_updated: ApiKeyUpdatedCallback | None = None,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._refresh_token = refresh_token
        self._access_token = access_token
        self._graphql_url = graphql_url
        self._user_agent = user_agent
        self._on_auth_updated = on_auth_updated
        self._on_api_key_updated = on_api_key_updated
        self._auth_lock = asyncio.Lock()

    @property
    def api_key(self) -> str | None:
        """Return the account API key discovered during authentication."""
        return self._api_key

    async def async_login_email_password(self, email: str, password: str) -> AuthToken:
        """Authenticate once with Spain Kraken credentials."""
        data = await self._graphql(
            operation_name="Login",
            query=LOGIN_MUTATION,
            variables={"input": {"email": email, "password": password}},
            flapjack=True,
        )
        auth = _parse_auth(data)
        self._apply_auth(auth)
        return auth

    async def async_login_api_key(self, api_key: str | None = None) -> AuthToken:
        """Authenticate with a long-lived Octopus account API key."""
        key = api_key or self._api_key
        if not key:
            raise OctopusIntelligentGoAuthError("missing API key")

        data = await self._graphql(
            operation_name="Login",
            query=LOGIN_MUTATION,
            variables={"input": {"APIKey": key}},
            flapjack=True,
        )
        auth = _parse_auth(data)
        self._set_api_key(key)
        self._apply_auth(auth)
        return auth

    async def async_login_refresh_token(self, refresh_token: str | None = None) -> AuthToken:
        """Authenticate with an existing refresh token."""
        token = refresh_token or self._refresh_token
        if not token:
            raise OctopusIntelligentGoAuthError("missing refresh token")

        data = await self._graphql(
            operation_name="Login",
            query=LOGIN_MUTATION,
            variables={"input": {"refreshToken": token}},
            flapjack=True,
        )
        auth = _parse_auth(data)
        self._apply_auth(auth, fallback_refresh_token=token)
        return auth

    async def async_get_account_numbers(self) -> list[str]:
        """Return account numbers for the authenticated viewer."""
        data = await self._authenticated_graphql(
            operation_name="GetAccountList",
            query=GET_ACCOUNT_LIST_QUERY,
            variables={},
        )
        accounts = data.get("data", {}).get("viewer", {}).get("accounts") or []
        return [
            account["number"]
            for account in accounts
            if isinstance(account, dict) and isinstance(account.get("number"), str)
        ]

    async def async_get_or_create_api_key(self) -> str:
        """Return the viewer API key, generating one when none exists."""
        if self._api_key:
            return self._api_key

        data = await self._authenticated_graphql(
            operation_name="RegenerateSecretKey",
            query=REGENERATE_SECRET_KEY_MUTATION,
            variables={},
        )
        secret_key = data.get("data", {}).get("regenerateSecretKey")
        api_key = secret_key.get("key") if isinstance(secret_key, dict) else None
        if not isinstance(api_key, str) or not api_key:
            raise OctopusIntelligentGoApiError(
                "API-key generation response did not include a key"
            )
        self._set_api_key(api_key)
        return api_key

    async def async_get_intelligent_go_devices(
        self,
        account_number: str,
        device_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return Intelligent Go devices for an account."""
        data = await self._authenticated_graphql(
            operation_name="GetSmartFlexDevices",
            query=GET_SMART_FLEX_DEVICES_QUERY,
            variables={"accountNumber": account_number, "deviceId": device_id},
        )
        return _devices_from_response(data)

    async def async_get_device_preferences(
        self,
        account_number: str,
        device_id: str,
    ) -> dict[str, Any]:
        """Return device preferences payload for one Intelligent Go device."""
        data = await self._authenticated_graphql(
            operation_name="GetSmartFlexDevicePreferences",
            query=GET_SMART_FLEX_DEVICE_PREFERENCES_QUERY,
            variables={"accountNumber": account_number, "deviceId": device_id},
        )
        return _first_device_or_raise(data, device_id)

    async def async_get_device_state(
        self,
        account_number: str,
        device_id: str,
    ) -> dict[str, Any]:
        """Return device state payload for one Intelligent Go device."""
        data = await self._authenticated_graphql(
            operation_name="GetSmartFlexDeviceState",
            query=GET_SMART_FLEX_DEVICE_STATE_QUERY,
            variables={"accountNumber": account_number, "deviceID": device_id},
        )
        return _first_device_or_raise(data, device_id)

    async def async_get_device_charge_capability(
        self,
        account_number: str,
        device_id: str,
    ) -> dict[str, Any]:
        """Return vehicle charge capability payload for one Intelligent Go device."""
        data = await self._authenticated_graphql(
            operation_name="GetSmartFlexDeviceChargeCapability",
            query=GET_SMART_FLEX_DEVICE_CHARGE_CAPABILITY_QUERY,
            variables={"accountNumber": account_number, "deviceId": device_id},
        )
        return _first_device_or_raise(data, device_id)

    async def async_set_max_percentage(
        self,
        *,
        device_id: str,
        percent: float,
        schedules: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Set the max charging percentage, preserving known schedule days/times."""
        prepared_schedules = _prepare_percentage_schedules(percent, schedules)
        return await self._authenticated_graphql(
            operation_name="SetSmartFlexDevicePreferences",
            query=SET_DEVICE_PREFERENCES_MUTATION,
            variables={
                "input": {
                    "deviceId": device_id,
                    "mode": "CHARGE",
                    "unit": "PERCENTAGE",
                    "schedules": prepared_schedules,
                }
            },
        )

    async def async_update_boost_charge(self, *, device_id: str, action: str) -> dict[str, Any]:
        """Start or cancel immediate charging."""
        return await self._authenticated_graphql(
            operation_name="FlexUpdateBoostCharge",
            query=BOOST_CHARGE_MUTATION,
            variables={"input": {"deviceId": device_id, "action": action}},
        )

    async def async_update_device_smart_control(
        self,
        *,
        device_id: str,
        action: str,
    ) -> dict[str, Any]:
        """Suspend or resume SmartFlex control for a device."""
        return await self._authenticated_graphql(
            operation_name="UpdateDeviceSmartControl",
            query=UPDATE_DEVICE_SMART_CONTROL_MUTATION,
            variables={"input": {"deviceId": device_id, "action": action}},
        )

    async def _authenticated_graphql(
        self,
        *,
        operation_name: str,
        query: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        await self._ensure_access_token()
        attempted_token = self._access_token
        try:
            data = await self._graphql(
                operation_name=operation_name,
                query=query,
                variables=variables,
                token=attempted_token,
            )
        except OctopusIntelligentGoAuthError:
            await self._refresh_after_auth_error(attempted_token)
            data = await self._graphql(
                operation_name=operation_name,
                query=query,
                variables=variables,
                token=self._access_token,
            )
        self._capture_api_key(data)
        return data

    async def _ensure_access_token(self) -> None:
        if self._access_token:
            return

        async with self._auth_lock:
            if self._access_token:
                return
            await self._authenticate()

    async def _refresh_after_auth_error(self, attempted_token: str | None) -> None:
        """Refresh once for the token that failed, coalescing concurrent failures."""
        async with self._auth_lock:
            if self._access_token and self._access_token != attempted_token:
                return
            self._access_token = None
            await self._authenticate()

    async def _authenticate(self) -> None:
        """Authenticate with the refresh token, falling back to the API key."""
        if self._refresh_token:
            try:
                await self.async_login_refresh_token()
                return
            except OctopusIntelligentGoAuthError:
                if not self._api_key:
                    raise
                self._refresh_token = None

        if self._api_key:
            await self.async_login_api_key()
            return

        raise OctopusIntelligentGoAuthError("missing refresh token and API key")

    def _apply_auth(self, auth: AuthToken, fallback_refresh_token: str | None = None) -> None:
        self._access_token = auth.token
        if auth.refresh_token:
            self._refresh_token = auth.refresh_token
            if self._on_auth_updated:
                self._on_auth_updated(auth)
        elif fallback_refresh_token:
            self._refresh_token = fallback_refresh_token

    def _capture_api_key(self, data: dict[str, Any]) -> None:
        viewer = data.get("data", {}).get("viewer")
        if not isinstance(viewer, dict):
            return
        api_key = viewer.get("liveSecretKey")
        if isinstance(api_key, str) and api_key:
            self._set_api_key(api_key)

    def _set_api_key(self, api_key: str) -> None:
        if self._api_key == api_key:
            return
        self._api_key = api_key
        if self._on_api_key_updated:
            self._on_api_key_updated(api_key)

    async def _graphql(
        self,
        *,
        operation_name: str,
        query: str,
        variables: dict[str, Any],
        token: str | None = None,
        flapjack: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "query": query,
            "operationName": operation_name,
            "variables": variables,
            "extensions": {"clientLibrary": {"name": "apollo-kotlin", "version": "5.0.0"}},
        }
        headers = {
            "x-apollo-operation-name": operation_name,
            "accept": "multipart/mixed;deferSpec=20220824, application/graphql-response+json, application/json",
            "accept-language": "en-US",
            "user-agent": self._user_agent,
            "content-type": "application/json",
        }
        if token:
            headers["authorization"] = token
        if flapjack:
            headers["x-kraken-flapjack"] = secrets.token_hex(32)

        try:
            async with self._session.post(
                self._graphql_url,
                params={"debug_op_name": operation_name},
                json=payload,
                headers=headers,
                timeout=ClientTimeout(total=30),
            ) as response:
                raw = await response.read()
                content_type = response.headers.get("content-type", "")
                data = _decode_response(raw, content_type)
                if response.status in (401, 403):
                    raise OctopusIntelligentGoAuthError(f"HTTP {response.status}: {data!r}")
                if response.status >= 400:
                    raise OctopusIntelligentGoApiError(f"HTTP {response.status}: {data!r}")
        except (ClientError, asyncio.TimeoutError) as exc:
            raise OctopusIntelligentGoApiError(f"request failed: {exc}") from exc

        if isinstance(data, dict) and data.get("errors"):
            errors = data["errors"]
            if _errors_are_auth_related(errors):
                raise OctopusIntelligentGoAuthError(_format_graphql_errors(errors))
            raise OctopusIntelligentGoApiError(_format_graphql_errors(errors))
        if not isinstance(data, dict):
            raise OctopusIntelligentGoApiError(f"unexpected response: {data!r}")
        return data


def _parse_auth(data: dict[str, Any]) -> AuthToken:
    token_data = data.get("data", {}).get("obtainKrakenToken")
    if not isinstance(token_data, dict):
        raise OctopusIntelligentGoApiError("login response did not include token data")
    token = token_data.get("token")
    if not isinstance(token, str) or not token:
        raise OctopusIntelligentGoAuthError("login response did not include an access token")
    refresh_expires_in = token_data.get("refreshExpiresIn")
    if not isinstance(refresh_expires_in, int):
        refresh_expires_in = None
    return AuthToken(
        token=token,
        refresh_token=token_data.get("refreshToken"),
        refresh_expires_in=refresh_expires_in,
    )


def _decode_response(raw: bytes, content_type: str) -> Any:
    text = raw.decode("utf-8", errors="replace")
    if "multipart/mixed" in content_type:
        return _decode_multipart_json(text, content_type)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise OctopusIntelligentGoApiError(f"response is not JSON: {text[:500]}") from exc


def _decode_multipart_json(text: str, content_type: str) -> Any:
    boundary = ""
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part.split("=", 1)[1].strip('"')
            break
    if not boundary:
        raise OctopusIntelligentGoApiError("multipart response did not include a boundary")
    for chunk in text.split("--" + boundary):
        if "\r\n\r\n" in chunk:
            _, body = chunk.split("\r\n\r\n", 1)
        elif "\n\n" in chunk:
            _, body = chunk.split("\n\n", 1)
        else:
            continue
        body = body.strip()
        if body and body != "--":
            return json.loads(body)
    raise OctopusIntelligentGoApiError("multipart response did not include a JSON body")


def _errors_are_auth_related(errors: Any) -> bool:
    if not isinstance(errors, list):
        return False
    for error in errors:
        if not isinstance(error, dict):
            continue
        message = str(error.get("message") or "").upper()
        extensions = error.get("extensions") or {}
        if not isinstance(extensions, dict):
            extensions = {}
        error_code = str(extensions.get("errorCode") or extensions.get("code") or "").upper()
        error_type = str(extensions.get("errorType") or extensions.get("errorClass") or "").upper()
        description = str(extensions.get("errorDescription") or "").upper()
        validation_errors = extensions.get("validationErrors") or []

        if error_code in {"KT-CT-1124", "KT-CT-1134", "KT-CT-1138", "KT-CT-1139"}:
            return True
        if "AUTH" in error_type or "UNAUTHENTICATED" in error_code:
            return True
        if "TOKEN" in message or "TOKEN" in description:
            return True
        if "JWT" in message or "JWT" in description:
            return True
        if "EXPIRED" in message or "EXPIRED" in description:
            return True
        if "CREDENTIAL" in message or "CREDENTIAL" in description:
            return True
        if isinstance(validation_errors, list):
            for validation_error in validation_errors:
                if not isinstance(validation_error, dict):
                    continue
                input_path = validation_error.get("inputPath") or []
                if any(
                    part in {"APIKey", "email", "password", "refreshToken"}
                    for part in input_path
                ):
                    return True
    return False


def _format_graphql_errors(errors: Any) -> str:
    if not isinstance(errors, list):
        return "Octopus Intelligent Go API returned an error."

    messages = []
    for error in errors:
        if not isinstance(error, dict):
            continue

        extensions = error.get("extensions") or {}
        if not isinstance(extensions, dict):
            extensions = {}

        message = _clean_error_text(error.get("message"))
        description = _clean_error_text(extensions.get("errorDescription"))
        code = _clean_error_text(extensions.get("errorCode"))
        refusal_reason = _format_refusal_reasons(extensions.get("boostChargeRefusalReasons"))

        base = message or description or "Octopus Intelligent Go API returned an error"
        if refusal_reason:
            if code == "KT-CT-4357":
                base = f"Immediate charging cannot be started because {refusal_reason}"
            else:
                base = f"{base}: {refusal_reason}"
        elif description and description.lower() != base.lower():
            base = f"{base}: {description}"
        if code:
            base = f"{base}. ({code})"
        else:
            base = f"{base}."
        messages.append(base)

    return " ".join(messages) if messages else "Octopus Intelligent Go API returned an error."


def _format_refusal_reasons(reasons: Any) -> str | None:
    if not isinstance(reasons, list):
        return None

    formatted = [
        BOOST_CHARGE_REFUSAL_REASONS.get(reason, _humanize_error_code(reason))
        for reason in reasons
        if isinstance(reason, str) and reason
    ]
    if not formatted:
        return None
    return _join_human_list(formatted)


def _clean_error_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned.rstrip(".")


def _humanize_error_code(value: str) -> str:
    text = value.removeprefix("BC_").lower().replace("_", " ")
    return text or value


def _join_human_list(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _devices_from_response(data: dict[str, Any]) -> list[dict[str, Any]]:
    devices = data.get("data", {}).get("devices") or []
    return [device for device in devices if isinstance(device, dict)]


def _first_device_or_raise(data: dict[str, Any], device_id: str) -> dict[str, Any]:
    devices = _devices_from_response(data)
    if not devices:
        raise OctopusIntelligentGoApiError(f"no device returned for {device_id}")
    return devices[0]


def _prepare_percentage_schedules(
    percent: float,
    schedules: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not schedules:
        schedules = [{"dayOfWeek": day, "time": DEFAULT_READY_TIME} for day in DAYS]

    prepared: list[dict[str, Any]] = []
    seen_days: set[str] = set()
    for schedule in schedules:
        day = schedule.get("dayOfWeek")
        if not isinstance(day, str) or day in seen_days:
            continue
        seen_days.add(day)
        item: dict[str, Any] = {
            "dayOfWeek": day,
            "time": schedule.get("time") if isinstance(schedule.get("time"), str) else DEFAULT_READY_TIME,
            "max": float(percent),
        }
        minimum = schedule.get("min")
        if isinstance(minimum, int | float):
            item["min"] = float(minimum)
        prepared.append(item)

    for day in DAYS:
        if day not in seen_days:
            prepared.append({"dayOfWeek": day, "time": DEFAULT_READY_TIME, "max": float(percent)})

    return prepared
