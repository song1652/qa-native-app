import importlib.util
from pathlib import Path

SERVE_PATH = Path(__file__).parents[2] / "agents" / "dashboard" / "serve.py"
SPEC = importlib.util.spec_from_file_location("dashboard_serve", SERVE_PATH)
assert SPEC and SPEC.loader
serve = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(serve)


def test_dashboard_html_contains_core_shell():
    assert "<!DOCTYPE html>" in serve.DASHBOARD_HTML
    assert "QA CONTROL CENTER" in serve.DASHBOARD_HTML
    assert "/api/status" in serve.DASHBOARD_HTML
    assert "quick-mode') ? _quickPlatform : getPlatform()" in serve.DASHBOARD_HTML
    assert "Promise.all([refreshStatus(),refreshGenerated()])" in serve.DASHBOARD_HTML
    assert "function importPreviewStats()" in serve.DASHBOARD_HTML
    assert 'class="is-full-table"' in serve.DASHBOARD_HTML
    assert 'class="is-reset-btn"' in serve.DASHBOARD_HTML
    assert "_importPreviewRequest++;_importStudio=" in serve.DASHBOARD_HTML
    assert "is-stage-mapping" in serve.DASHBOARD_HTML
    assert "is-stage-preview" in serve.DASHBOARD_HTML
    assert "setImportPreviewFilter" in serve.DASHBOARD_HTML


def test_parse_failed_tcs_deduplicates_summary_entries():
    log = """
FAILED tests/generated/tc_login.py::test_login - AssertionError: denied
================ short test summary info ================
FAILED tests/generated/tc_login.py::test_login - AssertionError: denied
FAILED tests/generated/tc_search.py::test_search - TimeoutError
"""

    assert serve.parse_failed_tcs(log) == [
        {
            "tc": "tests/generated/tc_login.py::test_login",
            "error": "AssertionError: denied",
        },
        {
            "tc": "tests/generated/tc_search.py::test_search",
            "error": "TimeoutError",
        },
    ]


def test_list_generated_groups_test_cases_by_platform(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    (generated / "android" / "login").mkdir(parents=True)
    (generated / "ios" / "login").mkdir(parents=True)
    (generated / ".cache").mkdir()
    (generated / "android" / "login" / "tc_001.py").write_text("", encoding="utf-8")
    (generated / "ios" / "login" / "tc_002.py").write_text("", encoding="utf-8")
    (generated / ".cache" / "tc_hidden.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(serve, "GENERATED_DIR", generated)

    assert serve.list_generated() == [
        {"platform": "android", "files": ["login/tc_001.py"], "count": 1},
        {"platform": "ios", "files": ["login/tc_002.py"], "count": 1},
    ]


def test_list_generated_filters_selected_platform(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    for platform in ("android", "ios"):
        folder = generated / platform / "settings"
        folder.mkdir(parents=True)
        (folder / "tc_001.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(serve, "GENERATED_DIR", generated)

    assert serve.list_generated("ios") == [
        {"platform": "ios", "files": ["settings/tc_001.py"], "count": 1}
    ]


def test_report_metadata_uses_relative_names(tmp_path, monkeypatch):
    name = "report_02.html"
    reports = tmp_path / "reports"
    report = reports / Path(name)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(serve, "REPORTS_DIR", reports)

    result = serve.list_reports()

    assert result[0]["name"] == name
    assert result[0]["size"] == len("<html></html>")


def test_report_listing_ignores_nested_reports(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    nested = reports / "suite" / "report_01.html"
    nested.parent.mkdir(parents=True)
    nested.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(serve, "REPORTS_DIR", reports)

    assert serve.list_reports() == []


def test_import_files_include_metadata(tmp_path, monkeypatch):
    import_dir = tmp_path / "import"
    import_dir.mkdir()
    source = import_dir / "sample.xlsx"
    source.write_bytes(b"excel")
    monkeypatch.setattr(serve, "IMPORT_DIR", import_dir)

    files = serve.list_import_files()

    assert files[0]["name"] == "sample.xlsx"
    assert files[0]["size"] == 5
    assert files[0]["modified_at"]


def test_tc_folders_follow_selected_platform(tmp_path, monkeypatch):
    testcases = tmp_path / "testcases"
    for platform in ("android", "ios"):
        group = testcases / platform / "login"
        group.mkdir(parents=True)
        (group / "tc_001.md").write_text("", encoding="utf-8")
    monkeypatch.setattr(serve, "TESTCASES_DIR", testcases)

    assert serve.list_tc_folders("android") == ["android"]
    assert serve.list_tc_folders("ios") == ["ios"]
