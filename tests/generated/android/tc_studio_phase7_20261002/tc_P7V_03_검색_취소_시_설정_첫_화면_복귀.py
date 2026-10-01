"""
tc_P7V_03_검색_취소_시_설정_첫_화면_복귀.py — Android TC-P7V_03: 검색 취소 시 설정 첫 화면 복귀 TC.

Tests:
    test_검색_취소_시_설정_첫_화면_복귀
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
# target_ref: 03_검색_취소_시_설정_첫_화면_복귀.settings_search_bar
# AppiumBy.ID
SEL_SETTINGS_SEARCH_BAR = 'com.android.settings:id/search_action_bar'
# target_ref: 03_검색_취소_시_설정_첫_화면_복귀.settings_back_button
# AppiumBy.ACCESSIBILITY_ID
SEL_SETTINGS_BACK_BUTTON = '뒤로'
# target_ref: 03_검색_취소_시_설정_첫_화면_복귀.settings_homepage_title
# AppiumBy.ID
SEL_SETTINGS_HOMEPAGE_TITLE = 'com.android.settings:id/homepage_title'
LOCATOR_SURFACES = {
    'com.android.settings:id/search_action_bar': {
        'surface': 'auto',
        'webview': None,
    },
    '뒤로': {
        'surface': 'auto',
        'webview': None,
    },
    'com.android.settings:id/homepage_title': {
        'surface': 'auto',
        'webview': None,
    },
}

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


class Test03검색취소시설정첫화면복귀:
    """TC-P7V_03: 검색 취소 시 설정 첫 화면 복귀 화면 TC."""

    def setup_method(self):
        _check_device_connected()
        self.driver = _build_driver()
        self.driver.terminate_app(
            "com.google.android.settings.intelligence"
        )
        self.driver.execute_script(
            "mobile: startActivity",
            {"intent": 'com.android.settings/.homepage.SettingsHomepageActivity'},
        )
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
    # TC-P7V-01
    # ----------------------------------------------------------------------
    def test_검색_취소_시_설정_첫_화면_복귀(self):
        """홈 화면 제목(settings_homepage_title)이 표시된다."""
        # 설정 첫 화면에서 검색창(settings_search_bar)을 탭한다
        self._find(AppiumBy.ID, SEL_SETTINGS_SEARCH_BAR).click()

        # 검색 화면에서 뒤로 버튼(settings_back_button)을 누른다
        self._find(AppiumBy.ACCESSIBILITY_ID, SEL_SETTINGS_BACK_BUTTON).click()

        # 기대결과 검증
        assert_el = self._find(AppiumBy.ID, SEL_SETTINGS_HOMEPAGE_TITLE)
        assert assert_el.is_displayed(), (
            "홈 화면 제목(settings_homepage_title)이 표시된다."
        )
