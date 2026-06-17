"""
02_generate.py — TC 마크다운 → pytest 코드 자동 생성.

testcases/tc_*.md 파일을 파싱하여 tests/generated/{platform}/tc_*.py를
자체 완결 형태(드라이버 초기화 포함, 공유 헬퍼 import 없음)로 생성한다.

Usage:
    python scripts/02_generate.py [--platform android|ios]
"""
import argparse
import json
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _find_adb() -> str:
    candidates = [
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
        "/usr/local/bin/adb",
        shutil.which("adb") or "",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return "adb"

ADB = _find_adb()
CONFIG_DIR = ROOT / "config"
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "pipeline.json"
TESTCASES_DIR = ROOT / "testcases"
TESTS_DIR = ROOT / "tests" / "generated"
LESSONS_FILE = ROOT / "agents" / "lessons_learned.md"

APPIUM_URL = "http://localhost:4723"
PLATFORM_MODE_ANDROID = "emulator"
PLATFORM_MODE_IOS = "simulator"


# ---------------------------------------------------------------------------
# Lessons Learned hints
# ---------------------------------------------------------------------------

def _load_lessons_learned_hints() -> dict:
    """lessons_learned.md에서 heal 성공 패턴을 읽어 {SEL_CONST: {value, strategy}} 반환.

    파싱 대상 형식:
        ### [Locator Heal] {screen} — {SEL_CONST}
        **해결**: `{value}` (`AppiumBy.{strategy}`)
    """
    if not LESSONS_FILE.exists():
        return {}
    hints = {}
    content = LESSONS_FILE.read_text(encoding="utf-8")
    header_pat = re.compile(r'### \[Locator Heal\] \S+ — (SEL_\w+)')
    value_pat = re.compile(
        r'\*\*해결\*\*: `([^`]+)` \(`AppiumBy\.(\w+)`\)'
    )
    headers = list(header_pat.finditer(content))
    values = list(value_pat.finditer(content))
    for hm, vm in zip(headers, values):
        sel_const = hm.group(1)
        hints[sel_const] = {"value": vm.group(1), "strategy": vm.group(2)}
    return hints


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {
        "step": "init",
        "dom_info": {},
        "generated_tests": [],
        "lint_results": {},
        "execute_results": {},
    }


def save_state(state: dict):
    STATE_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Markdown parser
# ---------------------------------------------------------------------------

def _extract_section(text: str, heading: str) -> str:
    """'## heading' 이후부터 다음 '##' 전까지의 텍스트를 반환한다."""
    pattern = rf"##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##|\Z)"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _extract_function_name(block: str) -> str:
    """### 테스트 함수명 블록에서 함수명을 추출한다.

    마크다운 인라인 코드 백틱(`) 안의 값 또는 일반 텍스트에서 추출한다.
    """
    match = re.search(r"`([^`]+)`", block)
    if match:
        return match.group(1).strip()
    # 백틱 없을 경우 첫 단어 반환
    line = block.strip().splitlines()[0] if block.strip() else ""
    return line.strip()


def _extract_selectors(block: str) -> dict:
    """### 셀렉터 힌트 블록에서 {설명키: 셀렉터값} 매핑을 추출한다.

    형식: - short_name: `selector_value`
    설명의 첫 번째 영문 snake_case 토큰을 키로 사용한다.
    """
    selectors = {}
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        match = re.search(r"`([^`]+)`", line)
        if not match:
            continue
        selector_val = match.group(1).strip()
        # 백틱 이전 부분에서 영문 short key 추출
        # "- digit_1: `...`" → "digit_1"
        # "- 숫자 1 버튼: `...`" → fallback to selector_val
        desc_raw = re.sub(r"\s*:?\s*`.*", "", line).lstrip("-").strip()
        eng_match = re.match(r"([a-zA-Z][a-zA-Z0-9_]*)", desc_raw)
        desc_key = eng_match.group(1) if eng_match else selector_val
        selectors[desc_key] = selector_val
    return selectors


def parse_tc_blocks(md_text: str) -> list:
    """마크다운에서 '## 테스트 케이스 N' 블록들을 파싱하여 목록으로 반환.

    반환 형식:
    [
        {
            "function_name": "test_login_success",
            "steps": ["step1", "step2"],
            "expected": "기대결과 텍스트",
            "selectors": {"key": "val"},
        },
        ...
    ]
    """
    # '## 테스트 케이스 N' 단위로 분리
    parts = re.split(r"(?=## 테스트 케이스)", md_text)

    result = []
    for part in parts:
        if not part.strip().startswith("## 테스트 케이스"):
            continue

        func_name = ""
        steps = []
        expected = ""
        selectors = {}

        # 각 ### 서브섹션을 분리
        subsections = re.split(r"(?=### )", part)
        for sub in subsections:
            sub_stripped = sub.strip()
            if sub_stripped.startswith("### 테스트 함수명"):
                body = re.sub(r"^###\s*테스트 함수명\s*", "", sub_stripped,
                              flags=re.MULTILINE).strip()
                func_name = _extract_function_name(body)

            elif sub_stripped.startswith("### 단계"):
                body = re.sub(r"^###\s*단계\s*", "", sub_stripped,
                              flags=re.MULTILINE).strip()
                for line in body.splitlines():
                    line = line.strip()
                    step_match = re.match(r"^\d+\.\s+(.+)", line)
                    if step_match:
                        steps.append(step_match.group(1).strip())

            elif sub_stripped.startswith("### 기대결과"):
                body = re.sub(r"^###\s*기대결과\s*", "", sub_stripped,
                              flags=re.MULTILINE).strip()
                lines = [
                    re.sub(r"^-\s*", "", ln).strip()
                    for ln in body.splitlines()
                    if ln.strip()
                ]
                expected = " ".join(lines)

            elif sub_stripped.startswith("### 셀렉터 힌트"):
                body = re.sub(r"^###\s*셀렉터 힌트\s*", "", sub_stripped,
                              flags=re.MULTILINE).strip()
                selectors = _extract_selectors(body)

        if func_name:
            result.append({
                "function_name": func_name,
                "steps": steps,
                "expected": expected,
                "selectors": selectors,
            })

    return result


def parse_md_file(md_path: Path) -> dict:
    """마크다운 파일 전체를 파싱하여 TC 메타데이터를 반환한다.

    반환 형식:
    {
        "tc_number": "001",
        "title": "로그인",
        "platform": ["android", "ios"],
        "precondition": "app_launch",
        "tc_blocks": [...],
    }
    """
    text = md_path.read_text(encoding="utf-8")

    # 파일명에서 tc 번호와 snake_case 이름 추출 (tc_001_login.md)
    stem = md_path.stem  # tc_001_login
    parts = stem.split("_", 2)
    tc_number = parts[1] if len(parts) > 1 else "000"
    tc_slug = parts[2] if len(parts) > 2 else stem

    # 제목: 첫 번째 # 헤딩
    title_match = re.search(
        r"^#\s+(?:TC-\d+[:：]?\s*)?(.+)$", text, re.MULTILINE
    )
    title = title_match.group(1).strip() if title_match else tc_slug

    # 플랫폼
    platform_section = _extract_section(text, "플랫폼")
    platforms = []
    for line in platform_section.splitlines():
        line = line.strip().lstrip("-").strip().lower()
        if "android" in line:
            platforms.append("android")
        if "ios" in line:
            platforms.append("ios")
    if not platforms:
        platforms = ["android", "ios"]

    # 전제조건
    precond_section = _extract_section(text, "전제조건")
    precond_match = re.search(r"precondition:\s*(\S+)", precond_section)
    precondition = precond_match.group(1).rstrip(")") if precond_match else ""

    tc_blocks = parse_tc_blocks(text)

    return {
        "tc_number": tc_number,
        "tc_slug": tc_slug,
        "title": title,
        "platform": platforms,
        "precondition": precondition,
        "tc_blocks": tc_blocks,
    }


# ---------------------------------------------------------------------------
# Code generator
# ---------------------------------------------------------------------------

def _to_class_name(tc_slug: str) -> str:
    """tc_slug(snake_case)를 CamelCase 클래스명으로 변환한다.

    예: login -> Login, file_list -> FileList
    """
    return "".join(word.capitalize() for word in tc_slug.split("_"))


def _sel_const_name(selector_key: str) -> str:
    """셀렉터 키를 유효한 Python 상수명으로 변환한다.

    resource-id(com.example:id/name) → SEL_NAME
    일반 snake_case → SEL_NAME
    """
    key = selector_key
    if ":id/" in key:
        key = key.split(":id/")[-1]
    elif "/" in key:
        key = key.split("/")[-1]
    key = re.sub(r"[^a-zA-Z0-9]", "_", key)
    key = re.sub(r"_+", "_", key).strip("_")
    return "SEL_" + key.upper()


def _collect_all_selectors(tc_blocks: list) -> dict:
    """모든 tc_block의 selectors를 합쳐 중복 없이 반환한다."""
    merged = {}
    for block in tc_blocks:
        for k, v in block["selectors"].items():
            if k not in merged:
                merged[k] = v
    return merged


def _build_android_imports() -> str:
    return """\
import json
import subprocess
from pathlib import Path

from appium import webdriver
from appium.options.android.uiautomator2.base import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC"""


def _build_ios_imports() -> str:
    return """\
import json
import subprocess
from pathlib import Path

from appium import webdriver
from appium.options.ios.xcuitest.base import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC"""


def _build_android_helpers(tc_number: str, tc_slug: str,
                           config_dir_expr: str = "") -> str:
    cfg = config_dir_expr or 'Path(__file__).parent.parent.parent.parent / "config"'
    return f"""\
CONFIG_DIR = {cfg}
APPIUM_URL = "{APPIUM_URL}"
PLATFORM_MODE = "{PLATFORM_MODE_ANDROID}"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


_ADB = "{ADB}"


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
    return webdriver.Remote(APPIUM_URL, options=options)"""


def _build_ios_helpers(tc_number: str, tc_slug: str,
                       config_dir_expr: str = "") -> str:
    cfg = config_dir_expr or 'Path(__file__).parent.parent.parent.parent / "config"'
    return f"""\
CONFIG_DIR = {cfg}
APPIUM_URL = "{APPIUM_URL}"
PLATFORM_MODE = "{PLATFORM_MODE_IOS}"


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
    return webdriver.Remote(APPIUM_URL, options=options)"""


def _build_setup_android(precondition: str, has_credentials: bool) -> str:
    guard = (
        "        _check_device_connected()\n"
    )
    creds = ""
    if has_credentials:
        creds = (
            "        test_data = _load_json(CONFIG_DIR / \"test_data.json\")\n"
            "        self._valid = test_data[\"credentials\"][\"valid\"]\n"
            "        self._invalid = test_data[\"credentials\"][\"invalid\"]\n"
        )
    return (
        "    def setup_method(self):\n"
        + guard
        + creds
        + "        self.driver = _build_driver()\n"
    )


def _build_setup_ios(precondition: str, has_credentials: bool) -> str:
    guard = (
        "        _check_device_connected()\n"
    )
    creds = ""
    if has_credentials:
        creds = (
            "        test_data = _load_json(CONFIG_DIR / \"test_data.json\")\n"
            "        self._valid = test_data[\"credentials\"][\"valid\"]\n"
            "        self._invalid = test_data[\"credentials\"][\"invalid\"]\n"
        )
    return (
        "    def setup_method(self):\n"
        + guard
        + creds
        + "        self.driver = _build_driver()\n"
    )


def _build_teardown() -> str:
    return (
        "    def teardown_method(self):\n"
        "        if hasattr(self, \"driver\") and self.driver:\n"
        "            self.driver.quit()\n"
    )


def _uses_credentials(tc_blocks: list) -> bool:
    """TC 블록 중 valid/invalid credentials를 사용하는지 판단한다."""
    for block in tc_blocks:
        fn = block.get("function_name", "")
        if "invalid" in fn or "valid" in fn:
            return True
        for step in block.get("steps", []):
            if "credentials" in step.lower():
                return True
    return False


def _build_test_method(block: dict, tc_number: str, idx: int,
                       platform: str) -> str:
    func_name = block["function_name"]
    steps = block["steps"]
    expected = block["expected"]
    selectors = block["selectors"]

    lines = []
    lines.append(f"    def {func_name}(self):")

    # docstring — 기대결과 요약
    if expected:
        # 짧게 요약 (첫 60자)
        summary = expected[:80].replace('"', "'")
        lines.append(f'        """{summary}"""')

    lines.append("        driver = self.driver")
    lines.append("")

    # 단계별 주석 + 코드 생성
    # 사용된 셀렉터를 추적해 AppiumBy 호출로 변환
    sel_const_map = {v: _sel_const_name(k) for k, v in selectors.items()}

    for step_text in steps:
        lines.append(f"        # {step_text}")

        # credentials 처리 — valid/invalid 판단
        if "credentials.valid.username" in step_text:
            sel = _get_step_selector(step_text, selectors,
                                     ["username"], "username_field")
            const = sel_const_map.get(sel, f'"{sel}"')
            lines.append(
                "        el = WebDriverWait(driver, 10).until("
            )
            lines.append(
                f"            EC.presence_of_element_located("
                f"(AppiumBy.ACCESSIBILITY_ID, {const}))"
            )
            lines.append("        )")
            lines.append("        el.clear()")
            lines.append("        el.send_keys(self._valid[\"username\"])")

        elif "credentials.invalid.username" in step_text:
            sel = _get_step_selector(step_text, selectors,
                                     ["username"], "username_field")
            const = sel_const_map.get(sel, f'"{sel}"')
            lines.append(
                "        el = WebDriverWait(driver, 10).until("
            )
            lines.append(
                f"            EC.presence_of_element_located("
                f"(AppiumBy.ACCESSIBILITY_ID, {const}))"
            )
            lines.append("        )")
            lines.append("        el.clear()")
            lines.append("        el.send_keys(self._invalid[\"username\"])")

        elif "credentials.valid.password" in step_text:
            sel = _get_step_selector(step_text, selectors,
                                     ["password"], "password_field")
            const = sel_const_map.get(sel, f'"{sel}"')
            lines.append(
                "        el = WebDriverWait(driver, 10).until("
            )
            lines.append(
                f"            EC.presence_of_element_located("
                f"(AppiumBy.ACCESSIBILITY_ID, {const}))"
            )
            lines.append("        )")
            lines.append("        el.clear()")
            lines.append("        el.send_keys(self._valid[\"password\"])")

        elif "credentials.invalid.password" in step_text:
            sel = _get_step_selector(step_text, selectors,
                                     ["password"], "password_field")
            const = sel_const_map.get(sel, f'"{sel}"')
            lines.append(
                "        el = WebDriverWait(driver, 10).until("
            )
            lines.append(
                f"            EC.presence_of_element_located("
                f"(AppiumBy.ACCESSIBILITY_ID, {const}))"
            )
            lines.append("        )")
            lines.append("        el.clear()")
            lines.append("        el.send_keys(self._invalid[\"password\"])")

        elif "탭한다" in step_text or "탭 한다" in step_text:
            # 탭 액션 — 셀렉터 힌트에서 셀렉터 찾기
            sel = _find_selector_for_step(step_text, selectors)
            if sel:
                const = sel_const_map.get(sel, f'"{sel}"')
                by = _appiumby_for(sel)
                lines.append(
                    "        WebDriverWait(driver, 10).until("
                )
                lines.append(
                    f"            EC.presence_of_element_located("
                    f"({by}, {const}))"
                )
                lines.append("        ).click()")
            else:
                lines.append(
                    "        # TODO: 셀렉터 힌트에서 탭 대상을 특정할 수 없음"
                )
                lines.append(
                    "        WebDriverWait(driver, 10).until("
                )
                lines.append(
                    "            EC.presence_of_element_located("
                    "(AppiumBy.ACCESSIBILITY_ID, \"{PLACEHOLDER}\"))"
                )
                lines.append("        ).click()")

        elif "확인한다" in step_text or "존재하는지" in step_text:
            sel = _find_selector_for_step(step_text, selectors)
            if sel:
                const = sel_const_map.get(sel, f'"{sel}"')
                by = _appiumby_for(sel)
                lines.append(
                    "        WebDriverWait(driver, 10).until("
                )
                lines.append(
                    f"            EC.presence_of_element_located(({by}, {const}))"
                )
                lines.append("        )")
            else:
                lines.append(
                    "        # TODO: 셀렉터 힌트에서 확인 대상을 특정할 수 없음"
                )
                lines.append(
                    "        WebDriverWait(driver, 10).until("
                )
                lines.append(
                    '            EC.presence_of_element_located('
                    '(AppiumBy.ACCESSIBILITY_ID, "{PLACEHOLDER}"))'
                )
                lines.append("        )")
        else:
            lines.append(
                "        # TODO: 단계를 자동 변환하지 못했습니다 — 직접 구현 필요"
            )

        lines.append("")

    # assert — 기대결과 기반
    lines.append("        # 기대결과 검증")
    asserted = _build_assert(expected, selectors, sel_const_map)
    lines.extend(asserted)

    return "\n".join(lines)


def _appiumby_for(selector_val: str) -> str:
    """셀렉터 값에 따라 적절한 AppiumBy 전략 문자열을 반환한다."""
    if selector_val.startswith("//") or selector_val.startswith("/"):
        return "AppiumBy.XPATH"
    if ":" in selector_val:
        return "AppiumBy.ID"
    return "AppiumBy.ACCESSIBILITY_ID"


def _get_step_selector(step_text: str, selectors: dict,
                       hint_keys: list, fallback: str) -> str:
    """단계 텍스트와 힌트 키워드를 기반으로 selectors에서 값을 찾는다."""
    for key in selectors:
        for hint in hint_keys:
            if hint in key:
                return selectors[key]
    return fallback


def _find_selector_for_step(step_text: str, selectors: dict) -> str:
    """단계 텍스트에서 셀렉터를 탐지한다.

    우선순위:
    1. 단계 텍스트 괄호 안에 셀렉터 값이 직접 명시된 경우: '탭(nav_files)'
    2. 셀렉터 값이 단계 텍스트 안에 문자열로 포함된 경우
    3. 셀렉터 키(영문 snake_case 토큰) 키워드 매칭
    """
    # 1. 괄호 안 셀렉터 직접 추출: (selector_name)
    paren_match = re.search(r"\(([a-z][a-z0-9_]*)\)", step_text)
    if paren_match:
        candidate = paren_match.group(1)
        if candidate in selectors:
            return selectors[candidate]

    # 2. 셀렉터 값이 단계 텍스트에 포함
    for val in selectors.values():
        if val in step_text:
            return val

    step_lower = step_text.lower()
    step_normalized = step_lower.replace("_", " ")

    # 3a. 셀렉터 키 전체가 단계 텍스트에 포함 (longest-match 우선)
    matched_by_full = [(key, val) for key, val in selectors.items()
                       if key.replace("_", " ") in step_normalized]
    if matched_by_full:
        matched_by_full.sort(key=lambda x: len(x[0]), reverse=True)
        return matched_by_full[0][1]

    # 3b. 모든 단어가 단계 텍스트에 포함되는 키 (all-words 매칭)
    for key, val in selectors.items():
        key_words = [w for w in key.replace("_", " ").split() if len(w) > 2]
        if key_words and all(w in step_normalized for w in key_words):
            return val

    # 4. 한글 키워드 → 셀렉터 suffix 패턴 추론
    #    예: "버튼을 탭" → _button, "탭 (nav" → nav_, "아이템" → _item
    korean_suffix_hints = [
        ("버튼", "_button"),
        ("필드", "_field"),
        ("탭", "nav_"),
        ("아이템", "_item"),
        ("화면", "_screen"),
    ]
    for korean_kw, suffix in korean_suffix_hints:
        if korean_kw in step_text:
            for key, val in selectors.items():
                if suffix in val:
                    return val
    return ""


def _build_assert(expected: str, selectors: dict,
                  sel_const_map: dict) -> list:
    """기대결과 텍스트로부터 assert 라인 목록을 생성한다."""
    lines = []
    # selectors 키(short name) 또는 값이 기대결과 텍스트에 포함된 것을 찾아 assert
    matched = []
    expected_lower = expected.lower()
    for key, val in selectors.items():
        if val in expected or key.lower() in expected_lower:
            if val not in matched:
                matched.append(val)

    if matched:
        for val in matched:
            const = sel_const_map.get(val, f'"{val}"')
            by = _appiumby_for(val)
            lines.append(
                "        assert_el = WebDriverWait(driver, 10).until("
            )
            lines.append(
                f"            EC.presence_of_element_located("
                f"({by}, {const}))"
            )
            lines.append("        )")
            lines.append(
                "        assert assert_el.is_displayed(), ("
            )
            short = expected[:100].replace('"', "'")
            lines.append(f'            "{short}"')
            lines.append("        )")
    else:
        # PLACEHOLDER — 셀렉터 힌트에서 검증 셀렉터를 특정할 수 없는 경우
        lines.append(
            "        # TODO: 기대결과 셀렉터를 특정할 수 없습니다"
            " — {PLACEHOLDER}를 실제 셀렉터로 교체하세요"
        )
        lines.append(
            "        assert_el = WebDriverWait(driver, 10).until("
        )
        lines.append(
            "            EC.presence_of_element_located("
            "(AppiumBy.ACCESSIBILITY_ID, \"{PLACEHOLDER}\")))"
        )
        lines.append("        assert assert_el.is_displayed(), (")
        short = expected[:100].replace('"', "'") if expected else "Expected element"
        lines.append(f'            "{short}"')
        lines.append("        )")

    return lines


def generate_test_file(meta: dict, platform: str,
                       hints: dict | None = None,
                       subfolder_depth: int = 0) -> str:
    """파싱된 메타데이터로 pytest 파일 내용(문자열)을 생성한다.

    hints: _load_lessons_learned_hints() 반환값. SEL_* 상수 값/전략을
           lessons_learned.md의 heal 성공 패턴으로 오버라이드한다.
    subfolder_depth: testcases/ 기준 서브폴더 깊이. 0=flat, 1=testcases/foo/.
                     CONFIG_DIR 상대경로 depth 계산에 사용한다.
    """
    if hints is None:
        hints = {}

    # CONFIG_DIR: tests/generated/{platform}[/{subfolder}*]/tc.py 에서 ROOT/config 까지
    # depth 0 (flat):    parent * 4 = tc.py → android/ → generated/ → tests/ → ROOT
    # depth 1 (1단계):   parent * 5
    parents = 4 + subfolder_depth
    config_dir_expr = 'Path(__file__)' + '.parent' * parents + ' / "config"'

    tc_number = meta["tc_number"]
    tc_slug = meta["tc_slug"]
    title = meta["title"]
    tc_blocks = meta["tc_blocks"]
    precondition = meta["precondition"]

    class_name = _to_class_name(tc_slug)
    all_selectors = _collect_all_selectors(tc_blocks)
    has_creds = _uses_credentials(tc_blocks)

    # --- 헤더 docstring ---
    header = (
        f'"""\n'
        f"tc_{tc_number}_{tc_slug}.py — {platform.capitalize()} {title} TC.\n"
        f"\n"
        f"Tests:\n"
    )
    for b in tc_blocks:
        header += f"    {b['function_name']}\n"
    header += '"""\n'

    # --- imports ---
    if platform == "android":
        imports = _build_android_imports()
    else:
        imports = _build_ios_imports()

    # --- 셀렉터 상수 ---
    sel_lines = ["", "# " + "-" * 74]
    sel_lines.append(
        "# Selectors — placeholder values from config/screens.json."
    )
    sel_lines.append(
        "# Replace with real resource-id / XPath once the app is attached."
    )
    sel_lines.append("# " + "-" * 74)
    for key, val in all_selectors.items():
        const_name = _sel_const_name(key)
        if const_name in hints:
            hint_val = hints[const_name]["value"]
            hint_strategy = hints[const_name]["strategy"]
            sel_lines.append(
                f'{const_name} = "{hint_val}"'
                f"  # healed: AppiumBy.{hint_strategy}"
            )
        else:
            sel_lines.append(f'{const_name} = "{val}"')

    sel_block = "\n".join(sel_lines)

    # --- 헬퍼 함수 ---
    if platform == "android":
        helpers = _build_android_helpers(tc_number, tc_slug, config_dir_expr)
    else:
        helpers = _build_ios_helpers(tc_number, tc_slug, config_dir_expr)

    # --- 클래스 ---
    if platform == "android":
        setup = _build_setup_android(precondition, has_creds)
    else:
        setup = _build_setup_ios(precondition, has_creds)

    teardown = _build_teardown()

    # TC 번호별 구분선 추가
    numbered_methods = []
    for idx, block in enumerate(tc_blocks):
        tc_label = f"TC-{tc_number.zfill(3)}-{str(idx + 1).zfill(2)}"
        numbered_methods.append(
            f"    # {'--' * 35}\n"
            f"    # {tc_label}\n"
            f"    # {'--' * 35}\n"
            + _build_test_method(block, tc_number, idx, platform)
        )

    methods_joined = "\n\n".join(numbered_methods)

    class_body = (
        f"class Test{class_name}:\n"
        f'    """{title} 화면 TC."""\n'
        f"\n"
        f"{setup}"
        f"\n"
        f"{teardown}"
        f"\n"
        f"{methods_joined}\n"
    )

    # --- 조립 ---
    parts = [
        header,
        imports,
        "",
        sel_block,
        "",
        helpers,
        "",
        "",
        class_body,
    ]

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="TC 마크다운 → pytest 코드 자동 생성"
    )
    parser.add_argument(
        "--platform", default="android", choices=["android", "ios"]
    )
    parser.add_argument(
        "--tc-dir", default=None,
        help="testcases/ 하위 폴더명 (미지정 시 testcases/ 전체 재귀 스캔)"
    )
    args = parser.parse_args()

    platform = args.platform
    print(f"[02_generate] platform={platform}")

    # testcases/ 스캔 루트 결정
    if args.tc_dir:
        scan_root = TESTCASES_DIR / args.tc_dir
        if not scan_root.is_dir():
            print(f"[02_generate] ERROR: tc-dir '{args.tc_dir}' 가 존재하지 않습니다.")
            return
        print(f"[02_generate] TC 폴더: testcases/{args.tc_dir}/")
    else:
        scan_root = TESTCASES_DIR

    # rglob으로 재귀 스캔 — 서브폴더 포함
    md_files = sorted(scan_root.rglob("tc_*.md"))
    if not md_files:
        print("[02_generate] WARNING: tc_*.md 파일이 없습니다.")
        return

    print(f"[02_generate] {len(md_files)}개 TC 마크다운 발견")

    # lessons_learned.md heal 성공 패턴 로드
    hints = _load_lessons_learned_hints()
    if hints:
        print(f"[02_generate] lessons_learned hints 로드: {list(hints.keys())}")
    else:
        print("[02_generate] lessons_learned hints 없음 — placeholder 사용")

    generated = []
    state = load_state()

    for md_path in md_files:
        print(f"  parsing: {md_path.relative_to(TESTCASES_DIR)}")
        meta = parse_md_file(md_path)

        # 플랫폼 필터
        if platform not in meta["platform"]:
            print(f"  skip {md_path.name} (platform not in {meta['platform']})")
            continue

        # 서브폴더 구조 미러링:
        #   testcases/foo/tc_001.md  →  tests/generated/android/foo/tc_001.py
        #   testcases/tc_001.md      →  tests/generated/android/tc_001.py
        rel_parent = md_path.parent.relative_to(TESTCASES_DIR)
        subfolder_depth = len(rel_parent.parts)

        out_dir = TESTS_DIR / platform / rel_parent
        out_dir.mkdir(parents=True, exist_ok=True)

        code = generate_test_file(
            meta, platform, hints=hints, subfolder_depth=subfolder_depth
        )

        out_name = f"tc_{meta['tc_number']}_{meta['tc_slug']}.py"
        out_path = out_dir / out_name
        out_path.write_text(code, encoding="utf-8")
        generated.append(str(out_path))
        print(f"  generated: {out_path.relative_to(ROOT)}")

    # state 업데이트
    state["step"] = "generated"
    state["platform"] = platform
    state["generated_tests"] = generated
    save_state(state)

    print(
        f"[02_generate] done. {len(generated)} file(s) generated"
        f" → tests/generated/{platform}/"
    )


if __name__ == "__main__":
    main()
