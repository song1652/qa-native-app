from __future__ import annotations

import pytest

import _tc_library as lib
from _tc_template import analyze_workbook
from _tc_xlsx_import import import_workbook

SUITE = "야핏무브"


@pytest.fixture
def seeded(library_dir, template_xlsx):
    profiles = analyze_workbook(template_xlsx)
    cases = import_workbook(template_xlsx, profiles, ["혜택", "홈"], {"혜택": "BEN", "홈": "HOME"})
    lib.save_template(SUITE, template_xlsx, profiles)
    lib.import_cases(SUITE, ["혜택", "홈"], cases, "tester")


def _draft(**kw):
    base = {"sheet": "혜택", "path": ["혜택 탭", "상단 배너", ""], "feature": "배너 롤링", "steps": ["대기"],
            "expected": "다음 배너로 넘어간다.", "priority": "P1", "source_refs": ["file:abc#§2"],
            "draft_meta": {"job_id": "job_000000000001"}}
    base.update(kw)
    return base


def test_add_drafts_goes_to_end_of_matching_branch(seeded):
    created = lib.add_drafts(SUITE, [_draft(), _draft(feature="두 번째", path=["혜택 탭", "신규회원 한정 혜택", "돈불리기"])], "generator")
    assert [c["case_id"] for c in created] == ["BEN_0006", "BEN_0007"]
    order = [c["case_id"] for c in lib.load_cases(SUITE)]
    assert order.index("BEN_0006") == order.index("BEN_0003") + 1
    assert order.index("BEN_0007") == order.index("BEN_0005") + 1
    assert lib.filter_cases(lib.load_cases(SUITE), {"job": "job_000000000001"})[0]["status"] == "draft"
    assert lib.history(SUITE, "BEN_0006")[0]["after"] == "generate"


def test_meta_and_source_refs_do_not_bump_rev(seeded):
    case = lib.set_draft_meta(SUITE, "BEN_0001", {"duplicate_checked": True})
    assert (case["rev"], case["draft_meta"]) == (1, {"duplicate_checked": True})
    case = lib.add_source_refs(SUITE, "BEN_0001", ["file:abc#§1", "file:abc#§1"])
    assert case["source_refs"][-1] == "file:abc#§1" and case["source_refs"].count("file:abc#§1") == 1
    assert case["rev"] == 1


def test_reserved_suite_names(library_dir):
    for name in ("profiles", "sources", "jobs", "import", "exports"):
        with pytest.raises(lib.LibraryError):
            lib.suite_dir(name)
