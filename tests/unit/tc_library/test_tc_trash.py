"""스위트 삭제·휴지통 (_tc_trash). 지운 스위트가 늦게 도착한 쓰기로 되살아나지 않는지 함께 본다."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

import _tc_generate as gen
import _tc_library as lib
import _tc_md_export as md
import _tc_sources as src
import _tc_trash as trash
from _state import update_state
from _tc_template import analyze_workbook
from _tc_xlsx_import import import_workbook
from tests.unit.tc_library.source_fixtures import PRD_MD

SUITE = "야핏무브"
TARGET = {"sheet": "혜택", "path": ["혜택 탭", "상단 배너"]}


@pytest.fixture
def seeded(library_dir, template_xlsx):
    profiles = analyze_workbook(template_xlsx)
    cases = import_workbook(template_xlsx, profiles, ["혜택", "홈"], {"혜택": "BEN", "홈": "HOME"})
    lib.save_template(SUITE, template_xlsx, profiles)
    lib.import_cases(SUITE, ["혜택", "홈"], cases, "tester")
    bundle = src.new_bundle()
    src.add_file(bundle, "prd.md", PRD_MD.encode())
    return bundle


def _fake_run(library_dir, suite: str, run_id: str = "libimp_" + "a" * 16):
    root = library_dir / "_import_runs"
    root.mkdir(exist_ok=True)
    (root / f"{run_id}.json").write_text(json.dumps(
        {"run_id": run_id, "suite": suite, "status": "committed", "created_at": "2026-09-30T10:00:00"}), encoding="utf-8")
    return root / f"{run_id}.json"


def test_delete_moves_suite_jobs_and_runs_to_trash(seeded, fake_claude, library_dir):
    job = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본")
    gen.run_job(job["job_id"])
    run = _fake_run(library_dir, SUITE)
    other = _fake_run(library_dir, "다른스위트", "libimp_" + "b" * 16)

    meta = trash.delete_suite(SUITE, SUITE)

    assert [s["suite"] for s in lib.list_suites()] == []
    assert not lib.suite_dir(SUITE).exists() and not run.exists() and other.exists()
    assert gen.latest_job(SUITE) is None                     # 같은 이름으로 다시 만들어도 옛 작업이 붙지 않는다
    assert meta["cases"] == 6 + 2 and meta["jobs"] == [job["job_id"]] and meta["runs"] == [run.name]
    assert (library_dir / "_sources" / seeded / "manifest.json").exists()    # 공유 소스는 그대로
    assert [i["trash_id"] for i in trash.list_trash()] == [meta["trash_id"]]


def test_confirm_must_match_and_names_are_validated(seeded):
    with pytest.raises(lib.LibraryError) as exc:
        trash.delete_suite(SUITE, "다른이름")
    assert exc.value.code == "CONFIRM_MISMATCH"
    for bad in ("_trash", "..", "trash", "없는스위트"):
        with pytest.raises(lib.LibraryError) as exc:
            trash.delete_suite(bad, bad)
        assert exc.value.code in ("INVALID_SUITE", "SUITE_NOT_FOUND"), bad
    with pytest.raises(lib.LibraryError) as exc:
        trash.restore_suite("../x")
    assert exc.value.code == "INVALID_TRASH"


def test_running_generation_blocks_delete(seeded, fake_claude):
    job = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본")     # queued
    with pytest.raises(lib.LibraryError) as exc:
        trash.delete_suite(SUITE, SUITE)
    assert exc.value.code == "JOB_RUNNING" and exc.value.status == 409
    gen.run_job(job["job_id"])
    trash.delete_suite(SUITE, SUITE)


def test_late_writes_do_not_recreate_deleted_suite(seeded):
    case = lib.load_cases(SUITE)[0]
    trash.delete_suite(SUITE, SUITE)
    late_writes = [
        lambda: lib.create_case(SUITE, {"sheet": "혜택", "path": ["혜택 탭"], "feature": "x"}, "t"),
        lambda: lib.patch_case(SUITE, case["case_id"], case["rev"], {"feature": "x"}, "t"),
        lambda: lib.add_drafts(SUITE, [{**case, "case_id": ""}], "t"),
        lambda: lib.add_branch(SUITE, "혜택", ["새 분류"]),
        lambda: md.save_group(SUITE, ["혜택", "혜택 탭"], "grp", "GRP"),
    ]
    for write in late_writes:
        with pytest.raises(lib.LibraryError) as exc:
            write()
        assert exc.value.code == "SUITE_NOT_FOUND" and exc.value.status == 404
    assert not lib.suite_dir(SUITE).exists()
    assert lib.load_cases(SUITE) == []                       # 읽기는 빈 결과 (폴더를 만들지 않음)
    assert not lib.suite_dir(SUITE).exists()


def test_restore_brings_everything_back_and_refuses_name_clash(seeded, fake_claude, library_dir, template_xlsx):
    job = gen.create_job(SUITE, bundle_id=seeded, target=TARGET, profile="기본")
    gen.run_job(job["job_id"])
    run = _fake_run(library_dir, SUITE)
    meta = trash.delete_suite(SUITE, SUITE)

    profiles = analyze_workbook(template_xlsx)             # 같은 이름으로 새 스위트를 가져온 경우
    lib.save_template(SUITE, template_xlsx, profiles)
    with pytest.raises(lib.LibraryError) as exc:
        trash.restore_suite(meta["trash_id"])
    assert exc.value.code == "SUITE_EXISTS" and exc.value.status == 409

    trash.delete_suite(SUITE, SUITE)
    trash.restore_suite(meta["trash_id"])
    assert len(lib.load_cases(SUITE)) == 8 and run.exists()
    assert gen.latest_job(SUITE)["job_id"] == job["job_id"]
    assert [i["trash_id"] for i in trash.list_trash()] != [meta["trash_id"]]


def test_expired_items_are_purged_when_listed(seeded):
    meta = trash.delete_suite(SUITE, SUITE)
    path = trash.trash_root() / meta["trash_id"] / "meta.json"
    old = (datetime.now() - timedelta(days=trash.RETENTION_DAYS + 1)).isoformat(timespec="seconds")
    update_state(path, lambda m: {**m, "deleted_at": old})
    assert trash.list_trash() == []
    assert not path.parent.exists()


def test_purge_removes_one_item(seeded):
    meta = trash.delete_suite(SUITE, SUITE)
    assert trash.purge(meta["trash_id"], SUITE)["suite"] == SUITE
    assert trash.list_trash() == []
    with pytest.raises(lib.LibraryError) as exc:
        trash.purge(meta["trash_id"], SUITE)
    assert exc.value.code == "TRASH_NOT_FOUND"


def test_purge_requires_matching_suite_name(seeded):
    meta = trash.delete_suite(SUITE, SUITE)
    with pytest.raises(lib.LibraryError) as exc:
        trash.purge(meta["trash_id"], "다른스위트")
    assert exc.value.code == "CONFIRM_MISMATCH"
    assert [i["trash_id"] for i in trash.list_trash()] == [meta["trash_id"]]


def test_purge_after_restore_is_not_found(seeded):
    meta = trash.delete_suite(SUITE, SUITE)
    trash.restore_suite(meta["trash_id"])
    with pytest.raises(lib.LibraryError) as exc:
        trash.purge(meta["trash_id"], SUITE)
    assert exc.value.code == "TRASH_NOT_FOUND"
    assert lib.suite_dir(SUITE).is_dir()


def test_purge_rejects_malformed_id(seeded):
    with pytest.raises(lib.LibraryError) as exc:
        trash.purge("../x", SUITE)
    assert exc.value.code == "INVALID_TRASH"


def test_default_suite_cannot_be_deleted(library_dir):
    lib.import_cases(lib.DEFAULT_SUITE, ["테스트케이스"], [], "tester")
    with pytest.raises(lib.LibraryError) as exc:
        trash.delete_suite(lib.DEFAULT_SUITE, lib.DEFAULT_SUITE)
    assert exc.value.code == "DEFAULT_SUITE"
    assert lib.suite_dir(lib.DEFAULT_SUITE).is_dir()
    assert [s["protected"] for s in lib.list_suites()] == [True]
