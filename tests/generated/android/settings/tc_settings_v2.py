"""
tc_android_settings_v2.py — Android | Android Settings v2 — Connected devices
자동 생성: Capture Studio (2026-09-12 15:55)
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


class TestTcAndroidSettingsV2:
    """Capture Studio — Android Settings v2 — Connected devices"""

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

    def test_tc_android_settings_v2(self):
        """단계별 동작 및 검증"""
        # Step 1: 'Connected devices' 탭
        self._el('AppiumBy.XPATH', "//*[@text='Connected devices']").click()
        _time.sleep(1.5)  # 화면 전환 대기
        # Step 2: 'Connected devices' 화면 진입 확인
        _found_text = False
        for _retry_i in range(5):
            _src = self.driver.page_source
            if 'Connected devices' in _src:
                _found_text = True; break
            _time.sleep(1.0)
        if not _found_text:
            from selenium.common.exceptions import NoSuchElementException
            try:
                _fb_el = self.driver.find_element(
                    AppiumBy.XPATH, "//*[@text='Connected devices']")
                _found_text = _fb_el is not None
            except NoSuchElementException:
                pass
        assert _found_text, f"페이지 소스·XPath에서 'Connected devices' 없음"
        # Step 3: 이전 화면 복귀
        self.driver.back()
        _time.sleep(1.0)  # 화면 복귀 대기
        # Step 4: 메인 복귀 확인 — 'Connected devices' 노출
        _found_text = False
        for _retry_i in range(5):
            _src = self.driver.page_source
            if 'Connected devices' in _src:
                _found_text = True; break
            _time.sleep(1.0)
        if not _found_text:
            from selenium.common.exceptions import NoSuchElementException
            try:
                _fb_el = self.driver.find_element(
                    AppiumBy.XPATH, "//*[@text='Connected devices']")
                _found_text = _fb_el is not None
            except NoSuchElementException:
                pass
        assert _found_text, f"페이지 소스·XPath에서 'Connected devices' 없음"
        # Step 5: 스크롤 다운
        _sz = self.driver.get_window_size()
        self.driver.swipe(_sz['width']//2, int(_sz['height']*0.7),
                          _sz['width']//2, int(_sz['height']*0.3), 400)
        _time.sleep(0.8)  # 스크롤 완료 대기
        # Step 6: 'Wallpaper & style' 탭
        self._el('AppiumBy.XPATH', "//*[@text='Wallpaper & style']").click()
        _time.sleep(1.5)  # 화면 전환 대기
        # Step 7: 'Wallpaper & style' 화면 진입 확인
        _found_text = False
        for _retry_i in range(5):
            _src = self.driver.page_source
            if 'Wallpaper & style' in _src or 'Wallpaper &amp; style' in _src:
                _found_text = True; break
            _time.sleep(1.0)
        if not _found_text:
            from selenium.common.exceptions import NoSuchElementException
            try:
                _fb_el = self.driver.find_element(
                    AppiumBy.XPATH, "//*[@text='Wallpaper & style']")
                _found_text = _fb_el is not None
            except NoSuchElementException:
                pass
        assert _found_text, f"페이지 소스·XPath에서 'Wallpaper & style' 없음"
