"""Tests for pure Octopus Intelligent Go data helpers."""

from __future__ import annotations

import pytest

from custom_components.octopus_intelligent_go.data import (
    CHARGING_MODE_CHARGE_NOW,
    CHARGING_MODE_PAUSED,
    CHARGING_MODE_SCHEDULED,
    IntelligentGoData,
    as_float,
    charging_mode_actions,
    charging_mode_from_status,
    immediate_charge_active_from_state,
    immediate_charge_status_from_state,
    normalize_state,
)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("BOOST", True),
        ("boost_charging", True),
        (" immediate_charge_active ", True),
        ("BUMP_CHARGE_ACTIVE", True),
        ("SMART_CONTROL_NOT_AVAILABLE", False),
        ("smart_control_available", False),
        ("boost_cancelled", False),
        ("immediate_charge_failed", False),
        ("something_else", False),
        (" ", None),
        (None, None),
    ],
)
def test_immediate_charge_active_from_state(
    state: str | None, expected: bool | None
) -> None:
    assert immediate_charge_active_from_state(state) is expected


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("BOOST_REQUESTED", "starting"),
        ("immediate_charge_starting", "starting"),
        ("BOOST", "running"),
        ("boost_charging", "running"),
        ("BUMP_CHARGE_ACTIVE", "running"),
        ("BOOST_CANCELLING", "stopping"),
        ("immediate_charge_stopping", "stopping"),
        ("BOOST_CANCELLED", "stopped"),
        ("immediate_charge_failed", "failed"),
        ("SMART_CONTROL_IN_PROGRESS", "stopped"),
        ("something_else", "stopped"),
        (" ", None),
        (None, None),
    ],
)
def test_immediate_charge_status_from_state(
    state: str | None,
    expected: str | None,
) -> None:
    assert immediate_charge_status_from_state(state) == expected


@pytest.mark.parametrize(
    ("status", "smart_control_enabled", "expected"),
    [
        ("starting", True, CHARGING_MODE_CHARGE_NOW),
        ("running", False, CHARGING_MODE_CHARGE_NOW),
        ("stopping", True, CHARGING_MODE_CHARGE_NOW),
        ("stopped", True, CHARGING_MODE_SCHEDULED),
        ("failed", True, CHARGING_MODE_SCHEDULED),
        ("stopped", False, CHARGING_MODE_PAUSED),
        ("failed", False, CHARGING_MODE_PAUSED),
        (None, True, None),
        ("stopped", None, None),
    ],
)
def test_charging_mode_from_status(
    status: str | None,
    smart_control_enabled: bool | None,
    expected: str | None,
) -> None:
    assert charging_mode_from_status(status, smart_control_enabled) == expected


@pytest.mark.parametrize(
    ("mode", "status", "smart_control_enabled", "expected"),
    [
        (CHARGING_MODE_SCHEDULED, "running", True, [("boost", "CANCEL")]),
        (
            CHARGING_MODE_SCHEDULED,
            "running",
            False,
            [("boost", "CANCEL"), ("smart_control", "UNSUSPEND")],
        ),
        (CHARGING_MODE_SCHEDULED, "stopped", True, []),
        (
            CHARGING_MODE_SCHEDULED,
            "stopped",
            False,
            [("smart_control", "UNSUSPEND")],
        ),
        (CHARGING_MODE_CHARGE_NOW, "stopped", True, [("boost", "BOOST")]),
        (
            CHARGING_MODE_CHARGE_NOW,
            "stopped",
            False,
            [("smart_control", "UNSUSPEND"), ("boost", "BOOST")],
        ),
        (CHARGING_MODE_CHARGE_NOW, "running", True, []),
        (
            CHARGING_MODE_CHARGE_NOW,
            "running",
            False,
            [("smart_control", "UNSUSPEND")],
        ),
        (CHARGING_MODE_CHARGE_NOW, "stopping", True, [("boost", "BOOST")]),
        (
            CHARGING_MODE_PAUSED,
            "running",
            True,
            [("boost", "CANCEL"), ("smart_control", "SUSPEND")],
        ),
        (
            CHARGING_MODE_PAUSED,
            "stopped",
            True,
            [("smart_control", "SUSPEND")],
        ),
        (CHARGING_MODE_PAUSED, "stopped", False, []),
    ],
)
def test_charging_mode_actions(
    mode: str,
    status: str,
    smart_control_enabled: bool,
    expected: list[tuple[str, str]],
) -> None:
    actions = charging_mode_actions(mode, status, smart_control_enabled)

    assert [(action.operation, action.action) for action in actions] == expected


@pytest.mark.parametrize(
    ("mode", "status", "smart_control_enabled"),
    [
        ("unsupported", "stopped", True),
        (CHARGING_MODE_SCHEDULED, None, True),
        (CHARGING_MODE_SCHEDULED, "stopped", None),
    ],
)
def test_charging_mode_actions_rejects_invalid_or_unavailable_state(
    mode: str,
    status: str | None,
    smart_control_enabled: bool | None,
) -> None:
    with pytest.raises(ValueError):
        charging_mode_actions(mode, status, smart_control_enabled)


def test_intelligent_go_data_normalizes_device_payloads() -> None:
    data = IntelligentGoData(
        preferences_device={
            "status": {"isSuspended": False},
            "preferences": {
                "schedules": [
                    "not-a-schedule",
                    {"dayOfWeek": "MONDAY", "time": "07:30", "max": True},
                    {"dayOfWeek": "TUESDAY", "time": "07:30", "max": "69.5"},
                ]
            },
        },
        state_device={"status": {"currentState": "BOOST_ACTIVE"}},
        charge_capability_device={
            "status": {
                "stateOfCharge": {"value": "56.7"},
                "stateOfChargeLimit": {"upperSocLimit": 80},
            }
        },
    )

    assert data.schedules == [
        {"dayOfWeek": "MONDAY", "time": "07:30", "max": True},
        {"dayOfWeek": "TUESDAY", "time": "07:30", "max": "69.5"},
    ]
    assert data.target_charge_percentage == 69.5
    assert data.current_state == "BOOST_ACTIVE"
    assert data.immediate_charge_active is True
    assert data.immediate_charge_status == "running"
    assert data.charging_mode == CHARGING_MODE_CHARGE_NOW
    assert data.smart_control_enabled is True
    assert data.state_of_charge == 56.7
    assert data.vehicle_charge_limit == 80.0


def test_intelligent_go_data_uses_current_fallback_for_state() -> None:
    data = IntelligentGoData(
        preferences_device={},
        state_device={"status": {"current": "SMART_CONTROL_NOT_AVAILABLE"}},
        charge_capability_device={},
    )

    assert data.current_state == "SMART_CONTROL_NOT_AVAILABLE"
    assert data.immediate_charge_active is False
    assert data.immediate_charge_status == "stopped"


def test_intelligent_go_data_tolerates_malformed_payloads() -> None:
    data = IntelligentGoData(
        preferences_device={"preferences": "not-a-dict"},
        state_device={"status": "not-a-dict"},
        charge_capability_device={
            "status": {"stateOfCharge": "bad", "stateOfChargeLimit": "bad"}
        },
    )

    assert data.preferences == {}
    assert data.schedules == []
    assert data.target_charge_percentage is None
    assert data.current_state is None
    assert data.immediate_charge_active is None
    assert data.immediate_charge_status is None
    assert data.charging_mode is None
    assert data.smart_control_enabled is None
    assert data.state_of_charge is None
    assert data.vehicle_charge_limit is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ({"isSuspended": False}, True),
        ({"isSuspended": True}, False),
        ({"isSuspended": "false"}, None),
        ({}, None),
        ("not-a-dict", None),
    ],
)
def test_smart_control_enabled_from_suspension_state(
    status: object,
    expected: bool | None,
) -> None:
    data = IntelligentGoData(
        preferences_device={"status": status},
        state_device={},
        charge_capability_device={},
    )

    assert data.smart_control_enabled is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (69, 69.0),
        (69.5, 69.5),
        ("69.5", 69.5),
        (True, None),
        (False, None),
        ("not-a-number", None),
        (None, None),
    ],
)
def test_as_float(value: object, expected: float | None) -> None:
    assert as_float(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" boost_active ", "BOOST_ACTIVE"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalize_state(value: str | None, expected: str | None) -> None:
    assert normalize_state(value) == expected
