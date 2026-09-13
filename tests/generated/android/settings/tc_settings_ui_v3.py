"""
tc_android_settings_ui_v3.py — Android | Android Settings UI 검증 v3
자동 생성: Capture Studio (2026-09-12 17:48)
"""
import json, subprocess, shutil, os
import time as _time
from pathlib import Path
from appium import webdriver
from appium.options.android.uiautomator2.base import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy

CONFIG_DIR = (Path(__file__).resolve().parent / "../../../.." / "config").resolve()
APPIUM_URL  = "http://localhost:4723"
PLATFORM_MODE = "emulator"

def _load_json(p): return json.loads(Path(p).read_text(encoding='utf-8'))

def _build_driver():
    devs = _load_json(CONFIG_DIR / 'devices.json')
    caps = devs['android'][PLATFORM_MODE].copy()
    caps['platformName'] = 'Android'
    caps.pop('app', None)  # 설치된 앱 사용
    caps['appPackage'] = 'com.android.settings'
    caps['appActivity'] = '.Settings'
    opts = UiAutomator2Options().load_capabilities(caps)
    return webdriver.Remote(APPIUM_URL, options=opts)


class TestTcAndroidSettingsUiV3:
    """Capture Studio — Android Settings UI 검증 v3"""

    def setup_method(self):
        self.driver = _build_driver()

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
        return self.driver.find_element(by_map.get(strategy, AppiumBy.XPATH), value)

    def test_tc_android_settings_ui_v3(self):
        """단계별 동작 및 검증"""
        # Step 1: 아래로 스크롤
        _sz = self.driver.get_window_size()
        self.driver.swipe(_sz['width']//2, int(_sz['height']*0.7),
                          _sz['width']//2, int(_sz['height']*0.3), 400)
        _time.sleep(0.8)  # 스크롤 완료 대기
        # Step 2: title
        self._el('AppiumBy.XPATH', "//*[@text='Display & touch']").click()
        _time.sleep(1.5)  # 화면 전환 대기
