import importlib.util
import sys
from pathlib import Path

# ── dashboard.html 직접 읽기 ─────────────────────────────────────
_DASHBOARD_DIR = Path(__file__).parents[2] / "agents" / "dashboard"
_DASHBOARD_HTML_PATH = _DASHBOARD_DIR / "dashboard.html"
sys.path.insert(0, str(_DASHBOARD_DIR))

# state.py에서 유틸리티 함수 import
from utils.state import (  # noqa: E402
    parse_failed_tcs,
    list_generated,
    list_reports,
    list_import_files,
    list_tc_folders,
)

DASHBOARD_HTML = _DASHBOARD_HTML_PATH.read_text(encoding="utf-8")


# ── 하위호환: serve 네임스페이스 (utils.state 함수를 re-export) ──
class _ServeCompat:
    DASHBOARD_HTML = DASHBOARD_HTML

    @staticmethod
    def parse_failed_tcs(log_text):
        return parse_failed_tcs(log_text)

    @staticmethod
    def list_generated(platform=None):
        return list_generated(platform)

    @staticmethod
    def list_reports():
        return list_reports()

    @staticmethod
    def list_import_files():
        return list_import_files()

    @staticmethod
    def list_tc_folders(platform=None):
        return list_tc_folders(platform)


serve = _ServeCompat()


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
    import utils.state as state_mod
    generated = tmp_path / "generated"
    (generated / "android" / "login").mkdir(parents=True)
    (generated / "ios" / "login").mkdir(parents=True)
    (generated / ".cache").mkdir()
    (generated / "android" / "login" / "tc_001.py").write_text("", encoding="utf-8")
    (generated / "ios" / "login" / "tc_002.py").write_text("", encoding="utf-8")
    (generated / ".cache" / "tc_hidden.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(state_mod, "GENERATED_DIR", generated)

    assert list_generated() == [
        {"platform": "android", "files": ["login/tc_001.py"], "count": 1},
        {"platform": "ios", "files": ["login/tc_002.py"], "count": 1},
    ]


def test_list_generated_filters_selected_platform(tmp_path, monkeypatch):
    import utils.state as state_mod
    generated = tmp_path / "generated"
    for platform in ("android", "ios"):
        folder = generated / platform / "settings"
        folder.mkdir(parents=True)
        (folder / "tc_001.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(state_mod, "GENERATED_DIR", generated)

    assert list_generated("ios") == [
        {"platform": "ios", "files": ["settings/tc_001.py"], "count": 1}
    ]


def test_report_metadata_uses_relative_names(tmp_path, monkeypatch):
    import utils.state as state_mod
    name = "report_02.html"
    reports = tmp_path / "reports"
    report = reports / Path(name)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(state_mod, "REPORTS_DIR", reports)

    result = list_reports()

    assert result[0]["name"] == name
    assert result[0]["size"] == len("<html></html>")


def test_report_listing_ignores_nested_reports(tmp_path, monkeypatch):
    import utils.state as state_mod
    reports = tmp_path / "reports"
    nested = reports / "suite" / "report_01.html"
    nested.parent.mkdir(parents=True)
    nested.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(state_mod, "REPORTS_DIR", reports)

    assert list_reports() == []


def test_import_files_include_metadata(tmp_path, monkeypatch):
    import utils.state as state_mod
    import_dir = tmp_path / "import"
    import_dir.mkdir()
    source = import_dir / "sample.xlsx"
    source.write_bytes(b"excel")
    monkeypatch.setattr(state_mod, "IMPORT_DIR", import_dir)

    files = list_import_files()

    assert files[0]["name"] == "sample.xlsx"
    assert files[0]["size"] == 5
    assert files[0]["modified_at"]


def test_tc_folders_follow_selected_platform(tmp_path, monkeypatch):
    import utils.state as state_mod
    testcases = tmp_path / "testcases"
    for platform in ("android", "ios"):
        group = testcases / platform / "login"
        group.mkdir(parents=True)
        (group / "tc_001.md").write_text("", encoding="utf-8")
    monkeypatch.setattr(state_mod, "TESTCASES_DIR", testcases)

    assert list_tc_folders("android") == ["android"]
    assert list_tc_folders("ios") == ["ios"]
