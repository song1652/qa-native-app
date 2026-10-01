from agents.dashboard.routes.pipeline import _pipeline_steps, _tc_folder_args
from agents.dashboard.shared import SCRIPT_MAP


def test_pipeline_scopes_generation_and_execution_to_selected_group():
    assert _tc_folder_args("generate", "android", "location") == [
        "--tc-dir", "android/location"
    ]
    assert _tc_folder_args("execute", "android", "location") == [
        "--tc-dir", "location"
    ]
    assert _tc_folder_args("lint", "android", "location") == []


def test_tc_studio_pipeline_starts_from_exported_markdown():
    assert _pipeline_steps(from_tc_studio=True) == ["generate", "lint", "execute"]
    assert _pipeline_steps(from_tc_studio=False) == ["analyze", "generate", "lint", "execute"]


def test_lint_step_reports_selected_platform():
    assert SCRIPT_MAP["lint"][1] == ["--platform", "{platform}"]
