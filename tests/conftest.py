"""Pytest bootstrap for testing pure integration modules without Home Assistant."""

from __future__ import annotations

from pathlib import Path
from enum import StrEnum
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
CUSTOM_COMPONENTS = ROOT / "custom_components"
INTEGRATION = CUSTOM_COMPONENTS / "octopus_intelligent_go"

custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(CUSTOM_COMPONENTS)]
sys.modules.setdefault("custom_components", custom_components)

octopus_intelligent_go = types.ModuleType("custom_components.octopus_intelligent_go")
octopus_intelligent_go.__path__ = [str(INTEGRATION)]
sys.modules["custom_components.octopus_intelligent_go"] = octopus_intelligent_go


class Platform(StrEnum):
    """Minimal Home Assistant Platform enum for pure module tests."""

    BUTTON = "button"
    NUMBER = "number"
    SELECT = "select"
    SENSOR = "sensor"
    SWITCH = "switch"


class ConfigFlow:
    """Minimal Home Assistant config flow base class."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__()


class TextSelectorType(StrEnum):
    """Minimal text selector type enum."""

    PASSWORD = "password"


class TextSelectorConfig:
    """Minimal text selector config."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class TextSelector:
    """Minimal text selector."""

    def __init__(self, config: TextSelectorConfig) -> None:
        self.config = config


homeassistant = types.ModuleType("homeassistant")
homeassistant.__path__ = []
homeassistant_config_entries = types.ModuleType("homeassistant.config_entries")
homeassistant_config_entries.ConfigFlow = ConfigFlow
homeassistant_config_entries.ConfigFlowResult = dict
homeassistant_const = types.ModuleType("homeassistant.const")
homeassistant_const.CONF_EMAIL = "email"
homeassistant_const.CONF_PASSWORD = "password"
homeassistant_const.Platform = Platform
homeassistant_helpers = types.ModuleType("homeassistant.helpers")
homeassistant_helpers.__path__ = []
homeassistant_aiohttp_client = types.ModuleType(
    "homeassistant.helpers.aiohttp_client"
)
homeassistant_aiohttp_client.async_get_clientsession = lambda hass: None
homeassistant_selector = types.ModuleType("homeassistant.helpers.selector")
homeassistant_selector.TextSelector = TextSelector
homeassistant_selector.TextSelectorConfig = TextSelectorConfig
homeassistant_selector.TextSelectorType = TextSelectorType
sys.modules.setdefault("homeassistant", homeassistant)
sys.modules["homeassistant.config_entries"] = homeassistant_config_entries
sys.modules["homeassistant.const"] = homeassistant_const
sys.modules["homeassistant.helpers"] = homeassistant_helpers
sys.modules["homeassistant.helpers.aiohttp_client"] = homeassistant_aiohttp_client
sys.modules["homeassistant.helpers.selector"] = homeassistant_selector
