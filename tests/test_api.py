"""Tests for Kraken GraphQL API helpers."""

from __future__ import annotations

import pytest

from custom_components.octopus_intelligent_go.api import (
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
