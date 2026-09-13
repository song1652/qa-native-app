"""
tc_ios_settings_ui_v3.py — Ios | iOS Settings UI 검증 v3
자동 생성: Capture Studio (2026-09-12 19:35)
"""
import json, subprocess, shutil, os
import time as _time
from pathlib import Path
from appium import webdriver
from appium.options.ios.xcuitest.base import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy

CONFIG_DIR = (Path(__file__).resolve().parent / "../../../.." / "config").resolve()
APPIUM_URL  = "http://localhost:4723"
PLATFORM_MODE = "simulator"

def _load_json(p): return json.loads(Path(p).read_text(encoding='utf-8'))

def _build_driver():
    devs = _load_json(CONFIG_DIR / 'devices.json')
    caps = devs['ios'][PLATFORM_MODE].copy()
    caps['platformName'] = 'iOS'
    caps.pop('app', None)  # 설치된 앱 사용
    caps['bundleId'] = 'com.apple.Preferences'
    opts = XCUITestOptions().load_capabilities(caps)
    return webdriver.Remote(APPIUM_URL, options=opts)


class TestTcIosSettingsUiV3:
    """Capture Studio — iOS Settings UI 검증 v3"""

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

    def _ios_find_and_tap(self, label):
        """iOS: 요소가 화면 밖에 있으면 mobile:scroll로 자동 스크롤 후 탭."""
        from selenium.common.exceptions import NoSuchElementException
        try:
            el = self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, label)
            el.click()
        except NoSuchElementException:
            # 화면 밖 → mobile:scroll로 요소까지 스크롤
            self.driver.execute_script('mobile: scroll',
                {'direction': 'down', 'predicateString': f'label == "{label}"'})
            _time.sleep(0.5)
            self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, label).click()

    def test_tc_ios_settings_ui_v3(self):
        """단계별 동작 및 검증"""
        # Step 1: '스크린 타임' 탭 (화면 밖이면 mobile:scroll 자동 스크롤)
        self._ios_find_and_tap('스크린 타임')
        _time.sleep(1.5)  # 화면 전환 대기
        # Step 2: '스크린 타임' 화면 진입 확인
        _found_text = False
        for _retry_i in range(5):
            _src = self.driver.page_source
            if '스크린 타임' in _src:
                _found_text = True; break
            _time.sleep(1.0)
        assert _found_text, "페이지 소스에서 '스크린 타임' 없음"
        # Step 3: 이전 화면 복귀
        self.driver.back()
        _time.sleep(1.0)  # 화면 복귀 대기
