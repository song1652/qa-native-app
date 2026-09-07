"""
tc_002_search_bar.py — Android Settings 검색창 탭 TC.

Tests:
    test_search_bar_tap
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from appium import webdriver
from appium.options.android.uiautomator2.base import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# --------------------------------------------------------------------------
# Selectors — generated from config/locators.json.
# Healing updates the registry, then regeneration updates this file.
# --------------------------------------------------------------------------
SEL_SEARCH_ACTION_BAR_TITLE = "com.android.settings:id/search_action_bar_title"  # target_ref: search_bar.search_action_bar_title / AppiumBy.ID
SEL_OPEN_SEARCH_VIEW = "com.google.android.settings.intelligence:id/open_search_view"  # target_ref: search_bar.open_search_view / AppiumBy.ID

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


class TestSearchBar:
    """Settings 검색창 탭 화면 TC."""

    def setup_method(self):
        _check_device_connected()
        self.driver = _build_driver()

    def teardown_method(self):
        if hasattr(self, "driver") and self.driver:
            self.driver.quit()

    # ----------------------------------------------------------------------
    # TC-002-01
    # ----------------------------------------------------------------------
    def test_search_bar_tap(self):
        """open_search_view 요소가 표시된다"""
        driver = self.driver

        # search_action_bar_title 버튼을 탭한다
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((AppiumBy.ID, SEL_SEARCH_ACTION_BAR_TITLE))
        ).click()

        # open_search_view 요소가 존재하는지 확인한다
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((AppiumBy.ID, SEL_OPEN_SEARCH_VIEW))
        )

        # 기대결과 검증
        assert_el = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((AppiumBy.ID, SEL_OPEN_SEARCH_VIEW))
        )
        assert assert_el.is_displayed(), (
            "open_search_view 요소가 표시된다"
        )
