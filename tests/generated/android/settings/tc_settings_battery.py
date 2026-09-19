"""
tc_settings_battery.py — Android | Settings Battery 화면 진입
자동 생성: Capture Studio (2026-09-16 11:26)
"""
import json, subprocess, shutil, os
import time as _time
from pathlib import Path
from appium import webdriver
from appium.options.android.uiautomator2.base import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait

CAPTURE_TEMPLATE_VERSION = 2
CONFIG_DIR = (Path(__file__).resolve().parent / "../../../.." / "config").resolve()
APPIUM_URL  = "http://localhost:4723"
PLATFORM_MODE = "emulator"

def _load_json(p): return json.loads(Path(p).read_text(encoding='utf-8'))

APP_ID = 'com.android.settings'
APP_ACTIVITY = '.Settings'

_NON_APPIUM_KEYS = frozenset({'default', 'wifi_ip', 'team_id', 'label', 'note'})

def _get_device(platform, mode):
    _s = _load_json(CONFIG_DIR / 'devices.json').get(platform, {}).get(mode)
    if isinstance(_s, dict): return _s
    if isinstance(_s, list):
        return next((d for d in _s if d.get('default')), _s[0] if _s else {})
    return {}

def _build_driver():
    _raw = _get_device('android', PLATFORM_MODE)
    caps = {k: v for k, v in _raw.items() if k not in _NON_APPIUM_KEYS}
    caps['platformName'] = 'Android'
    caps.pop('app', None)  # 설치된 앱 사용
    caps['appPackage'] = APP_ID
    caps['appActivity'] = APP_ACTIVITY
    opts = UiAutomator2Options().load_capabilities(caps)
    return webdriver.Remote(APPIUM_URL, options=opts)

def _reset_to_start(driver):
    """Every pytest attempt starts in the target app's native root state."""
    try:
        if driver.current_context != 'NATIVE_APP':
            driver.switch_to.context('NATIVE_APP')
    except Exception:
        pass
    try:
        _foreground = driver.current_package
        if _foreground and _foreground != APP_ID:
            driver.terminate_app(_foreground)
    except Exception:
        pass
    try:
        driver.terminate_app(APP_ID)
    except Exception:
        pass
    _time.sleep(0.3)
    driver.activate_app(APP_ID)
    if APP_ACTIVITY:
        try:
            driver.execute_script('mobile: startActivity', {
                'intent': f'{APP_ID}/{APP_ACTIVITY}', 'wait': True, 'stop': True
            })
        except Exception:
            driver.activate_app(APP_ID)
    _time.sleep(1.0)


class TestTcSettingsBattery:
    """Capture Studio — Settings Battery 화면 진입"""

    def setup_method(self):
        self.driver = _build_driver()
        _reset_to_start(self.driver)

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
        by = by_map.get(strategy, AppiumBy.XPATH)
        return WebDriverWait(self.driver, 15).until(lambda d: d.find_element(by, value))

    def test_tc_settings_battery(self):
        """단계별 동작 및 검증"""
        # Step 1: el_1
        self.driver.execute_script('mobile: clickGesture', {'x': 273, 'y': 1791})
        _time.sleep(1.5)  # 화면 전환 대기

        # 기대결과: Battery Saver
        _found = False
        for _retry in range(5):
            _src = self.driver.page_source
            if 'Battery Saver' in _src:
                _found = True; break
            _time.sleep(1.0)
        if not _found:
            from selenium.common.exceptions import NoSuchElementException
            try:
                _fb = self.driver.find_element(AppiumBy.XPATH, "//*[@text='Battery Saver']")
                _found = _fb is not None
            except NoSuchElementException:
                pass
        assert _found, f"기대결과 미충족: 'Battery Saver' 가 화면에 없음"
