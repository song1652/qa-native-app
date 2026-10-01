from __future__ import annotations

from _tc_model import (
    format_steps, join_expected, merge_results, new_case, next_case_id, parse_steps,
    split_expected, validate_case,
)


def _codes(case: dict) -> list[str]:
    return [issue["code"] for issue in validate_case(case)]


def _valid(**overrides) -> dict:
    fields = dict(case_id="BEN_0001", sheet="혜택", path=["혜택 탭", "", ""],
                  feature="혜택 탭 버튼", steps=["앱 실행"], expected="혜택 탭 화면으로 진입된다.",
                  priority="P0")
    fields.update(overrides)
    return new_case(**fields)


def test_parse_steps_strips_numbers_and_joins_continuation_lines():
    assert parse_steps("1. 앱 실행\n2) 혜택 탭 선택\n   (하단 탭)\n") == ["앱 실행", "혜택 탭 선택\n(하단 탭)"]
    assert format_steps(["앱 실행", "혜택 탭 선택"]) == "1. 앱 실행\n2. 혜택 탭 선택"


def test_split_expected_separates_ui_text_bullets():
    expected, bullets = split_expected("팝업이 노출된다.\n- 내일부터 참여할 수 있어요\n- 확인")
    assert expected == "팝업이 노출된다."
    assert bullets == [{"text": "내일부터 참여할 수 있어요", "verified": True},
                       {"text": "확인", "verified": True}]
    assert join_expected(expected, bullets) == "팝업이 노출된다.\n- 내일부터 참여할 수 있어요\n- 확인"


def test_merge_results_prefers_fail_then_na_and_keeps_blank_as_not_run():
    assert merge_results(["fail", "pass"]) == "fail"
    assert merge_results(["pass", "na"]) == "na"
    assert merge_results(["", ""]) == ""


def test_next_case_id_continues_after_highest_number():
    assert next_case_id("BEN", {"BEN_0002", "BEN_0010", "HOME_0099"}) == "BEN_0011"
    assert next_case_id("BEN", set()) == "BEN_0001"


def test_valid_case_has_no_issues():
    assert validate_case(_valid()) == []


def test_empty_priority_is_only_a_warning():
    issues = validate_case(_valid(priority=""))
    assert [(i["level"], i["code"]) for i in issues] == [("warning", "PRIORITY_EMPTY")]


def test_invalid_values_are_errors():
    assert "PRIORITY_INVALID" in _codes(_valid(priority="상"))
    assert "RESULT_INVALID" in _codes(_valid(execution_result="done"))
    assert "STEP_EMPTY" in _codes(_valid(steps=["앱 실행", " "]))
    assert "PATH_EMPTY" in _codes(_valid(path=["", "", ""]))
    assert "MISSING_FIELD" in _codes(_valid(expected=""))


def test_vague_expected_is_rejected_even_inside_bullets():
    assert "VAGUE_EXPECTED" in _codes(_valid(expected="팝업이 정상적으로 노출된다."))
    assert "VAGUE_EXPECTED" in _codes(_valid(bullets=[{"text": "정상 동작", "verified": False}]))
