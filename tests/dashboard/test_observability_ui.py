from pathlib import Path
import importlib.util

from tests.dashboard.dashboard_source import load_dashboard_source


HTML = load_dashboard_source()


def test_evidence_panel_supports_attempt_switching():
    assert "function _evSelectAttempt(" in HTML
    assert "entry.attempts" in HTML
    assert "attempt=" in HTML


def test_evidence_panel_maps_collection_errors_to_korean_guidance():
    assert "video_invalid" in HTML
    assert "video_pull_failed" in HTML
    assert "ios_real_device_unsupported" in HTML
    assert "ios_log_bundle_id_missing" in HTML


def test_log_toolbar_has_required_presets():
    assert "AndroidRuntime" in HTML
    assert "manifest.app_id" in HTML
    assert "FATAL" in HTML
    assert "E/" in HTML


def _load_report_html_module():
    path = Path(__file__).parents[2] / "scripts" / "report_html.py"
    spec = importlib.util.spec_from_file_location("report_html_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_html_report_has_no_artifact_link():
    """관측 아티팩트 링크는 사용자 요청으로 제거되었다 (포트 불일치, 케이스별 증거로 대체)."""
    module = _load_report_html_module()

    rendered = module.build_report([], {"passed": 0, "failed": 0}, "2026-09-17")

    assert "관측 아티팩트" not in rendered


def test_html_report_embeds_per_case_screenshot_and_video_urls():
    """report_html.py는 관측성 manifest에서 얻은 screenshot_url/video_url을
    case-detail에 직접 img/video 태그로 임베드한다 (레거시 file:// 경로 대체)."""
    module = _load_report_html_module()

    rendered = module.case_row(
        {
            "title": "TC: 예시",
            "precondition": [], "steps": [], "expected": "",
            "error": "AssertionError: boom",
            "screenshot_url": "/api/run_artifacts/run_android_1/screenshot?nodeid=x&attempt=1",
            "video": "",
            "video_url": "/api/run_artifacts/run_android_1/video?nodeid=x&attempt=1",
        },
        "grp_0",
        "failed",
    )

    assert 'src="/api/run_artifacts/run_android_1/screenshot?nodeid=x&amp;attempt=1"' in rendered
    assert 'src="/api/run_artifacts/run_android_1/video?nodeid=x&amp;attempt=1"' in rendered
