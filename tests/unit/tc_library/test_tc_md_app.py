from __future__ import annotations

import importlib.util
from pathlib import Path

import _paths
import _tc_library as lib
import pytest
from _tc_model import new_case


def test_approved_case_exports_only_selected_platform_and_pipeline_reads_it(library_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(_paths, "TESTCASES_DIR", tmp_path / "testcases")
    case = new_case(case_id="APP_0001", sheet="로그인", path=["로그인", "", ""], feature="로그인 성공",
                    precondition="앱 실행", steps=["로그인 누르기"], expected="홈 표시", priority="P1",
                    status="approved", platforms=["ios"])
    lib.import_cases("앱", ["로그인"], [case], "t")
    import _tc_md_export as md
    md.save_group("앱", ["로그인", "로그인"], "login", "LOG")
    run = md.preview("앱")
    assert len(run["rows"]) == 1
    assert run["rows"][0]["platform"] == "ios"
    assert "priority: high" in run["rows"][0]["content"]
    md.commit("앱", run["run_id"], [])
    files = list((tmp_path / "testcases").rglob("*.md"))
    assert len(files) == 1 and "ios/login" in str(files[0])
    generator = Path(__file__).resolve().parents[3] / "scripts" / "02_generate.py"
    spec = importlib.util.spec_from_file_location("generate02", generator)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.parse_tc_blocks(files[0].read_text(encoding="utf-8"))


def test_default_skip_conflict_and_rollback(library_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(_paths, "TESTCASES_DIR", tmp_path / "testcases")
    case = new_case(case_id="APP_0001", sheet="로그인", path=["로그인", "", ""], feature="로그인 성공",
                    steps=["누르기"], expected="표시", priority="P1", status="approved")
    lib.import_cases("앱", ["로그인"], [case], "t")
    import _tc_md_export as md
    md.save_group("앱", ["로그인", "로그인"], "login", "LOG")
    run = md.preview("앱")
    target = tmp_path / "testcases" / "android" / "login" / "tc_LOG_01_로그인_성공.md"
    target.parent.mkdir(parents=True)
    target.write_text("existing", encoding="utf-8")
    md.commit("앱", run["run_id"], [])
    assert target.read_text(encoding="utf-8") == "existing"
    ios_file = next((tmp_path / "testcases" / "ios").rglob("*.md"))
    md.rollback("앱", run["run_id"])
    assert not ios_file.exists() and target.read_text(encoding="utf-8") == "existing"


def test_md_export_refuses_changed_target_on_commit_and_rollback(library_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(_paths, "TESTCASES_DIR", tmp_path / "testcases")
    case = new_case(case_id="APP_0001", sheet="로그인", path=["로그인", "", ""], feature="로그인 성공",
                    steps=["누르기"], expected="표시", status="approved", platforms=["ios"])
    lib.import_cases("앱", ["로그인"], [case], "t")
    import _tc_md_export as md
    md.save_group("앱", ["로그인", "로그인"], "login", "LOG")
    run = md.preview("앱")
    target = tmp_path / "testcases" / run["rows"][0]["file"]
    target.parent.mkdir(parents=True)
    target.write_text("manual", encoding="utf-8")
    with pytest.raises(lib.LibraryError) as error:
        md.commit("앱", run["run_id"], [], overwrite=True)
    assert error.value.code == "TARGET_CHANGED"
    target.unlink()
    md.commit("앱", run["run_id"], [])
    target.write_text("manual after export", encoding="utf-8")
    with pytest.raises(lib.LibraryError) as error:
        md.rollback("앱", run["run_id"])
    assert error.value.code == "TARGET_CHANGED"
    assert target.read_text(encoding="utf-8") == "manual after export"
