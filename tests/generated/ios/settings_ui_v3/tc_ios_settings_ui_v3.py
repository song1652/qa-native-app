"""
tc_ios_settings_ui_v3.py — Ios tc_ios_settings_ui_v3: iOS Settings UI 검증 v3 TC.

Tests:
"""

import json
import subprocess
from pathlib import Path

from appium import webdriver
from appium.options.ios.xcuitest.base import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from scripts.hybrid_runtime import HybridSession


# --------------------------------------------------------------------------
# Selectors — generated from config/locators.json.
# Healing updates the registry, then regeneration updates this file.
# --------------------------------------------------------------------------
LOCATOR_SURFACES = {}

CONFIG_DIR = Path(__file__).parent.parent.parent.parent.parent / "config"
APPIUM_URL = "http://localhost:4723"
PLATFORM_MODE = "simulator"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_device_connected() -> None:
    result = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "booted"],
        capture_output=True, text=True
    )
    if "Booted" not in result.stdout:
        raise RuntimeError(
            "[ios_driver] No booted simulator found. "
            "Run: xcrun simctl boot <device_udid>"
        )


def _get_device(platform: str, mode: str) -> dict:
    _s = _load_json(CONFIG_DIR / "devices.json").get(platform, {}).get(mode)
    if isinstance(_s, dict):
        return _s
    if isinstance(_s, list):
        return next((d for d in _s if d.get("default")), _s[0] if _s else {})
    return {}


_NON_APPIUM_KEYS = frozenset({"default", "wifi_ip", "team_id", "label", "note"})


def _build_driver() -> webdriver.Remote:
    _raw = _get_device("ios", PLATFORM_MODE)
    test_data = _load_json(CONFIG_DIR / "test_data.json")

    caps = {k: v for k, v in _raw.items() if k not in _NON_APPIUM_KEYS}
    caps["platformName"] = "iOS"
    caps["bundleId"] = test_data["app"]["ios"]["bundle_id"]
    app_path = test_data["app"]["ios"]["app_path"]
    if app_path:
        caps["app"] = app_path

    options = XCUITestOptions().load_capabilities(caps)
    return webdriver.Remote(APPIUM_URL, options=options)


class TestSettingsUiV3:
    """tc_ios_settings_ui_v3: iOS Settings UI 검증 v3 화면 TC."""

    def setup_method(self):
        _check_device_connected()
        self.driver = _build_driver()
        self.hybrid = HybridSession(self.driver)

    def teardown_method(self):
        if hasattr(self, "hybrid"):
            self.hybrid.close()
        if hasattr(self, "driver") and self.driver:
            self.driver.quit()

    def _find(self, by, value):
        spec = LOCATOR_SURFACES.get(value, {})
        return self.hybrid.find(
            by,
            value,
            surface=spec.get("surface", "auto"),
            webview=spec.get("webview"),
        )
