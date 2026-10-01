"""
tc_LOC_01_설정_홈에서_위치_화면_진입_시_제목과_항목_표시.py — Android TC-LOC_01: 설정 홈에서 위치 화면 진입 시 제목과 항목 표시 TC.

Tests:
    test_설정_홈에서_위치_화면_진입_시_제목과_항목_표시
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from appium import webdriver
from appium.options.android.uiautomator2.base import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from scripts.hybrid_runtime import HybridSession


# --------------------------------------------------------------------------
# Selectors — generated from config/locators.json.
# Healing updates the registry, then regeneration updates this file.
# --------------------------------------------------------------------------
LOCATOR_SURFACES = {}

CONFIG_DIR = Path(__file__).parent.parent.parent.parent.parent / "config"
APPIUM_URL = "http://localhost:4723"
PLATFORM_MODE = "emulator"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_adb() -> str:
    candidates = [
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
        "/usr/local/bin/adb",
        shutil.which("adb") or "",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return "adb"


_ADB = _find_adb()


def _check_device_connected() -> None:
    result = subprocess.run([_ADB, "devices"], capture_output=True, text=True)
    lines = result.stdout.strip().splitlines()
    connected = [
        line for line in lines[1:]
        if line.strip() and "offline" not in line
    ]
    if not connected:
        raise RuntimeError(
            "[android_driver] No device/emulator connected. "
            "Run: adb devices"
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
    _raw = _get_device("android", PLATFORM_MODE)

    caps = {k: v for k, v in _raw.items() if k not in _NON_APPIUM_KEYS}
    caps["platformName"] = "Android"
    _uid = os.environ.get("DEVICE_UDID", "")
    if _uid:
        caps["udid"] = _uid
    caps["appPackage"] = "com.android.settings"
    caps["appActivity"] = ".homepage.SettingsHomepageActivity"
    caps["forceAppLaunch"] = True

    options = UiAutomator2Options().load_capabilities(caps)
    return webdriver.Remote(APPIUM_URL, options=options)


class Test01설정홈에서위치화면진입시제목과항목표시:
    """TC-LOC_01: 설정 홈에서 위치 화면 진입 시 제목과 항목 표시 화면 TC."""

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
    # TC-LOC-01
    # ----------------------------------------------------------------------
    def test_설정_홈에서_위치_화면_진입_시_제목과_항목_표시(self):
        """위치 화면 상단에 '위치' 제목이 표시되고 '위치 사용'과 '위치 서비스' 항목이 보인다. 위치 위"""
        # 설정 홈에서 '위치' 항목을 누른다
        target = (
            'new UiScrollable(new UiSelector().scrollable(true))'
            '.scrollIntoView(new UiSelector().text(\"위치\"))'
        )
        self.driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, target).click()

        # 기대결과 검증
        assert_el = self.driver.find_element(
            AppiumBy.XPATH, '//*[@text="위치" or @content-desc="위치"]'
        )
        assert assert_el.is_displayed(), '위치'
        assert_el = self.driver.find_element(
            AppiumBy.XPATH, '//*[@text="위치 사용" or @content-desc="위치 사용"]'
        )
        assert assert_el.is_displayed(), '위치 사용'
        assert_el = self.driver.find_element(
            AppiumBy.XPATH, '//*[@text="위치 서비스" or @content-desc="위치 서비스"]'
        )
        assert assert_el.is_displayed(), '위치 서비스'
