"""Tests for Kraken GraphQL API helpers."""

from __future__ import annotations

import asyncio
from http.cookies import SimpleCookie
from typing import Any

import pytest

from custom_components.octopus_intelligent_go.api import (
    AuthToken,
    OctopusIntelligentGoClient,
    OctopusIntelligentGoApiError,
    OctopusIntelligentGoAuthError,
    _decode_response,
    _errors_are_auth_related,
    _format_graphql_errors,
    _parse_auth,
    _prepare_percentage_schedules,
)
from custom_components.octopus_intelligent_go.const import DAYS, DEFAULT_READY_TIME


def test_prepare_percentage_schedules_preserves_known_times_and_fills_missing_days() -> None:
    schedules = [
        {"dayOfWeek": "MONDAY", "time": "06:45", "min": 20, "max": 50},
        {"dayOfWeek": "MONDAY", "time": "08:00", "max": 70},
        {"dayOfWeek": "TUESDAY", "time": 123, "max": 70},
    ]

    prepared = _prepare_percentage_schedules(80, schedules)

    assert len(prepared) == 7
    assert [schedule["dayOfWeek"] for schedule in prepared] == DAYS
    assert prepared[0] == {"dayOfWeek": "MONDAY", "time": "06:45", "max": 80.0, "min": 20.0}
    assert prepared[1] == {"dayOfWeek": "TUESDAY", "time": DEFAULT_READY_TIME, "max": 80.0}


def test_prepare_percentage_schedules_builds_default_week_when_empty() -> None:
    prepared = _prepare_percentage_schedules(60.5, None)

    assert len(prepared) == 7
    assert all(schedule["time"] == DEFAULT_READY_TIME for schedule in prepared)
    assert all(schedule["max"] == 60.5 for schedule in prepared)


def test_format_graphql_errors_humanizes_boost_refusal_reasons() -> None:
    errors = [
        {
            "message": "Unable to trigger boost charge.",
            "extensions": {
                "errorCode": "KT-CT-4357",
                "errorDescription": "An internal error occurred. Please try again later.",
                "boostChargeRefusalReasons": [
                    "BC_DEVICE_DISCONNECTED",
                    "BC_DEVICE_NOT_AT_HOME",
                ],
            },
        }
    ]

    assert (
        _format_graphql_errors(errors)
        == "Immediate charging cannot be started because the vehicle is not plugged in "
        "and the vehicle is not at home. (KT-CT-4357)"
    )


def test_format_graphql_errors_humanizes_unknown_refusal_reason() -> None:
    errors = [
        {
            "message": "Unable to trigger boost charge.",
            "extensions": {
                "errorCode": "KT-CT-9999",
                "boostChargeRefusalReasons": ["BC_DEVICE_SLEEPING"],
            },
        }
    ]

    assert _format_graphql_errors(errors) == "Unable to trigger boost charge: device sleeping. (KT-CT-9999)"


@pytest.mark.parametrize(
    "errors",
    [
        [{"extensions": {"errorCode": "KT-CT-1124"}}],
        [{"message": "JWT has expired"}],
        [{"extensions": {"errorDescription": "Refresh token expired"}}],
        [{"extensions": {"validationErrors": [{"inputPath": ["input", "password"]}]}}],
        [
            {
                "extensions": {
                    "errorCode": "KT-CT-1139",
                    "validationErrors": [{"inputPath": ["input", "APIKey"]}],
                }
            }
        ],
    ],
)
def test_errors_are_auth_related(errors: list[dict[str, object]]) -> None:
    assert _errors_are_auth_related(errors) is True


def test_errors_are_auth_related_rejects_application_error() -> None:
    errors = [{"message": "Unable to trigger boost charge", "extensions": {"errorCode": "KT-CT-4357"}}]

    assert _errors_are_auth_related(errors) is False


def test_parse_auth_accepts_valid_token_payload() -> None:
    auth = _parse_auth(
        {
            "data": {
                "obtainKrakenToken": {
                    "token": "access-token",
                    "refreshToken": "refresh-token",
                    "refreshExpiresIn": 123,
                }
            }
        }
    )

    assert auth.token == "access-token"
    assert auth.refresh_token == "refresh-token"
    assert auth.refresh_expires_in == 123


def test_parse_auth_rejects_missing_access_token() -> None:
    with pytest.raises(OctopusIntelligentGoAuthError, match="access token"):
        _parse_auth({"data": {"obtainKrakenToken": {"refreshToken": "refresh-token"}}})


def test_decode_response_rejects_non_json() -> None:
    with pytest.raises(OctopusIntelligentGoApiError, match="response is not JSON"):
        _decode_response(b"not json", "application/json")


def test_api_key_login_uses_api_key_input_and_stores_rotated_token() -> None:
    async def run_test() -> None:
        updates: list[AuthToken] = []
        calls: list[dict[str, Any]] = []
        client = OctopusIntelligentGoClient(
            None,  # type: ignore[arg-type]
            api_key="account-api-key",
            on_auth_updated=updates.append,
        )

        async def fake_graphql(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return _auth_response("access-token", "refresh-token", 123)

        client._graphql = fake_graphql  # type: ignore[method-assign]

        auth = await client.async_login_api_key()

        assert auth.refresh_token == "refresh-token"
        assert calls[0]["variables"] == {"input": {"APIKey": "account-api-key"}}
        assert calls[0]["flapjack"] is True
        assert updates == [auth]

    asyncio.run(run_test())


def test_spanish_credentials_are_exchanged_for_api_key_then_token() -> None:
    async def run_test() -> None:
        calls: list[dict[str, Any]] = []
        client = OctopusIntelligentGoClient(None)  # type: ignore[arg-type]

        async def fake_get_api_key(email: str, password: str) -> str:
            assert email == "customer@example.com"
            assert password == "one-time-password"
            return "spanish-account-api-key"

        async def fake_graphql(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return _auth_response("access-token", "refresh-token", 123)

        client._async_get_api_key_with_credentials = fake_get_api_key  # type: ignore[method-assign]
        client._graphql = fake_graphql  # type: ignore[method-assign]

        auth = await client.async_login_email_password(
            "customer@example.com",
            "one-time-password",
        )

        assert auth.refresh_token == "refresh-token"
        assert client.api_key == "spanish-account-api-key"
        assert calls[0]["variables"] == {
            "input": {"APIKey": "spanish-account-api-key"}
        }

    asyncio.run(run_test())


def test_spanish_portal_login_uses_session_cookies_to_read_api_key() -> None:
    async def run_test() -> None:
        login_cookies = SimpleCookie()
        login_cookies["accessToken"] = "encrypted-access"
        login_cookies["refreshToken"] = "encrypted-refresh"
        session = _FakeSession(
            [
                _FakeResponse(b'{"authenticated":true}', cookies=login_cookies),
                _FakeResponse(
                    b'{"data":{"viewer":{"liveSecretKey":"sk_live_spain"}}}'
                ),
            ]
        )
        client = OctopusIntelligentGoClient(session)  # type: ignore[arg-type]

        api_key = await client._async_get_api_key_with_credentials(
            "customer@example.com",
            "one-time-password",
        )

        assert api_key == "sk_live_spain"
        assert session.calls[0]["json"] == {
            "email": "customer@example.com",
            "password": "one-time-password",
        }
        cookie_header = session.calls[1]["headers"]["cookie"]
        assert "accessToken=encrypted-access" in cookie_header
        assert "refreshToken=encrypted-refresh" in cookie_header

    asyncio.run(run_test())


def test_authenticated_query_captures_spanish_account_api_key() -> None:
    async def run_test() -> None:
        updates: list[str] = []
        client = OctopusIntelligentGoClient(
            None,  # type: ignore[arg-type]
            access_token="access-token",
            on_api_key_updated=updates.append,
        )

        async def fake_graphql(**kwargs: Any) -> dict[str, Any]:
            return {
                "data": {
                    "viewer": {"liveSecretKey": "sk_live_discovered"},
                    "devices": [],
                }
            }

        client._graphql = fake_graphql  # type: ignore[method-assign]

        await client._authenticated_graphql(
            operation_name="GetSmartFlexDevicePreferences",
            query="query { viewer { liveSecretKey } }",
            variables={},
        )

        assert client.api_key == "sk_live_discovered"
        assert updates == ["sk_live_discovered"]

    asyncio.run(run_test())


def test_concurrent_startup_requests_share_one_refresh() -> None:
    async def run_test() -> None:
        login_calls = 0
        client = OctopusIntelligentGoClient(
            None,  # type: ignore[arg-type]
            refresh_token="old-refresh-token",
        )

        async def fake_graphql(**kwargs: Any) -> dict[str, Any]:
            nonlocal login_calls
            if kwargs["operation_name"] == "Login":
                login_calls += 1
                assert kwargs["variables"] == {
                    "input": {"refreshToken": "old-refresh-token"}
                }
                await asyncio.sleep(0)
                return _auth_response("new-access-token", "new-refresh-token", 456)
            return {"token_used": kwargs["token"]}

        client._graphql = fake_graphql  # type: ignore[method-assign]

        results = await asyncio.gather(
            *(
                client._authenticated_graphql(
                    operation_name=f"Query{index}",
                    query="query { viewer { __typename } }",
                    variables={},
                )
                for index in range(3)
            )
        )

        assert login_calls == 1
        assert results == [{"token_used": "new-access-token"}] * 3

    asyncio.run(run_test())


def test_concurrent_expired_access_token_errors_share_one_refresh() -> None:
    async def run_test() -> None:
        login_calls = 0
        client = OctopusIntelligentGoClient(
            None,  # type: ignore[arg-type]
            access_token="expired-access-token",
            refresh_token="refresh-token",
        )

        async def fake_graphql(**kwargs: Any) -> dict[str, Any]:
            nonlocal login_calls
            if kwargs["operation_name"] == "Login":
                login_calls += 1
                await asyncio.sleep(0)
                return _auth_response("new-access-token", "new-refresh-token", 789)
            if kwargs["token"] == "expired-access-token":
                await asyncio.sleep(0)
                raise OctopusIntelligentGoAuthError("JWT expired")
            return {"token_used": kwargs["token"]}

        client._graphql = fake_graphql  # type: ignore[method-assign]

        results = await asyncio.gather(
            *(
                client._authenticated_graphql(
                    operation_name=f"Query{index}",
                    query="query { viewer { __typename } }",
                    variables={},
                )
                for index in range(3)
            )
        )

        assert login_calls == 1
        assert results == [{"token_used": "new-access-token"}] * 3

    asyncio.run(run_test())


def test_expired_refresh_token_falls_back_to_api_key() -> None:
    async def run_test() -> None:
        login_inputs: list[dict[str, str]] = []
        updates: list[AuthToken] = []
        client = OctopusIntelligentGoClient(
            None,  # type: ignore[arg-type]
            api_key="account-api-key",
            refresh_token="expired-refresh-token",
            on_auth_updated=updates.append,
        )

        async def fake_graphql(**kwargs: Any) -> dict[str, Any]:
            login_input = kwargs["variables"]["input"]
            login_inputs.append(login_input)
            if "refreshToken" in login_input:
                raise OctopusIntelligentGoAuthError("refresh token expired")
            return _auth_response("api-key-access", "api-key-refresh", 999)

        client._graphql = fake_graphql  # type: ignore[method-assign]

        await client._ensure_access_token()

        assert login_inputs == [
            {"refreshToken": "expired-refresh-token"},
            {"APIKey": "account-api-key"},
        ]
        assert updates == [
            AuthToken(
                token="api-key-access",
                refresh_token="api-key-refresh",
                refresh_expires_in=999,
            )
        ]

    asyncio.run(run_test())


def test_expired_refresh_token_without_api_key_still_requires_reauth() -> None:
    async def run_test() -> None:
        client = OctopusIntelligentGoClient(
            None,  # type: ignore[arg-type]
            refresh_token="expired-refresh-token",
        )

        async def fake_graphql(**kwargs: Any) -> dict[str, Any]:
            raise OctopusIntelligentGoAuthError("refresh token expired")

        client._graphql = fake_graphql  # type: ignore[method-assign]

        with pytest.raises(OctopusIntelligentGoAuthError, match="expired"):
            await client._ensure_access_token()

    asyncio.run(run_test())


def _auth_response(
    access_token: str,
    refresh_token: str,
    refresh_expires_in: int,
) -> dict[str, Any]:
    return {
        "data": {
            "obtainKrakenToken": {
                "token": access_token,
                "refreshToken": refresh_token,
                "refreshExpiresIn": refresh_expires_in,
            }
        }
    }


class _FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        cookies: SimpleCookie[str] | None = None,
    ) -> None:
        self._body = body
        self.status = status
        self.cookies = cookies or SimpleCookie()
        self.headers = {"content-type": "application/json"}

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def read(self) -> bytes:
        return self._body


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = iter(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return next(self._responses)
