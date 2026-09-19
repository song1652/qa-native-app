"""02_generate.py의 마크다운 파서(_extract_section/parse_tc_blocks/parse_md_file)를
실제 TC 마크다운 형식으로 검증한다.

report_html.py의 TC 마크다운 파서가 실제 헤더 형식과 맞지 않아 몇 달간 조용히
비어 있던 사고(2026-09-17)가 재발하지 않도록, import_excel.py가 실제로 쓰는
마크다운을 02_generate.py가 그대로 읽어 들이는 라운드트립을 고정한다.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]

_gen_spec = importlib.util.spec_from_file_location(
    "generate_script_under_test", ROOT / "scripts" / "02_generate.py"
)
generate = importlib.util.module_from_spec(_gen_spec)
_gen_spec.loader.exec_module(generate)

_imp_spec = importlib.util.spec_from_file_location(
    "import_excel_under_test", ROOT / "scripts" / "import_excel.py"
)
import_excel = importlib.util.module_from_spec(_imp_spec)
_imp_spec.loader.exec_module(import_excel)


@pytest.fixture
def rendered_markdown():
    """import_excel.py가 실제로 쓰는 것과 동일한 마크다운 본문."""
    return import_excel._render_markdown(
        platform="android",
        tc_number="001",
        summary="로그인 성공",
        precondition="앱이 실행된 상태 (precondition: app_launch)",
        steps="로그인 버튼 탭\n아이디 입력",
        expected="로그인 성공\n홈 화면 진입",
        priority_value="High",
    )


def test_import_excel_renders_structured_tc_blocks(rendered_markdown):
    """작성 형식이 02_generate.py가 기대하는 헤더와 실제로 일치하는지 그 자체로 확인."""
    assert "## 테스트 케이스 1" in rendered_markdown
    assert "### 테스트 함수명" in rendered_markdown
    assert "### 단계" in rendered_markdown
    assert "### 기대결과" in rendered_markdown


def test_parse_md_file_round_trips_import_excel_output(tmp_path, rendered_markdown):
    md_path = tmp_path / "tc_001_login-seong-gong.md"
    md_path.write_text(rendered_markdown, encoding="utf-8")

    meta = generate.parse_md_file(md_path)

    assert meta["tc_number"] == "001"
    assert meta["platform"] == ["android"]
    assert meta["precondition"] == "app_launch"
    assert len(meta["tc_blocks"]) == 1


def test_parse_tc_blocks_extracts_function_name_steps_and_expected(rendered_markdown):
    blocks = generate.parse_tc_blocks(rendered_markdown)

    assert len(blocks) == 1
    block = blocks[0]
    assert block["function_name"] == "test_로그인_성공"
    assert block["steps"] == ["로그인 버튼 탭", "아이디 입력"]
    assert block["expected"] == "로그인 성공 홈 화면 진입"


def test_parse_tc_blocks_handles_selector_hints():
    """### 셀렉터 힌트 서브섹션도 함께 파싱되는지 확인 (수동 작성 TC 대응)."""
    md = (
        "## 테스트 케이스 1\n\n"
        "### 테스트 함수명\n`test_tap_login`\n\n"
        "### 단계\n1. 로그인 버튼 탭\n\n"
        "### 기대결과\n- 홈 화면 진입\n\n"
        "### 셀렉터 힌트\n- login_button: `//android.widget.Button[@text='Login']`\n"
    )
    blocks = generate.parse_tc_blocks(md)

    assert blocks[0]["selectors"] == {
        "login_button": "//android.widget.Button[@text='Login']"
    }
