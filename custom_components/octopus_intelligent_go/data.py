"""Pure data helpers for Octopus Intelligent Go."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

IMMEDIATE_CHARGE_ACTIVE_STATES = {
    "BUMP_CHARGE",
    "BUMP_CHARGE_ACTIVE",
    "BUMP_CHARGING",
    "BOOST",
    "BOOST_ACTIVE",
    "BOOST_CHARGE",
    "BOOST_CHARGE_ACTIVE",
    "BOOST_CHARGING",
    "BOOST_IN_PROGRESS",
    "BOOSTING",
    "IMMEDIATE_CHARGE",
    "IMMEDIATE_CHARGE_ACTIVE",
    "IMMEDIATE_CHARGING",
}

IMMEDIATE_CHARGE_INACTIVE_STATES = {
    "AVAILABLE",
    "AWAITING_DISPATCH",
    "DISCONNECTED",
    "IDLE",
    "NOT_AT_HOME",
    "NOT_AVAILABLE",
    "PLANNED",
    "PLUGGED_IN",
    "READY",
    "SMART_CONTROL_NOT_AVAILABLE",
    "SMART_CONTROL_AVAILABLE",
    "SMART_CONTROL_OFF",
    "SUSPENDED",
    "UNAVAILABLE",
}

IMMEDIATE_CHARGE_NEGATIVE_MARKERS = ("CANCEL", "STOP", "ENDED", "FAILED")

IMMEDIATE_CHARGE_STARTING_MARKERS = (
    "INITIATING",
    "PENDING",
    "REQUESTED",
    "STARTING",
)

IMMEDIATE_CHARGE_STOPPING_MARKERS = (
    "CANCELING",
    "CANCELLING",
    "STOPPING",
)

IMMEDIATE_CHARGE_FAILED_MARKERS = ("ERROR", "FAILED", "REFUSED")

CHARGING_MODE_SCHEDULED = "scheduled"
CHARGING_MODE_CHARGE_NOW = "charge_now"
CHARGING_MODE_PAUSED = "paused"
CHARGING_MODES = (
    CHARGING_MODE_SCHEDULED,
    CHARGING_MODE_CHARGE_NOW,
    CHARGING_MODE_PAUSED,
)

CHARGING_OPERATION_BOOST = "boost"
CHARGING_OPERATION_SMART_CONTROL = "smart_control"

IMMEDIATE_CHARGE_ACTIVE_STATUSES = {"starting", "running"}
IMMEDIATE_CHARGE_IN_PROGRESS_STATUSES = {
    *IMMEDIATE_CHARGE_ACTIVE_STATUSES,
    "stopping",
}


@dataclass(frozen=True)
class ChargingModeAction:
    """One Kraken mutation needed to reach a charging mode."""

    operation: str
    action: str


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
            value = as_float(schedule.get("max"))
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
    def immediate_charge_active(self) -> bool | None:
        """Return whether immediate charging appears active from device state."""
        return immediate_charge_active_from_state(self.current_state)

    @property
    def immediate_charge_status(self) -> str | None:
        """Return a user-facing immediate-charging lifecycle state."""
        return immediate_charge_status_from_state(self.current_state)

    @property
    def charging_mode(self) -> str | None:
        """Return the combined immediate/scheduled charging mode."""
        return charging_mode_from_status(
            self.immediate_charge_status,
            self.smart_control_enabled,
        )

    @property
    def smart_control_enabled(self) -> bool | None:
        """Return whether Octopus smart scheduling is enabled."""
        status = self.preferences_device.get("status") or {}
        if not isinstance(status, dict):
            return None
        is_suspended = status.get("isSuspended")
        if not isinstance(is_suspended, bool):
            return None
        return not is_suspended

    @property
    def state_of_charge(self) -> float | None:
        status = self.charge_capability_device.get("status") or {}
        if not isinstance(status, dict):
            return None
        state_of_charge = status.get("stateOfCharge") or {}
        if not isinstance(state_of_charge, dict):
            return None
        return as_float(state_of_charge.get("value"))

    @property
    def vehicle_charge_limit(self) -> float | None:
        status = self.charge_capability_device.get("status") or {}
        if not isinstance(status, dict):
            return None
        charge_limit = status.get("stateOfChargeLimit") or {}
        if not isinstance(charge_limit, dict):
            return None
        return as_float(charge_limit.get("upperSocLimit"))


def immediate_charge_active_from_state(value: str | None) -> bool | None:
    """Return the active/inactive immediate-charge state for a Kraken state string."""
    state = normalize_state(value)
    if state is None:
        return None
    if state in IMMEDIATE_CHARGE_ACTIVE_STATES:
        return True
    if state in IMMEDIATE_CHARGE_INACTIVE_STATES:
        return False
    if any(marker in state for marker in ("BOOST", "BUMP", "IMMEDIATE")):
        return not any(marker in state for marker in IMMEDIATE_CHARGE_NEGATIVE_MARKERS)
    return False


def immediate_charge_status_from_state(value: str | None) -> str | None:
    """Return a normalized immediate-charging lifecycle state."""
    state = normalize_state(value)
    if state is None:
        return None

    is_immediate_charge_state = any(
        marker in state for marker in ("BOOST", "BUMP", "IMMEDIATE")
    )
    if not is_immediate_charge_state:
        return "stopped"
    if any(marker in state for marker in IMMEDIATE_CHARGE_FAILED_MARKERS):
        return "failed"
    if any(marker in state for marker in IMMEDIATE_CHARGE_STOPPING_MARKERS):
        return "stopping"
    if any(marker in state for marker in IMMEDIATE_CHARGE_STARTING_MARKERS):
        return "starting"
    if any(marker in state for marker in ("CANCELED", "CANCELLED", "ENDED", "STOPPED")):
        return "stopped"
    if immediate_charge_active_from_state(state):
        return "running"
    return "stopped"


def charging_mode_from_status(
    immediate_charge_status: str | None,
    smart_control_enabled: bool | None,
) -> str | None:
    """Derive the combined charging mode from Kraken readback."""
    if immediate_charge_status is None or smart_control_enabled is None:
        return None
    if immediate_charge_status in IMMEDIATE_CHARGE_IN_PROGRESS_STATUSES:
        return CHARGING_MODE_CHARGE_NOW
    if smart_control_enabled:
        return CHARGING_MODE_SCHEDULED
    return CHARGING_MODE_PAUSED


def charging_mode_actions(
    charging_mode: str,
    immediate_charge_status: str | None,
    smart_control_enabled: bool | None,
) -> tuple[ChargingModeAction, ...]:
    """Plan the minimum ordered mutations needed to reach a charging mode."""
    if charging_mode not in CHARGING_MODES:
        raise ValueError(f"Unsupported charging mode: {charging_mode}")
    if immediate_charge_status is None or smart_control_enabled is None:
        raise ValueError("Charging state is unavailable")

    actions: list[ChargingModeAction] = []
    immediate_charge_active = (
        immediate_charge_status in IMMEDIATE_CHARGE_ACTIVE_STATUSES
    )

    if charging_mode == CHARGING_MODE_SCHEDULED:
        if immediate_charge_active:
            actions.append(ChargingModeAction(CHARGING_OPERATION_BOOST, "CANCEL"))
        if not smart_control_enabled:
            actions.append(
                ChargingModeAction(CHARGING_OPERATION_SMART_CONTROL, "UNSUSPEND")
            )
    elif charging_mode == CHARGING_MODE_CHARGE_NOW:
        if not smart_control_enabled:
            actions.append(
                ChargingModeAction(CHARGING_OPERATION_SMART_CONTROL, "UNSUSPEND")
            )
        if not immediate_charge_active:
            actions.append(ChargingModeAction(CHARGING_OPERATION_BOOST, "BOOST"))
    else:
        if immediate_charge_active:
            actions.append(ChargingModeAction(CHARGING_OPERATION_BOOST, "CANCEL"))
        if smart_control_enabled:
            actions.append(
                ChargingModeAction(CHARGING_OPERATION_SMART_CONTROL, "SUSPEND")
            )

    return tuple(actions)


def as_float(value: Any) -> float | None:
    """Return a float for numeric API values, excluding booleans."""
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


def normalize_state(value: str | None) -> str | None:
    """Return an uppercase state string or None."""
    if not isinstance(value, str):
        return None
    state = value.strip().upper()
    return state or None
