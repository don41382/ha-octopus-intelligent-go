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
    SENSOR = "sensor"


homeassistant = types.ModuleType("homeassistant")
homeassistant_const = types.ModuleType("homeassistant.const")
homeassistant_const.Platform = Platform
sys.modules.setdefault("homeassistant", homeassistant)
sys.modules["homeassistant.const"] = homeassistant_const
