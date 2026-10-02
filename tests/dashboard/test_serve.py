import importlib.util
import sys
from pathlib import Path

from tests.dashboard.dashboard_source import load_dashboard_source

# ── dashboard.html 직접 읽기 ─────────────────────────────────────
_DASHBOARD_DIR = Path(__file__).parents[2] / "agents" / "dashboard"
_DASHBOARD_HTML_PATH = _DASHBOARD_DIR / "dashboard.html"
sys.path.insert(0, str(_DASHBOARD_DIR))

# state.py에서 유틸리티 함수 import
from utils.state import (  # noqa: E402
    list_generated,
    list_reports,
    list_tc_folders,
)

DASHBOARD_HTML = load_dashboard_source()


# ── 하위호환: serve 네임스페이스 (utils.state 함수를 re-export) ──
class _ServeCompat:
    DASHBOARD_HTML = DASHBOARD_HTML

    @staticmethod
    def list_generated(platform=None):
        return list_generated(platform)

    @staticmethod
    def list_reports():
        return list_reports()

    @staticmethod
    def list_tc_folders(platform=None):
        return list_tc_folders(platform)


serve = _ServeCompat()


def test_dashboard_html_contains_core_shell():
    assert "<!DOCTYPE html>" in serve.DASHBOARD_HTML
    assert "QA Control Center" in serve.DASHBOARD_HTML
    assert "/api/status" in serve.DASHBOARD_HTML
    assert "quick-mode') ? _quickPlatform : getPlatform()" in serve.DASHBOARD_HTML
    assert "Promise.all([refreshStatus(),refreshGenerated()])" in serve.DASHBOARD_HTML
    assert "/static/import-studio.js" not in serve.DASHBOARD_HTML  # 엑셀 가져오기는 TC 스튜디오로 통합
    assert "analyze: null, generate:null" in serve.DASHBOARD_HTML
    assert '<span>TC 스튜디오</span>' in serve.DASHBOARD_HTML


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


def test_tc_folders_follow_selected_platform(tmp_path, monkeypatch):
    import utils.state as state_mod
    testcases = tmp_path / "testcases"
    for platform in ("android", "ios"):
        group = testcases / platform / "login"
        group.mkdir(parents=True)
        (group / "tc_001.md").write_text("", encoding="utf-8")
    monkeypatch.setattr(state_mod, "TESTCASES_DIR", testcases)

    assert list_tc_folders("android") == ["login"]
    assert list_tc_folders("ios") == ["login"]


def test_tc_folders_list_only_groups_with_cases(tmp_path, monkeypatch):
    import utils.state as state_mod
    testcases = tmp_path / "testcases"
    for group in ("location", "settings"):
        folder = testcases / "android" / group
        folder.mkdir(parents=True)
        (folder / "tc_001.md").write_text("", encoding="utf-8")
    (testcases / "android" / "empty").mkdir()
    monkeypatch.setattr(state_mod, "TESTCASES_DIR", testcases)

    assert list_tc_folders("android") == ["location", "settings"]


def test_tc_folders_include_platform_root_cases(tmp_path, monkeypatch):
    import utils.state as state_mod
    root = tmp_path / "testcases" / "android"
    (root / "group").mkdir(parents=True)
    (root / "tc_root.md").write_text("", encoding="utf-8")
    (root / "group" / "tc_child.md").write_text("", encoding="utf-8")
    monkeypatch.setattr(state_mod, "TESTCASES_DIR", tmp_path / "testcases")

    assert list_tc_folders("android") == ["__root__", "group"]
