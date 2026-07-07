"""Constants for the Octopus Intelligent Go integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "octopus_intelligent_go"

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
]

GRAPHQL_URL = "https://api.oees-kraken.energy/v1/graphql/"
DEFAULT_USER_AGENT = "OctoAppClient/Android/4.134.0 (Android 16; emu64a)"

CONF_ACCOUNT_NUMBER = "account_number"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_TYPE = "device_type"
CONF_PROVIDER = "provider"
CONF_REFRESH_EXPIRES_IN = "refresh_expires_in"
CONF_REFRESH_TOKEN = "refresh_token"

SERVICE_CANCEL_IMMEDIATE_CHARGE = "cancel_immediate_charge"
SERVICE_START_IMMEDIATE_CHARGE = "start_immediate_charge"

DAYS = [
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
]

DEFAULT_READY_TIME = "07:30"
