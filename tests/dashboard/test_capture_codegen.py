"""Contracts for Capture Studio's actions-to-pytest generator."""
from datetime import datetime
from pathlib import Path
import sys

import pytest


DASHBOARD = Path(__file__).parents[2] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

from utils.capture_codegen import (  # noqa: E402
    CaptureCodegenValidationError,
    generate_test_from_actions,
)


@pytest.mark.parametrize(
    ("platform", "identity"),
    [
        ("android", {"app_pkg": "com.android.settings", "app_activity": ".Settings"}),
        ("ios", {"bundle_id": "com.apple.Preferences"}),
    ],
)
def test_generate_test_from_actions_writes_compilable_pytest(
    tmp_path, platform, identity
):
    body = {
        "tc_id": f"tc_{platform}_generated",
        "title": "Generated smoke test",
        "platform": platform,
        "tc_group": "capture_codegen",
        "actions": [{"type": "wait", "wait_seconds": 0}],
        **identity,
    }

    result = generate_test_from_actions(
        body,
        {},
        tmp_path,
        generated_at=datetime(2026, 9, 18, 12, 0),
    )

    output_path = tmp_path / result["file"]
    assert result["ok"] is True
    assert output_path.read_text(encoding="utf-8") == result["code"]
    assert "자동 생성: Capture Studio (2026-09-18 12:00)" in result["code"]
    compile(result["code"], str(output_path), "exec")


def test_generate_test_from_actions_rejects_invalid_platform(tmp_path):
    with pytest.raises(
        CaptureCodegenValidationError,
        match="tc_id와 platform이 필요합니다",
    ):
        generate_test_from_actions(
            {"tc_id": "tc_invalid", "platform": "windows"},
            {},
            tmp_path,
        )


def test_generate_test_from_actions_rejects_empty_executable_actions(tmp_path):
    with pytest.raises(
        CaptureCodegenValidationError,
        match="실행 가능한 액션이 하나 이상 필요합니다",
    ):
        generate_test_from_actions(
            {
                "tc_id": "tc_empty",
                "platform": "android",
                "actions": [],
            },
            {},
            tmp_path,
        )

    assert not (tmp_path / "tests" / "generated").exists()
