"""report_html.py의 TC 마크다운 파서(_parse_tc_meta_from_md)와 case_row()의
EXPECTED/ERROR 필드 독립성을 실제 형식으로 고정한다.

2026-09-17 사고 재발 방지: 헤더 정규식이 실제 TC 마크다운(`## 사전 조건` 등)과
맞지 않아 PRECONDITION/STEPS/EXPECTED가 몇 달간 조용히 비어 있었고, EXPECTED가
비면 ERROR(pytest longrepr)로 fallback하던 코드가 실패 원인 텍스트를 EXPECTED에
그대로 노출했다.
"""
import html
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]

_spec = importlib.util.spec_from_file_location(
    "report_html_under_test", ROOT / "scripts" / "report_html.py"
)
report_html = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report_html)


SIMPLE_FORMAT_MD = """# TC: 화면 밝기 슬라이더 존재 확인

## 기본 정보
- **플랫폼**: android
- **TC ID**: tc_display_brightness
- **그룹**: obs_demo
- **우선순위**: Medium

## 사전 조건
- Android 에뮬레이터 또는 실기기 연결

## 테스트 단계
1. Settings 앱 실행
2. "Display" 메뉴 탭
3. "Brightness level" 슬라이더 확인

## 예상 결과
- 밝기 슬라이더 요소가 존재함
- 슬라이더가 인터랙션 가능한 상태
"""

STRUCTURED_FORMAT_MD = """---
id: tc_001
priority: medium
tags: [imported]
type: structured
---
# TC-001: 로그인 성공

## 목적
로그인 성공

## 플랫폼
- Android

## 전제조건
- 앱이 실행된 상태 (precondition: app_launch)

## 테스트 케이스 1

### 테스트 함수명
`test_login`

### 단계
1. 로그인 버튼 탭
2. 아이디 입력

### 기대결과
- 로그인 성공
- 홈 화면 진입
"""


@pytest.fixture
def testcases_dir(tmp_path, monkeypatch):
    d = tmp_path / "testcases"
    d.mkdir()
    monkeypatch.setattr(report_html, "TESTCASES_DIR", d)
    return d


def test_parses_simple_obs_demo_format(testcases_dir):
    (testcases_dir / "android" / "obs_demo").mkdir(parents=True)
    (testcases_dir / "android" / "obs_demo" / "tc_display_brightness.md").write_text(
        SIMPLE_FORMAT_MD, encoding="utf-8"
    )

    meta = report_html._parse_tc_meta_from_md(
        "tests/generated/android/obs_demo/tc_display_brightness.py"
    )

    assert meta["precondition"] == ["Android 에뮬레이터 또는 실기기 연결"]
    assert meta["steps"] == [
        'Settings 앱 실행', '"Display" 메뉴 탭', '"Brightness level" 슬라이더 확인',
    ]
    assert meta["expected"] == "밝기 슬라이더 요소가 존재함\n슬라이더가 인터랙션 가능한 상태"


def test_parses_structured_import_excel_format(testcases_dir):
    (testcases_dir / "android" / "settings").mkdir(parents=True)
    (testcases_dir / "android" / "settings" / "tc_001_login.md").write_text(
        STRUCTURED_FORMAT_MD, encoding="utf-8"
    )

    meta = report_html._parse_tc_meta_from_md(
        "tests/generated/android/settings/tc_001_login.py"
    )

    assert meta["precondition"] == ["앱이 실행된 상태 (precondition: app_launch)"]
    assert meta["steps"] == ["로그인 버튼 탭", "아이디 입력"]
    assert meta["expected"] == "로그인 성공\n홈 화면 진입"


def test_missing_markdown_returns_empty_not_error(testcases_dir):
    """대응하는 .md가 없으면 빈 값을 반환한다 (예외로 죽지 않음)."""
    meta = report_html._parse_tc_meta_from_md(
        "tests/generated/android/unknown/tc_missing.py"
    )
    assert meta == {
        "title": "tc_missing", "precondition": [], "steps": [], "expected": "",
    }


def test_case_row_expected_never_falls_back_to_error_text():
    """EXPECTED는 TC 마크다운 값만 쓰고, 비어 있어도 pytest 에러 메시지로
    대체되지 않아야 한다 — self = <...object...> 노출 버그의 회귀 테스트."""
    longrepr_like_error = (
        "self = <tests.generated.android.obs_demo.tc_x.TestX object at 0x10>"
    )
    rendered = report_html.case_row(
        {
            "title": "TC: 예시", "precondition": [], "steps": [],
            "expected": "",  # 마크다운에 예상 결과가 없는 경우
            "error": longrepr_like_error,
        },
        "grp_0", "failed",
    )

    expected_val = re.search(
        r'Expected</span>\s*<span class="detail-val">(.*?)</span>', rendered
    ).group(1)
    assert expected_val == "-"
    assert html.escape(longrepr_like_error, quote=True) in rendered  # ERROR 필드에는 그대로 나와야 함
