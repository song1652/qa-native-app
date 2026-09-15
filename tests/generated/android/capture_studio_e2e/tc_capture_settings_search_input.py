"""
tc_capture_settings_search_input.py — Android | 설정 검색창 텍스트 입력과 검증
자동 생성: Capture Studio (2026-09-15 16:23)
"""
import json, subprocess, shutil, os
import time as _time
from pathlib import Path
from appium import webdriver
from appium.options.android.uiautomator2.base import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from scripts.generated_runtime import (
    CAPTURE_TEMPLATE_VERSION, appium_capabilities, find_with_wait,
    reset_to_start, select_device,
)

CONFIG_DIR = (Path(__file__).resolve().parent / "../../../.." / "config").resolve()
APPIUM_URL  = "http://localhost:4723"
PLATFORM_MODE = "emulator"
APP_ID = "com.android.settings"
APP_ACTIVITY = ".Settings"

def _load_json(p): return json.loads(Path(p).read_text(encoding='utf-8'))

_NON_APPIUM_KEYS = frozenset({'default', 'wifi_ip', 'team_id', 'label', 'note'})

def _get_device(platform, mode):
    return select_device(CONFIG_DIR / 'devices.json', platform, mode)

def _build_driver():
    _raw = _get_device('android', PLATFORM_MODE)
    caps = appium_capabilities(_raw)
    caps['platformName'] = 'Android'
    caps.pop('app', None)  # 설치된 앱 사용
    caps['appPackage'] = APP_ID
    caps['appActivity'] = APP_ACTIVITY
    opts = UiAutomator2Options().load_capabilities(caps)
    return webdriver.Remote(APPIUM_URL, options=opts)


class TestTcCaptureSettingsSearchInput:
    """Capture Studio — 설정 검색창 텍스트 입력과 검증"""

    def setup_method(self):
        self.driver = _build_driver()
        reset_to_start(self.driver, 'android', APP_ID, APP_ACTIVITY)

    def teardown_method(self):
        if hasattr(self, 'driver') and self.driver:
            self.driver.quit()

    def _el(self, strategy, value):
        by_map = {
            'id': AppiumBy.ID, 'xpath': AppiumBy.XPATH,
            'accessibility id': AppiumBy.ACCESSIBILITY_ID,
            'class name': AppiumBy.CLASS_NAME,
            'AppiumBy.ID': AppiumBy.ID, 'AppiumBy.XPATH': AppiumBy.XPATH,
            'AppiumBy.ACCESSIBILITY_ID': AppiumBy.ACCESSIBILITY_ID,
            'AppiumBy.CLASS_NAME': AppiumBy.CLASS_NAME,
        }
        return find_with_wait(self.driver, by_map.get(strategy, AppiumBy.XPATH), value)

    def test_tc_capture_settings_search_input(self):
        """단계별 동작 및 검증"""
        # Step 1: search_action_bar
        self._el('AppiumBy.ID', 'com.android.settings:id/search_action_bar').click()
        _time.sleep(1.5)  # 화면 전환 대기
        # Step 2: 2초 대기
        import time; time.sleep(2.0)
        # Step 3: open_search_view_edit_text
        el = self._el('AppiumBy.ID', 'com.google.android.settings.intelligence:id/open_search_view_edit_text')
        el.clear()
        el.send_keys('Bluetooth')
        # Step 4: 2초 대기
        import time; time.sleep(2.0)
        # Step 5: open_search_view_edit_text
        el = self._el('AppiumBy.ID', 'com.google.android.settings.intelligence:id/open_search_view_edit_text')
        assert 'Bluetooth' in el.text, f"텍스트 {el.text!r}에 'Bluetooth' 없음"
