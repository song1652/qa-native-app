"""Capture Studio actions-to-pytest generation."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


class CaptureCodegenValidationError(ValueError):
    """Raised when a Capture Studio generation request is invalid."""


def generate_test_from_actions(
    body: dict,
    session: dict,
    project_root: Path,
    *,
    generated_at: datetime | None = None,
) -> dict:
    """Render and persist one pytest module from Capture Studio actions."""
    project_root = Path(project_root)
    generated_at = generated_at or datetime.now()
    tc_id    = str(body.get("tc_id", "tc_001")).strip()
    title    = str(body.get("title", "자동 생성 TC")).strip()
    expected = str(body.get("expected", "")).strip()
    platform = body.get("platform", session.get("platform", "android"))
    tc_group = str(body.get("tc_group", session.get("tc_group", "default"))).strip()
    actions      = body.get("actions", [])
    source_filter = body.get("source_filter", "all")  # all | user | mcp
    _NON_EXEC = frozenset({"screenshot", "hierarchy", "generate_test_case", "clear_actions", "screen_info"})
    executable_actions = [
        a for a in actions
        if (a.get("type") or a.get("action", "")) not in _NON_EXEC
        and (source_filter == "all" or a.get("source", "user") == source_filter)
    ]
    _origins = {a.get("source", "user") for a in executable_actions}
    _origin_label = next(iter(_origins)) if len(_origins) == 1 else "mixed"
    app_pkg   = str(session.get("app_package", body.get("app_pkg", ""))).strip()
    app_act   = str(session.get("app_activity", body.get("app_activity", ""))).strip()
    bundle_id = str(session.get("bundle_id", body.get("bundle_id", ""))).strip()

    if not tc_id or platform not in ("android", "ios"):
        raise CaptureCodegenValidationError("tc_id와 platform이 필요합니다")
    if not executable_actions:
        raise CaptureCodegenValidationError("실행 가능한 액션이 하나 이상 필요합니다")

    slug       = tc_id.replace("-", "_")
    class_name = "".join(w.capitalize() for w in slug.split("_") if w)
    parents    = "../" * 4  # tests/generated/{platform}/{group}/tc.py → ROOT

    lines = [
        f'"""',
        f'{slug}.py — {platform.capitalize()} | {title}',
        f'자동 생성: Capture Studio ({generated_at.strftime("%Y-%m-%d %H:%M")})',
        f'출처: {_origin_label} ({len(executable_actions)} actions)',
        f'"""',
        f"import json, subprocess, shutil, os",
        f"import time as _time",
        f"from pathlib import Path",
        f"from appium import webdriver",
        (
            f"from appium.options.android.uiautomator2.base import UiAutomator2Options"
            if platform == "android"
            else f"from appium.options.ios.xcuitest.base import XCUITestOptions"
        ),
        f"from appium.webdriver.common.appiumby import AppiumBy",
        f"from selenium.webdriver.support.ui import WebDriverWait",
        f"",
        f"CAPTURE_TEMPLATE_VERSION = 2",
        f'CONFIG_DIR = (Path(__file__).resolve().parent / "{parents.rstrip("/")}" / "config").resolve()',
        f'APPIUM_URL  = "http://localhost:4723"',
        f'PLATFORM_MODE = "{"emulator" if platform == "android" else "simulator"}"',
        f"",
        f"def _load_json(p): return json.loads(Path(p).read_text(encoding='utf-8'))",
        f"",
        (
            f"APP_ID = {app_pkg!r}"
            if platform == "android" and app_pkg
            else f"APP_ID = _load_json(CONFIG_DIR / 'test_data.json')['app']['android']['package']"
            if platform == "android"
            else f"APP_ID = {bundle_id!r}"
            if bundle_id
            else f"APP_ID = _load_json(CONFIG_DIR / 'test_data.json')['app']['ios']['bundle_id']"
        ),
        (
            f"APP_ACTIVITY = {app_act!r}"
            if platform == "android" and app_act
            else f"APP_ACTIVITY = _load_json(CONFIG_DIR / 'test_data.json')['app']['android']['activity']"
            if platform == "android"
            else f"APP_ACTIVITY = ''"
        ),
        f"",
        f"_NON_APPIUM_KEYS = frozenset({{'default', 'wifi_ip', 'team_id', 'label', 'note'}})",
        f"",
        f"def _get_device(platform, mode):",
        f"    _s = _load_json(CONFIG_DIR / 'devices.json').get(platform, {{}}).get(mode)",
        f"    if isinstance(_s, dict): return _s",
        f"    if isinstance(_s, list):",
        f"        return next((d for d in _s if d.get('default')), _s[0] if _s else {{}})",
        f"    return {{}}",
        f"",
        f"def _build_driver():",
        f"    _raw = _get_device('{platform}', PLATFORM_MODE)",
        f"    caps = {{k: v for k, v in _raw.items() if k not in _NON_APPIUM_KEYS}}",
        f"    caps['platformName'] = '{'Android' if platform == 'android' else 'iOS'}'",
        f"    caps.pop('app', None)  # 설치된 앱 사용",
    ]
    if platform == "android":
        lines += [
            (
                f"    caps['appPackage'] = APP_ID"
                if app_pkg
                else f"    caps['appPackage'] = _load_json(CONFIG_DIR / 'test_data.json')['app']['android']['package']"
            ),
            (
                f"    caps['appActivity'] = APP_ACTIVITY"
                if app_act
                else f"    caps['appActivity'] = _load_json(CONFIG_DIR / 'test_data.json')['app']['android']['activity']"
            ),
            f"    opts = UiAutomator2Options().load_capabilities(caps)",
        ]
    else:
        lines += [
            (
                f"    caps['bundleId'] = APP_ID"
                if bundle_id
                else f"    caps['bundleId'] = _load_json(CONFIG_DIR / 'test_data.json')['app']['ios']['bundle_id']"
            ),
            f"    opts = XCUITestOptions().load_capabilities(caps)",
        ]
    lines += [
        f"    return webdriver.Remote(APPIUM_URL, options=opts)",
        f"",
        f"def _reset_to_start(driver):",
        f"    \"\"\"Every pytest attempt starts in the target app's native root state.\"\"\"",
        f"    try:",
        f"        if driver.current_context != 'NATIVE_APP':",
        f"            driver.switch_to.context('NATIVE_APP')",
        f"    except Exception:",
        f"        pass",
        *(
            [
                f"    try:",
                f"        _foreground = driver.current_package",
                f"        if _foreground and _foreground != APP_ID:",
                f"            driver.terminate_app(_foreground)",
                f"    except Exception:",
                f"        pass",
            ]
            if platform == "android"
            else []
        ),
        f"    try:",
        f"        driver.terminate_app(APP_ID)",
        f"    except Exception:",
        f"        pass",
        f"    _time.sleep(0.3)",
        f"    driver.activate_app(APP_ID)",
        *(
            [
                f"    if APP_ACTIVITY:",
                f"        try:",
                f"            driver.execute_script('mobile: startActivity', {{",
                f"                'intent': f'{{APP_ID}}/{{APP_ACTIVITY}}', 'wait': True, 'stop': True",
                f"            }})",
                f"        except Exception:",
                f"            driver.activate_app(APP_ID)",
            ]
            if platform == "android"
            else []
        ),
        f"    _time.sleep(1.0)",
        f"",
        f"",
        f"class Test{class_name}:",
        f'    """Capture Studio — {title}"""',
        f"",
        f"    def setup_method(self):",
        f"        self.driver = _build_driver()",
        f"        _reset_to_start(self.driver)",
        f"",
        f"    def teardown_method(self):",
        f"        if hasattr(self, 'driver') and self.driver:",
        f"            self.driver.quit()",
        f"",
        f"    def _el(self, strategy, value):",
        f"        by_map = {{",
        f"            'id': AppiumBy.ID, 'xpath': AppiumBy.XPATH,",
        f"            'accessibility id': AppiumBy.ACCESSIBILITY_ID,",
        f"            'class name': AppiumBy.CLASS_NAME,",
        f"            'AppiumBy.ID': AppiumBy.ID, 'AppiumBy.XPATH': AppiumBy.XPATH,",
        f"            'AppiumBy.ACCESSIBILITY_ID': AppiumBy.ACCESSIBILITY_ID,",
        f"            'AppiumBy.CLASS_NAME': AppiumBy.CLASS_NAME,",
        f"        }}",
        f"        by = by_map.get(strategy, AppiumBy.XPATH)",
        f"        return WebDriverWait(self.driver, 15).until(lambda d: d.find_element(by, value))",
        f"",
        *(
            [
                f"    def _ios_tap(self, label):",
                f"        \"\"\"iOS: 화면 밖 요소는 mobile:scroll로 자동 스크롤 후 탭.\"\"\"",
                f"        from selenium.common.exceptions import NoSuchElementException",
                f"        try:",
                f"            self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, label).click()",
                f"        except NoSuchElementException:",
                f"            self.driver.execute_script('mobile: scroll',",
                f"                {{'direction': 'down', 'predicateString': f'label == \"{{label}}\"'}})",
                f"            _time.sleep(0.5)",
                f"            self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, label).click()",
                f"",
            ]
            if platform == "ios"
            else []
        ),
        f"    def test_{slug}(self):",
        f'        """단계별 동작 및 검증"""',
    ]

    by_map_str = {
        "id":               "AppiumBy.ID",
        "xpath":            "AppiumBy.XPATH",
        "accessibility id": "AppiumBy.ACCESSIBILITY_ID",
        "accessibility-id": "AppiumBy.ACCESSIBILITY_ID",
        "class name":       "AppiumBy.CLASS_NAME",
        "class":            "AppiumBy.CLASS_NAME",
        "resource-id":      "AppiumBy.ID",
    }

    def _by(strategy: str) -> str:
        return by_map_str.get(strategy.lower().strip(), "AppiumBy.XPATH")

    for i, act in enumerate(executable_actions, 1):
        atype    = act.get("type") or act.get("action", "")
        label    = act.get("label", f"el_{i}")
        strategy = act.get("locator_strategy", act.get("strategy", "xpath"))
        value    = act.get("locator_value", act.get("value", ""))
        if strategy.lower().strip() == "text" and value and not value.startswith("/"):
            strategy = "xpath"
            value    = f"//*[@text='{value}']"
        lines.append(f"        # Step {i}: {label}")

        if atype in ("tap", "click"):
            device_x = act.get("device_x")
            device_y = act.get("device_y")
            if not value and device_x is not None and device_y is not None:
                gesture = "mobile: clickGesture" if platform == "android" else "mobile: tap"
                lines.append(
                    f"        self.driver.execute_script({gesture!r}, "
                    f"{{'x': {int(device_x)}, 'y': {int(device_y)}}})"
                )
            # iOS + accessibility-id → _ios_tap() (화면 밖 자동 스크롤 지원)
            elif platform == "ios" and strategy.lower().strip() in ("accessibility-id", "accessibility id"):
                lines.append(f"        self._ios_tap({value!r})")
            else:
                lines.append(f"        self._el({_by(strategy)!r}, {value!r}).click()")
            lines.append(f"        _time.sleep(1.5)  # 화면 전환 대기")

        elif atype == "input":
            input_val = act.get("input_value", act.get("assertion_value", ""))
            lines.append(f"        el = self._el({_by(strategy)!r}, {value!r})")
            lines.append(f"        el.clear()")
            lines.append(f"        el.send_keys({input_val!r})")

        elif atype == "assertion":
            a_type = act.get("assertion_type", "element_present")
            a_val  = act.get("assertion_value", "")
            if a_type == "text_visible":
                if value:
                    lines.append(f"        el = self._el({_by(strategy)!r}, {value!r})")
                    lines.append(f'        assert {a_val!r} in el.text, f"텍스트 {{el.text!r}}에 {a_val!r} 없음"')
                else:
                    # page_source는 raw XML → & 는 &amp; 로 인코딩됨
                    # 5초 재시도 루프 + XPath fallback으로 타이밍 문제·화면 전환 지연 처리
                    import html as _html_mod
                    escaped_val = _html_mod.escape(a_val, quote=False)
                    lines.append(f"        _found_text = False")
                    lines.append(f"        for _retry_i in range(5):")
                    lines.append(f"            _src = self.driver.page_source")
                    if escaped_val != a_val:
                        lines.append(f"            if {a_val!r} in _src or {escaped_val!r} in _src:")
                    else:
                        lines.append(f"            if {a_val!r} in _src:")
                    lines.append(f"                _found_text = True; break")
                    lines.append(f"            _time.sleep(1.0)")
                    # XPath fallback: XPath는 XML 인코딩을 올바르게 처리하므로 &amp; 문제 없음
                    lines.append(f"        if not _found_text:")
                    lines.append(f"            from selenium.common.exceptions import NoSuchElementException")
                    lines.append(f"            try:")
                    lines.append(f"                _fb_el = self.driver.find_element(")
                    lines.append(f"                    AppiumBy.XPATH, \"//*[@text={repr(a_val)}]\")")
                    lines.append(f"                _found_text = _fb_el is not None")
                    lines.append(f"            except NoSuchElementException:")
                    lines.append(f"                pass")
                    lines.append(f"        assert _found_text, f\"페이지 소스·XPath에서 {a_val!r} 없음\"")
            elif a_type == "element_present":
                lines.append(f"        assert self._el({_by(strategy)!r}, {value!r}).is_displayed()")
            elif a_type == "element_absent":
                lines.append(f"        from selenium.common.exceptions import NoSuchElementException")
                lines.append(f"        try:")
                lines.append(f"            self._el({_by(strategy)!r}, {value!r})")
                lines.append(f"            assert False, '요소가 존재해서 안 됩니다: {value}'")
                lines.append(f"        except NoSuchElementException:")
                lines.append(f"            pass")

        elif atype in ("back", "scroll_down", "scroll_up"):
            if atype == "back":
                lines.append(f"        self.driver.back()")
                lines.append(f"        _time.sleep(1.0)  # 화면 복귀 대기")
            elif atype == "scroll_down":
                # driver.swipe()는 Android·iOS 양쪽에서 동작
                # (mobile: scrollGesture는 elementId 없이 호출 시 InvalidArgumentException 발생)
                lines.append(f"        _sz = self.driver.get_window_size()")
                lines.append(f"        self.driver.swipe(_sz['width']//2, int(_sz['height']*0.7),")
                lines.append(f"                          _sz['width']//2, int(_sz['height']*0.3), 400)")
                lines.append(f"        _time.sleep(0.8)  # 스크롤 완료 대기")
            else:
                lines.append(f"        _sz = self.driver.get_window_size()")
                lines.append(f"        self.driver.swipe(_sz['width']//2, int(_sz['height']*0.3),")
                lines.append(f"                          _sz['width']//2, int(_sz['height']*0.7), 400)")
                lines.append(f"        _time.sleep(0.8)  # 스크롤 완료 대기")

        elif atype == "wait":
            secs = float(act.get("wait_seconds", 1))
            lines.append(f"        import time; time.sleep({secs})")

        else:
            lines.append(f"        pass  # TODO: {atype}")

    # 기대결과 assertion
    if expected:
        import html as _html_mod
        escaped_expected = _html_mod.escape(expected, quote=False)
        lines.append(f"")
        lines.append(f"        # 기대결과: {expected}")
        lines.append(f"        _found = False")
        lines.append(f"        for _retry in range(5):")
        lines.append(f"            _src = self.driver.page_source")
        if escaped_expected != expected:
            lines.append(f"            if {expected!r} in _src or {escaped_expected!r} in _src:")
        else:
            lines.append(f"            if {expected!r} in _src:")
        lines.append(f"                _found = True; break")
        lines.append(f"            _time.sleep(1.0)")
        lines.append(f"        if not _found:")
        lines.append(f"            from selenium.common.exceptions import NoSuchElementException")
        lines.append(f"            try:")
        lines.append(f"                _fb = self.driver.find_element(AppiumBy.XPATH, \"//*[@text={expected!r}]\")")
        lines.append(f"                _found = _fb is not None")
        lines.append(f"            except NoSuchElementException:")
        lines.append(f"                pass")
        lines.append(f"        assert _found, f\"기대결과 미충족: {expected!r} 가 화면에 없음\"")

    lines.append("")
    code = "\n".join(lines)

    out_dir  = project_root / "tests" / "generated" / platform / tc_group
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.py"
    out_path.write_text(code, encoding="utf-8")

    return {
        "ok": True,
        "file": str(out_path.relative_to(project_root)),
        "code": code,
        "lines": len(lines),
    }
