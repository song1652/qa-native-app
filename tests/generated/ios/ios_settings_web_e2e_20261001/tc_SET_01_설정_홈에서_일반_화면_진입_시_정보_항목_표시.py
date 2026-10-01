"""
tc_SET_01_설정_홈에서_일반_화면_진입_시_정보_항목_표시.py — Ios TC-SET_01: 설정 홈에서 일반 화면 진입 시 정보 항목 표시 TC.

Tests:
    test_설정_홈에서_일반_화면_진입_시_정보_항목_표시
"""

import json
import os
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
    _mode = os.environ.get("DEVICE_MODE", mode)
    _uid = os.environ.get("DEVICE_UDID", "")
    _s = _load_json(CONFIG_DIR / "devices.json").get(platform, {}).get(_mode)
    if isinstance(_s, dict):
        return _s
    if isinstance(_s, list):
        if _uid:
            _match = next((d for d in _s if d.get("udid") == _uid), None)
            if _match:
                return _match
        return next((d for d in _s if d.get("default")), _s[0] if _s else {})
    return {}


_NON_APPIUM_KEYS = frozenset({"default", "wifi_ip", "team_id", "label", "note"})


def _build_driver() -> webdriver.Remote:
    _raw = _get_device("ios", PLATFORM_MODE)

    caps = {k: v for k, v in _raw.items() if k not in _NON_APPIUM_KEYS}
    caps["platformName"] = "iOS"
    caps["bundleId"] = "com.apple.Preferences"

    options = XCUITestOptions().load_capabilities(caps)
    return webdriver.Remote(APPIUM_URL, options=options)


class Test01설정홈에서일반화면진입시정보항목표시:
    """TC-SET_01: 설정 홈에서 일반 화면 진입 시 정보 항목 표시 화면 TC."""

    def setup_method(self):
        _check_device_connected()
        self.driver = _build_driver()
        self.driver.implicitly_wait(10)
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

    # ----------------------------------------------------------------------
    # TC-SET-01
    # ----------------------------------------------------------------------
    def test_설정_홈에서_일반_화면_진입_시_정보_항목_표시(self):
        """일반 화면 상단에 '일반' 제목이 표시되고 '정보' 항목이 보인다. 일반 정보"""
        # 설정 홈에서 '일반' 항목을 누른다
        self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, '일반').click()

        # 기대결과 검증
        assert_el = self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, '일반')
        assert assert_el.is_displayed(), '일반'
        assert_el = self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, '정보')
        assert assert_el.is_displayed(), '정보'
