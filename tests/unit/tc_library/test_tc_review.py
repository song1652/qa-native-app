from __future__ import annotations

import pytest

import _tc_library as lib
from _tc_profiles import DEFAULT_PROFILE
from _tc_review import classify, coverage_gaps, find_duplicates, resolve_duplicate, similarity
from _tc_model import new_case
from _tc_template import analyze_workbook
from _tc_xlsx_import import import_workbook

SUITE = "야핏무브"


@pytest.fixture
def seeded(library_dir, template_xlsx):
    profiles = analyze_workbook(template_xlsx)
    cases = import_workbook(template_xlsx, profiles, ["혜택", "홈"], {"혜택": "BEN", "홈": "HOME"})
    lib.save_template(SUITE, template_xlsx, profiles)
    lib.import_cases(SUITE, ["혜택", "홈"], cases, "tester")


def test_similarity_and_classify():
    a = new_case(feature="배너 스크롤", steps=["혜택 탭 선택"], expected="배너가 넘어간다.")
    b = new_case(feature="배너 스크롤!", steps=["혜택 탭  선택"], expected="배너가 넘어간다")
    assert similarity(a, b) == 1.0
    assert classify(new_case(expected="진입 불가 안내 팝업이 노출된다.")) == "negative"
    assert classify(new_case(steps=["아이디 입력"], expected="필수 입력 항목입니다 문구가 노출된다.")) == "validation"
    assert classify(new_case(expected="홈 화면으로 이동한다.")) == "positive"


def test_skip_and_add_actions(seeded):
    draft = lib.create_case(SUITE, {"sheet": "혜택", "path": ["혜택 탭", "", ""], "feature": "x",
                                    "draft_meta": {"duplicates": [{"case_id": "BEN_0001", "similarity": 0.8}]}}, "t")
    assert resolve_duplicate(SUITE, draft["case_id"], 1, "add", "t")["draft"]["draft_meta"]["duplicate_checked"] is True
    assert resolve_duplicate(SUITE, draft["case_id"], 1, "skip", "t")["draft"]["status"] == "rejected"
    with pytest.raises(lib.LibraryError):
        resolve_duplicate(SUITE, draft["case_id"], 2, "merge", "t")


def test_duplicates_resolution_and_coverage(seeded):
    existing = lib.get_case(SUITE, "BEN_0002")
    lib.patch_case(SUITE, "BEN_0002", 1, {"status": "approved"}, "t")
    twin = lib.create_case(SUITE, {k: existing[k] for k in lib.EDITABLE_FIELDS if k != "status"}, "t")
    hits = find_duplicates(twin, lib.load_cases(SUITE))
    assert hits[0] == {"case_id": "BEN_0002", "similarity": 1.0}

    result = resolve_duplicate(SUITE, twin["case_id"], twin["rev"], "update", "t", "BEN_0002", 1)
    assert result["deleted_draft"] == twin["case_id"]
    assert twin["case_id"] not in [c["case_id"] for c in lib.load_cases(SUITE)]

    strict_profile = {**DEFAULT_PROFILE, "coverage": {"positive": 1, "negative": 1, "validation_if_input": 1}}
    gaps = coverage_gaps(SUITE, "혜택", ["혜택 탭", "신규회원 한정 혜택", "돈불리기"], strict_profile)
    assert gaps == [{"feature": "진입 불가", "positive": 0, "negative": 2, "validation": 0,
                     "has_input": False, "missing": ["정상"]}]
