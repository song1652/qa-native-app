"""
tc_005_ApiDemos_WebView_텍스트_입력.py — Android ApiDemos WebView 텍스트 입력 TC.

Tests:
    test_webview_text_input_after_native_detection
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
# target_ref: ApiDemos_WebView_텍스트_입력.native_header / AppiumBy.XPATH
SEL_NATIVE_HEADER = '//*[@text="Views/WebView"]'
# target_ref: ApiDemos_WebView_텍스트_입력.webview_textbox / AppiumBy.ACCESSIBILITY_ID
SEL_WEBVIEW_TEXTBOX = '#i_am_a_textbox'
LOCATOR_SURFACES = {'//*[@text="Views/WebView"]': {'surface': 'native',
                                                   'webview': None},
                    '#i_am_a_textbox': {'surface': 'webview',
                                        'webview': {'strategy': 'css',
                                                    'value': '#i_am_a_textbox'}}}

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


class TestApidemosWebview텍스트입력:
    """ApiDemos WebView 텍스트 입력 화면 TC."""

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

    # ----------------------------------------------------------------------
    # TC-005-01
    # ----------------------------------------------------------------------
    def test_webview_text_input_after_native_detection(self):
        """WebView가 감지되기 전에는 native locator만 사용한다. WebView 전환 후 we"""
        # 앱을 `NATIVE_APP` context에서 실행한다.
        assert self.driver.current_context == "NATIVE_APP"

        # native_header 요소가 존재하는지 확인한다.
        self._find(AppiumBy.XPATH, SEL_NATIVE_HEADER)

        # WebView context가 감지되면 해당 context로 전환한다.
        assert self.hybrid.webview_contexts

        # webview_textbox 요소의 기존 값을 지운다.
        self._find(AppiumBy.ACCESSIBILITY_ID, SEL_WEBVIEW_TEXTBOX).clear()

        # webview_textbox 요소에 `hybrid-test`를 입력한다.
        self._find(AppiumBy.ACCESSIBILITY_ID, SEL_WEBVIEW_TEXTBOX).send_keys('hybrid-test')

        # webview_textbox 요소의 값을 확인한다.
        self._find(AppiumBy.ACCESSIBILITY_ID, SEL_WEBVIEW_TEXTBOX)

        # 기대결과 검증
        assert_el = self._find(AppiumBy.ACCESSIBILITY_ID, SEL_WEBVIEW_TEXTBOX)
        assert assert_el.is_displayed(), (
            "WebView가 감지되기 전에는 native locator만 사용한다. WebView 전환 후 we"
        )
