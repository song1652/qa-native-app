"""
tc_001_main_screen.py — Android Settings 메인 화면 표시 TC.

Tests:
    test_settings_main_screen
"""

import json
import subprocess
from pathlib import Path

from appium import webdriver
from appium.options.android.uiautomator2.base import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# --------------------------------------------------------------------------
# Selectors — placeholder values from config/screens.json.
# Replace with real resource-id / XPath once the app is attached.
# --------------------------------------------------------------------------
SEL_HOMEPAGE_TITLE = "com.android.settings:id/homepage_title"
SEL_SEARCH_ACTION_BAR_TITLE = "com.android.settings:id/search_action_bar_title"

CONFIG_DIR = Path(__file__).parent.parent.parent.parent.parent / "config"
APPIUM_URL = "http://localhost:4723"
PLATFORM_MODE = "emulator"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


_ADB = "/Users/songkyoungjin/Library/Android/sdk/platform-tools/adb"


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


def _build_driver() -> webdriver.Remote:
    devices = _load_json(CONFIG_DIR / "devices.json")
    test_data = _load_json(CONFIG_DIR / "test_data.json")

    caps = devices["android"][PLATFORM_MODE].copy()
    caps["platformName"] = "Android"
    caps["appPackage"] = test_data["app"]["android"]["package"]
    caps["appActivity"] = test_data["app"]["android"]["activity"]
    app_path = test_data["app"]["android"]["app_path"]
    if app_path:
        caps["app"] = app_path

    options = UiAutomator2Options().load_capabilities(caps)
    return webdriver.Remote(APPIUM_URL, options=options)


class TestMainScreen:
    """Settings 메인 화면 표시 화면 TC."""

    def setup_method(self):
        _check_device_connected()
        self.driver = _build_driver()

    def teardown_method(self):
        if hasattr(self, "driver") and self.driver:
            self.driver.quit()

    # ----------------------------------------------------------------------
    # TC-001-01
    # ----------------------------------------------------------------------
    def test_settings_main_screen(self):
        """homepage_title 요소에 'Settings' 텍스트가 표시된다"""
        driver = self.driver

        # homepage_title 요소가 존재하는지 확인한다
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((AppiumBy.ID, SEL_HOMEPAGE_TITLE))
        )

        # 기대결과 검증
        assert_el = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((AppiumBy.ID, SEL_HOMEPAGE_TITLE))
        )
        assert assert_el.is_displayed(), (
            "homepage_title 요소에 'Settings' 텍스트가 표시된다"
        )
