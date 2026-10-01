from __future__ import annotations

from fastapi.testclient import TestClient
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import _paths
import _tc_library as lib
from _tc_model import new_case
from agents.dashboard.serve import app
from tests.unit.tc_library.test_tc_platform_results import _workbook
from tests.unit.tc_library.conftest import fake_claude  # noqa: F401
import openpyxl


def test_blank_starter_is_explicit_and_ready_for_authoring(tmp_path, monkeypatch):
    monkeypatch.setattr(_paths, "TC_LIBRARY_DIR", tmp_path / "library")
    client = TestClient(app)
    assert client.get("/api/tc-library").json()["suites"] == []

    started = client.post("/api/tc-library/starter")
    assert started.status_code == 201
    assert started.json()["suite"] == "기본양식"
    assert client.post("/api/tc-library/starter").status_code == 200
    suites = client.get("/api/tc-library").json()["suites"]
    assert len(suites) == 1
    assert suites[0]["sheets"] == ["테스트케이스"]
    assert suites[0]["count"] == 0
    assert suites[0]["kind"] == "app"
    assert client.post("/api/tc-library/기본양식/branches", json={
        "sheet": "테스트케이스", "path": ["로그인", "", ""]}).status_code == 200


def test_import_and_mismatch_filter_use_app_library(tmp_path, monkeypatch):
    monkeypatch.setattr(_paths, "TC_LIBRARY_DIR", tmp_path / "library")
    client = TestClient(app)
    source = _workbook(tmp_path / "cases.xlsx", True)
    preview = client.post("/api/tc-library/import/preview?filename=cases.xlsx", content=source.read_bytes())
    assert preview.status_code == 200
    body = preview.json()
    imported = client.post("/api/tc-library/import", json={"preview_id": body["preview_id"],
        "suite": "앱", "sheets": ["로그인"], "prefixes": {"로그인": "APP"}})
    assert imported.status_code == 200
    suites = client.get("/api/tc-library").json()["suites"]
    assert suites[0]["kind"] == "app"
    filtered = client.get("/api/tc-library/앱?mismatch=1").json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["results"] == {"android": "pass", "ios": "fail"}


def test_empty_app_workbook_keeps_platform_suite_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(_paths, "TC_LIBRARY_DIR", tmp_path / "library")
    source = _workbook(tmp_path / "empty.xlsx", False)
    book = openpyxl.load_workbook(source)
    sheet = book.active
    sheet.delete_rows(2, 2)
    book.save(source)
    book.close()
    client = TestClient(app)
    preview = client.post("/api/tc-library/import/preview?filename=empty.xlsx", content=source.read_bytes())
    assert preview.status_code == 200
    imported = client.post("/api/tc-library/import", json={"preview_id": preview.json()["preview_id"],
        "suite": "빈앱", "sheets": ["로그인"], "prefixes": {"로그인": "APP"}})
    assert imported.status_code == 200
    assert client.get("/api/tc-library").json()["suites"][0]["kind"] == "app"


def test_mapping_profile_and_md_preview_are_available(tmp_path, monkeypatch):
    monkeypatch.setattr(_paths, "TC_LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(_paths, "TESTCASES_DIR", tmp_path / "testcases")
    monkeypatch.setattr(_paths, "IMPORT_PROFILES_PATH", tmp_path / "mapping_profiles.json", raising=False)
    client = TestClient(app)
    response = client.post("/api/tc-library/import/mapping-profiles", json={"name": "양식", "mapping": {
        "header_row": 1, "columns": {"feature": "B", "steps": "C", "expected": "D"}}})
    assert response.status_code == 201
    assert client.get("/api/tc-library/import/mapping-profiles").json()["profiles"][0]["name"] == "양식"
    case = new_case(case_id="APP_0001", sheet="로그인", path=["로그인", "", ""], feature="성공",
                    steps=["누르기"], expected="표시", priority="P1", status="approved", platforms=["ios"])
    lib.import_cases("앱", ["로그인"], [case], "t")
    mapped = client.put("/api/tc-library/앱/md-groups", json={"path": ["로그인", "로그인"],
        "group": "login", "code": "LOG"})
    assert mapped.status_code == 200
    preview = client.post("/api/tc-library/앱/export/md").json()
    assert preview["rows"][0]["file"].startswith("ios/login/")
    committed = client.post(f"/api/tc-library/앱/md-exports/{preview['run_id']}/commit", json={"skip": []})
    assert committed.status_code == 200
    assert len(list((tmp_path / "testcases").rglob("*.md"))) == 1
    rolled = client.post(f"/api/tc-library/앱/md-exports/{preview['run_id']}/rollback")
    assert rolled.status_code == 200
    assert not list((tmp_path / "testcases").rglob("*.md"))


def test_authoring_source_and_actor_header(tmp_path, monkeypatch):
    monkeypatch.setattr(_paths, "TC_LIBRARY_DIR", tmp_path / "library")
    client = TestClient(app)
    bundle = client.post("/api/tc-library/sources").json()["bundle_id"]
    source = client.post(f"/api/tc-library/sources/{bundle}/paste", json={"text": "# 로그인\n버튼을 누른다"})
    assert source.status_code == 201
    assert client.get(f"/api/tc-library/sources/{bundle}").json()["sources"]
    case = new_case(case_id="APP_0001", sheet="로그인", path=["로그인", "", ""], feature="성공")
    lib.import_cases("앱", ["로그인"], [case], "seed")
    changed = client.patch("/api/tc-library/앱/cases/APP_0001", json={"rev": 1, "note": "확인"},
                           headers={"X-TC-Actor": "tester"})
    assert changed.status_code == 200
    history = client.get("/api/tc-library/앱/cases/APP_0001/history").json()
    assert any(row.get("actor") == "tester" for row in history["history"])


def test_tc_api_rejects_foreign_origin_and_oversized_request(tmp_path, monkeypatch):
    monkeypatch.setattr(_paths, "TC_LIBRARY_DIR", tmp_path / "library")
    client = TestClient(app)
    assert client.get("/api/tc-library", headers={"Origin": "https://outside.example"}).status_code == 403
    assert client.post("/api/tc-library/import/preview", content=b"x" * (25 * 1024 * 1024 + 1)).status_code == 413


def test_authoring_job_creates_ios_draft_through_api(tmp_path, monkeypatch, fake_claude):
    monkeypatch.setattr(_paths, "TC_LIBRARY_DIR", tmp_path / "library")
    lib.import_cases("앱", ["로그인"], [], "seed")
    client = TestClient(app)
    bundle = client.post("/api/tc-library/sources").json()["bundle_id"]
    added = client.post(f"/api/tc-library/sources/{bundle}/paste", json={
        "text": "# 로그인\n\n## 비밀번호\n\n비밀번호를 입력하면 홈 화면으로 이동한다."})
    assert added.status_code == 201
    started = client.post("/api/tc-library/앱/jobs", json={"bundle_id": bundle, "sheet": "로그인",
        "path": ["로그인"], "profile": "기본", "platforms": ["ios"]})
    assert started.status_code == 202
    job_id = started.json()["job"]["job_id"]
    for _ in range(100):
        job = client.get(f"/api/tc-library/jobs/{job_id}").json()["job"]
        if job["status"] not in ("queued", "fetching", "drafting", "validating"):
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    drafts = client.get("/api/tc-library/앱?status=draft").json()["items"]
    assert drafts and all(case["platforms"] == ["ios"] for case in drafts)


def test_library_edit_conflict_xlsx_export_and_import_rollback(tmp_path, monkeypatch):
    monkeypatch.setattr(_paths, "TC_LIBRARY_DIR", tmp_path / "library")
    client = TestClient(app)
    source = _workbook(tmp_path / "cases.xlsx", True)
    preview = client.post("/api/tc-library/import/preview?filename=cases.xlsx", content=source.read_bytes()).json()
    imported = client.post("/api/tc-library/import", json={"preview_id": preview["preview_id"],
        "suite": "앱", "sheets": ["로그인"], "prefixes": {"로그인": "APP"}}).json()
    case = client.get("/api/tc-library/앱").json()["items"][0]
    path = f"/api/tc-library/앱/cases/{case['case_id']}"
    updated = client.patch(path, json={"rev": case["rev"], "feature": "수정된 경우"})
    assert updated.status_code == 200
    conflict = client.patch(path, json={"rev": case["rev"], "feature": "오래된 변경"})
    assert conflict.status_code == 409 and conflict.json()["code"] == "REV_CONFLICT"
    exported = client.post("/api/tc-library/앱/export/xlsx", json={"scope": "all"})
    assert exported.status_code == 200
    assert not [check for check in exported.json()["checks"] if check["level"] == "error"]
    downloaded = client.get(f"/api/tc-library/exports/{exported.json()['export_id']}/download")
    assert downloaded.status_code == 200 and downloaded.content.startswith(b"PK")
    rollback = client.post(f"/api/tc-library/import/runs/{imported['run_id']}/rollback")
    assert rollback.status_code == 409 and rollback.json()["code"] == "SUITE_CHANGED"
