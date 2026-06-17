"""
tc_001_main_screen.py — Ios Settings 메인 화면 표시 TC.

Tests:
    test_settings_main_screen
"""

import json
import subprocess
from pathlib import Path

from appium import webdriver
from appium.options.ios.xcuitest.base import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# --------------------------------------------------------------------------
# Selectors — placeholder values from config/screens.json.
# Replace with real resource-id / XPath once the app is attached.
# --------------------------------------------------------------------------
SEL_HOMEPAGE_TITLE = "설정"

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


def _build_driver() -> webdriver.Remote:
    devices = _load_json(CONFIG_DIR / "devices.json")
    test_data = _load_json(CONFIG_DIR / "test_data.json")

    caps = devices["ios"][PLATFORM_MODE].copy()
    caps["platformName"] = "iOS"
    caps["bundleId"] = test_data["app"]["ios"]["bundle_id"]
    app_path = test_data["app"]["ios"]["app_path"]
    if app_path:
        caps["app"] = app_path

    options = XCUITestOptions().load_capabilities(caps)
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
        """설정 타이틀 요소가 화면에 표시된다"""
        driver = self.driver

        # 설정 타이틀 요소가 존재하는지 확인한다
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((AppiumBy.ACCESSIBILITY_ID, SEL_HOMEPAGE_TITLE))
        )

        # 기대결과 검증
        assert_el = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((AppiumBy.ACCESSIBILITY_ID, SEL_HOMEPAGE_TITLE))
        )
        assert assert_el.is_displayed(), (
            "설정 타이틀 요소가 화면에 표시된다"
        )
