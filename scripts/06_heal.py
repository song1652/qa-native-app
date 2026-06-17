"""
06_heal.py — 실패 TC 셀렉터 self-heal (page_source XML 기반).

state/pipeline.json의 execute_results.errors 에서 실패 TC 목록을 읽어
dom_info XML에서 실제 요소를 탐색한 뒤 SEL_* 상수값을 교체하고 pytest를 재실행한다.

heal 흐름:
    실패 TC 파일명 → 화면명 추출 (tc_001_login → "login")
    → dom_info["login"]["xml"] 로드
    → XML 파싱 후 SEL_* 값과 속성 유사도 비교
    → best match 속성값으로 SEL 상수 + AppiumBy 전략 교체
    → pytest 재실행 → 성공 시 저장

dom_info 없을 때는 기존 전략 교체 방식(fallback)으로 처리한다.

Usage:
    python scripts/06_heal.py [--platform android|ios]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "pipeline.json"

# XML 속성 추출 대상 (Android UiAutomator2 기준)
ATTRS = ["resource-id", "content-desc", "text"]

# 속성별 AppiumBy 전략 매핑
ATTR_STRATEGY = {
    "resource-id": "ID",
    "content-desc": "ACCESSIBILITY_ID",
    "text": "XPATH",
}

# fallback: 전략 교체 순서 (dom_info 없을 때)
HEAL_STRATEGIES = ["ACCESSIBILITY_ID", "ID", "XPATH"]

LESSONS_FILE = ROOT / "agents" / "lessons_learned.md"


# ---------------------------------------------------------------------------
# Lessons Learned helpers
# ---------------------------------------------------------------------------

def _append_lessons_learned(result: dict, screen_name: str, platform: str):
    """heal 결과를 agents/lessons_learned.md에 추가한다.

    - heal 성공 시: [Locator Heal] 형식으로 기록
    - heal 실패 시: [Locator Heal Failed] 형식으로 기록
    - 동일 [screen_name — sel_const] 제목이 이미 있으면 스킵 (중복 방지)
    - platform이 'ios'이면 '## iOS' 섹션 아래, 그 외는 '## Appium / Android' 아래에 추가
    """
    LESSONS_FILE.parent.mkdir(exist_ok=True)

    if LESSONS_FILE.exists():
        content = LESSONS_FILE.read_text(encoding="utf-8")
    else:
        content = (
            "# Lessons Learned — App QA\n\n"
            "## Appium / Android\n\n"
            "## iOS\n\n"
            "## 공통\n\n"
        )

    is_success = "strategy" in result
    sel_const = result.get("sel_const", "UNKNOWN")
    heading_key = f"{screen_name} — {sel_const}"

    # 중복 방지: 동일 제목 이미 존재 시 스킵
    if heading_key in content:
        print(f"[06_heal] lessons_learned 스킵 (중복): {heading_key}")
        return

    if is_success:
        original_value = result.get("original_value", "")
        replacement_value = result.get("replacement_value", "")
        strategy = result.get("strategy", "")
        matched_attr = result.get("matched_attr", "")
        entry = (
            f"\n### [Locator Heal] {heading_key}\n"
            f"**문제**: `{original_value}` 로 요소를 찾지 못함 (NoSuchElementException)\n"
            f"**원인**: 생성 시 placeholder 값이 실제 앱 속성값과 불일치\n"
            f"**해결**: `{replacement_value}` (`AppiumBy.{strategy}`) 로 교체\n"
            f"**적용 범위**: {screen_name} 화면 / {matched_attr} 속성 기반 매칭\n\n"
            "---\n"
        )
    else:
        original_value = result.get("original_value", result.get("reason", ""))
        entry = (
            f"\n### [Locator Heal Failed] {heading_key}\n"
            f"**문제**: `{original_value}` — XML에서 유사 요소를 찾지 못함\n"
            f"**원인**: dom_info XML이 오래됐거나 화면 구조 변경 가능성\n"
            f"**해결**: `01_analyze.py` 재실행 후 dom_info 갱신 필요\n"
            f"**적용 범위**: {screen_name} 화면 heal 재시도 시 참고\n\n"
            "---\n"
        )

    # 플랫폼 섹션 결정
    if platform == "ios":
        section_header = "## iOS"
    else:
        section_header = "## Appium / Android"

    if section_header in content:
        insert_pos = content.index(section_header) + len(section_header)
        # 섹션 헤더 직후 개행 뒤에 삽입
        newline_pos = content.find("\n", insert_pos)
        if newline_pos == -1:
            newline_pos = len(content)
        content = (
            content[:newline_pos + 1] + entry + content[newline_pos + 1:]
        )
    else:
        content = content + f"\n{section_header}\n" + entry

    LESSONS_FILE.write_text(content, encoding="utf-8")
    status = "성공" if is_success else "실패"
    print(f"[06_heal] lessons_learned 업데이트 ({status}): {heading_key}")


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
        "heal_results": {},
        "heal_count": 0,
    }


def save_state(state: dict):
    STATE_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# TC 파일 관련 헬퍼
# ---------------------------------------------------------------------------

def _extract_failed_files(errors: list) -> list:
    """execute_results.errors 목록에서 TC 파일 경로를 추출한다.

    errors 항목은 문자열("경로::함수명 오류메시지") 또는
    dict({"file": "...", "error": "..."}) 형태를 모두 허용한다.
    """
    files = []
    seen = set()
    for entry in errors:
        if isinstance(entry, dict):
            fp = entry.get("file", "")
        else:
            fp = str(entry).split("::")[0].strip()

        fp = fp.strip()
        if fp and fp not in seen:
            path = Path(fp)
            if not path.is_absolute():
                path = ROOT / path
            if path.exists():
                files.append(str(path))
                seen.add(fp)
            else:
                print(f"[06_heal]   WARNING: 파일 없음 — {fp}")
    return files


def _screen_name_from_path(file_path: str) -> str:
    """TC 파일명에서 화면명을 추출한다.

    tc_001_login.py       → "login"
    tc_002_file_list.py   → "file_list"
    tc_003_file_detail.py → "file_detail"
    규칙: tc_{번호}_{화면명}.py → 화면명 부분 반환
    """
    stem = Path(file_path).stem  # tc_001_login
    parts = stem.split("_", 2)   # ["tc", "001", "login"]
    if len(parts) >= 3:
        return parts[2]
    return stem


def _find_sel_constants(source: str) -> list:
    """소스에서 SEL_* 상수 정의를 추출한다.

    반환: [{"const": "SEL_FOO", "value": "some_value"}, ...]
    """
    pattern = re.compile(r'^(SEL_\w+)\s*=\s*"([^"]+)"', re.MULTILINE)
    return [
        {"const": m.group(1), "value": m.group(2)}
        for m in pattern.finditer(source)
    ]


# ---------------------------------------------------------------------------
# XML 파싱 및 유사도 매칭
# ---------------------------------------------------------------------------

def _collect_elements(xml_text: str) -> list:
    """XML 텍스트에서 ATTRS 속성을 가진 요소 목록을 반환한다.

    반환: [{"resource-id": ..., "content-desc": ..., "text": ...}, ...]
    속성이 없으면 해당 키는 포함하지 않는다.
    """
    elements = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"[06_heal]   XML 파싱 오류: {exc}")
        return elements

    for node in root.iter():
        attrs = {}
        for attr in ATTRS:
            val = node.get(attr, "").strip()
            if val:
                attrs[attr] = val
        if attrs:
            elements.append(attrs)
    return elements


def _similarity_score(sel_value: str, attr_value: str) -> int:
    """sel_value와 attr_value의 유사도를 점수로 반환한다.

    점수 체계:
        3 — 정확 일치
        2 — 포함 일치 (한쪽이 다른 쪽에 포함)
        1 — 키워드 일치 (snake_case 분리 후 부분 포함)
        0 — 불일치
    """
    if not sel_value or not attr_value:
        return 0

    sel_lower = sel_value.lower()
    attr_lower = attr_value.lower()

    # 1단계: 정확 일치
    if sel_lower == attr_lower:
        return 3

    # 2단계: 포함 일치
    if sel_lower in attr_lower or attr_lower in sel_lower:
        return 2

    # 3단계: 키워드 일치 — snake_case 분리 후 개별 단어가 attr에 포함되는지
    keywords = [kw for kw in sel_value.split("_") if len(kw) > 2]
    if keywords and any(kw.lower() in attr_lower for kw in keywords):
        return 1

    return 0


def _find_best_match(sel_value: str, elements: list) -> dict:
    """SEL 상수값에 가장 잘 맞는 XML 요소 속성 정보를 반환한다.

    반환: {"attr": "resource-id", "value": "com.example:id/et_username"}
          매칭 없으면 {}
    """
    best_score = 0
    best_attr = ""
    best_value = ""

    for elem in elements:
        for attr in ATTRS:
            attr_value = elem.get(attr, "")
            if not attr_value:
                continue
            score = _similarity_score(sel_value, attr_value)
            if score > best_score:
                best_score = score
                best_attr = attr
                best_value = attr_value

    if best_score > 0:
        return {"attr": best_attr, "value": best_value}
    return {}


# ---------------------------------------------------------------------------
# 소스 교체 헬퍼
# ---------------------------------------------------------------------------

def _replace_sel_value_and_strategy(
    source: str,
    const_name: str,
    new_value: str,
    new_strategy: str,
) -> str:
    """소스에서 SEL_* 상수값과 해당 AppiumBy 전략을 동시에 교체한다.

    1) SEL_FOO = "old_value"  →  SEL_FOO = "new_value"
       XPATH 전략일 때는 //*[@text="new_value"] 형식으로 직접 교체
    2) AppiumBy.OLD_STRATEGY, const_name  →  AppiumBy.NEW_STRATEGY, const_name
    """
    # 1) 상수 정의 줄 교체
    #    XPATH 전략이면 처음부터 XPath 표현식으로 교체 (이중 치환 방지)
    if new_strategy == "XPATH":
        final_value = f'//*[@text="{new_value}"]'
    else:
        final_value = new_value

    def_pattern = re.compile(
        r'^(' + re.escape(const_name) + r'\s*=\s*)"[^"]*"',
        re.MULTILINE,
    )
    source = def_pattern.sub(r'\g<1>"' + final_value + '"', source)

    # 2) AppiumBy 전략 교체 — 어떤 전략이든 new_strategy로 교체
    strategy_pattern = re.compile(
        r'AppiumBy\.\w+(\s*,\s*' + re.escape(const_name) + r')'
    )
    source = strategy_pattern.sub(
        'AppiumBy.' + new_strategy + r'\1', source
    )

    return source


# ---------------------------------------------------------------------------
# Fallback: 전략만 교체 (dom_info 없을 때)
# ---------------------------------------------------------------------------

def _current_strategy(source: str, const_name: str) -> str:
    """소스에서 특정 상수가 사용된 AppiumBy 전략을 감지한다."""
    pattern = re.compile(
        r'AppiumBy\.(\w+),\s*' + re.escape(const_name)
    )
    m = pattern.search(source)
    if m:
        return m.group(1)
    return ""


def _replace_strategy_only(
    source: str, const_name: str,
    old_strategy: str, new_strategy: str
) -> str:
    """소스에서 특정 상수에 대한 AppiumBy 전략만 교체한다 (fallback용)."""
    suffix = r'(,\s*' + re.escape(const_name) + r')'
    pattern = re.compile(
        r'(AppiumBy\.)' + re.escape(old_strategy) + suffix
    )
    return pattern.sub(r'\g<1>' + new_strategy + r'\g<2>', source)


# ---------------------------------------------------------------------------
# pytest 실행
# ---------------------------------------------------------------------------

def _run_pytest_single(file_path: str) -> bool:
    """단일 TC 파일에 pytest를 실행하고 통과 여부를 반환한다."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", file_path, "-v", "--tb=no", "-q"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Heal 로직 — XML 기반
# ---------------------------------------------------------------------------

def heal_file_xml(file_path: str, dom_info: dict) -> dict:
    """dom_info XML 기반으로 단일 TC 파일에 self-heal을 적용한다.

    반환:
        성공: {
            "file": ..., "sel_const": ..., "original_value": ...,
            "replacement_value": ..., "strategy": ..., "matched_attr": ...
        }
        실패: {"file": ..., "reason": ...}
    """
    path = Path(file_path)
    source = path.read_text(encoding="utf-8")

    sel_constants = _find_sel_constants(source)
    if not sel_constants:
        return {"file": file_path, "reason": "SEL_* 상수를 찾을 수 없음"}

    screen_name = _screen_name_from_path(file_path)
    screen_info = dom_info.get(screen_name, {})
    xml_text = screen_info.get("xml", "")

    if not xml_text:
        return {
            "file": file_path,
            "reason": f"dom_info에 '{screen_name}' XML 없음",
        }

    elements = _collect_elements(xml_text)
    if not elements:
        return {
            "file": file_path,
            "reason": f"'{screen_name}' XML에서 요소를 파싱하지 못함",
        }

    # 원본 백업
    backup_path = path.with_suffix(".py.backup")
    if not backup_path.exists():
        shutil.copy2(str(path), str(backup_path))
        print(f"[06_heal]   backup: {backup_path.name}")

    # 1단계: 모든 SEL 상수에 대해 XML 매칭 후 일괄 적용
    healed_any = False
    heal_details = []

    for sel in sel_constants:
        const_name = sel["const"]
        original_value = sel["value"]

        print(f"[06_heal]   {const_name}: 값='{original_value}' 매칭 중...")

        match = _find_best_match(original_value, elements)
        if not match:
            print(f"[06_heal]   {const_name}: XML에서 매칭 요소 없음, 건너뜀")
            continue

        matched_attr = match["attr"]
        replacement_value = match["value"]
        new_strategy = ATTR_STRATEGY[matched_attr]

        print(
            f"[06_heal]   {const_name}: {matched_attr}='{replacement_value}'"
            f" 전략={new_strategy}"
        )

        source = _replace_sel_value_and_strategy(
            source, const_name, replacement_value, new_strategy
        )
        healed_any = True
        heal_details.append({
            "sel_const": const_name,
            "original_value": original_value,
            "replacement_value": replacement_value,
            "strategy": new_strategy,
            "matched_attr": matched_attr,
        })

    if not healed_any:
        return {
            "file": file_path,
            "reason": "XML 매칭 후 모든 시도 실패",
        }

    # 2단계: 모든 heal 적용 후 pytest 1회 실행
    path.write_text(source, encoding="utf-8")
    print(f"[06_heal]   {len(heal_details)}개 SEL 일괄 적용 후 pytest 실행")

    if _run_pytest_single(file_path):
        print(f"[06_heal]   성공: {len(heal_details)}개 SEL heal 완료")
        last = heal_details[-1]
        return {
            "file": file_path,
            "sel_const": last["sel_const"],
            "original_value": last["original_value"],
            "replacement_value": last["replacement_value"],
            "strategy": last["strategy"],
            "matched_attr": last["matched_attr"],
            "heal_details": heal_details,
        }

    # pytest 실패 — 원본 복원
    source_backup = backup_path.read_text(encoding="utf-8")
    path.write_text(source_backup, encoding="utf-8")
    print(f"[06_heal]   pytest 실패, 원본 복원 ({backup_path.name})")

    return {
        "file": file_path,
        "reason": "XML 매칭 후 모든 시도 실패",
        "sel_const": heal_details[-1]["sel_const"],
    }


# ---------------------------------------------------------------------------
# Heal 로직 — 전략 교체 fallback
# ---------------------------------------------------------------------------

def heal_file_fallback(file_path: str) -> dict:
    """dom_info 없을 때 AppiumBy 전략만 교체하는 fallback heal.

    반환:
        성공: {"file": ..., "original_value": ..., "replacement_value": ..., "strategy": ...}
        실패: {"file": ..., "reason": ...}
    """
    path = Path(file_path)
    source = path.read_text(encoding="utf-8")

    sel_constants = _find_sel_constants(source)
    if not sel_constants:
        return {"file": file_path, "reason": "SEL_* 상수를 찾을 수 없음"}

    backup_path = path.with_suffix(".py.backup")
    if not backup_path.exists():
        shutil.copy2(str(path), str(backup_path))
        print(f"[06_heal]   backup: {backup_path.name}")

    for sel in sel_constants:
        const_name = sel["const"]
        original_value = sel["value"]

        current = _current_strategy(source, const_name)
        if not current:
            print(f"[06_heal]   {const_name}: 전략 감지 불가, 건너뜀")
            continue

        if current in HEAL_STRATEGIES:
            start_idx = HEAL_STRATEGIES.index(current)
            strategies_to_try = HEAL_STRATEGIES[start_idx + 1:]
        else:
            strategies_to_try = HEAL_STRATEGIES[1:]

        for new_strategy in strategies_to_try:
            print(f"[06_heal]   {const_name}: fallback 전략 시도 → {new_strategy}")
            patched = _replace_strategy_only(
                source, const_name, current, new_strategy
            )
            path.write_text(patched, encoding="utf-8")

            if _run_pytest_single(file_path):
                print(f"[06_heal]   성공(fallback): {const_name} → {new_strategy}")
                source = patched
                return {
                    "file": file_path,
                    "sel_const": const_name,
                    "original_value": original_value,
                    "replacement_value": f"AppiumBy.{new_strategy}",
                    "strategy": new_strategy,
                    "matched_attr": "",
                }

            source_backup = backup_path.read_text(encoding="utf-8")
            path.write_text(source_backup, encoding="utf-8")
            source = source_backup

    return {
        "file": file_path,
        "reason": "fallback 전략 모두 실패",
        "sel_const": const_name,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="실패 TC 셀렉터 self-heal (page_source XML 기반)"
    )
    parser.add_argument(
        "--platform", default="android", choices=["android", "ios"]
    )
    args = parser.parse_args()

    print(f"[06_heal] platform={args.platform}")

    state = load_state()
    dom_info = state.get("dom_info", {})

    if not dom_info:
        print(
            "[06_heal] dom_info 없음 — 01_analyze.py를 먼저 실행하세요."
            " fallback(전략 교체) 모드로 진행합니다."
        )

    execute_results = state.get("execute_results", {})
    errors = execute_results.get("errors", [])

    if not errors:
        print("[06_heal] heal할 항목 없음 — execute_results.errors가 비어 있습니다.")
        state["step"] = "healed"
        state["heal_results"] = {"healed": [], "failed": []}
        state["heal_count"] = 0
        save_state(state)
        sys.exit(0)

    failed_files = _extract_failed_files(errors)
    if not failed_files:
        print("[06_heal] 유효한 TC 파일 없음 — errors에서 파일을 찾지 못했습니다.")
        state["step"] = "heal_failed"
        state["heal_results"] = {"healed": [], "failed": []}
        state["heal_count"] = 0
        save_state(state)
        sys.exit(1)

    print(f"[06_heal] {len(failed_files)}개 실패 TC 처리 시작")

    healed = []
    failed = []

    for file_path in failed_files:
        fname = Path(file_path).name
        print(f"[06_heal] healing: {fname}")

        if dom_info:
            result = heal_file_xml(file_path, dom_info)
        else:
            result = heal_file_fallback(file_path)

        screen_name = _screen_name_from_path(file_path)

        # heal_details가 있으면 각 항목별로 lessons_learned에 기록
        if "heal_details" in result:
            for detail in result["heal_details"]:
                _append_lessons_learned(
                    {"file": file_path, **detail},
                    screen_name,
                    args.platform,
                )
        else:
            _append_lessons_learned(result, screen_name, args.platform)

        if "strategy" in result:
            healed.append(result)
        else:
            failed.append(result)

    heal_count = len(healed)

    state["heal_results"] = {
        "healed": healed,
        "failed": failed,
    }
    state["heal_count"] = heal_count

    if failed:
        state["step"] = "heal_failed"
        save_state(state)
        print(
            f"[06_heal] 완료 — healed={heal_count}, failed={len(failed)}"
        )
        sys.exit(1)
    else:
        state["step"] = "healed"
        save_state(state)
        print(f"[06_heal] done — {heal_count}개 TC 복구 완료")


if __name__ == "__main__":
    main()
