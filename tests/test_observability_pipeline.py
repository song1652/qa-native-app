import importlib
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "agents" / "dashboard"))


def _pipeline():
    return importlib.import_module("routes.pipeline")


def test_build_run_env_does_not_mutate_parent_environment(monkeypatch):
    pipeline = _pipeline()
    monkeypatch.setenv("QA_OBS_KEEP", "parent-value")
    before = dict(os.environ)

    child = pipeline._build_run_env(
        "run_android_20260917_120000_001",
        "android",
        "always",
        "emulator",
        "emulator-5554",
    )

    assert dict(os.environ) == before
    assert child["QA_RUN_ID"] == "run_android_20260917_120000_001"
    assert child["QA_PLATFORM"] == "android"
    assert child["QA_OBS_KEEP"] == "always"
    assert child["DEVICE_MODE"] == "emulator"
    assert child["DEVICE_UDID"] == "emulator-5554"


def test_build_run_env_defaults_invalid_policy_to_on_failure():
    pipeline = _pipeline()

    child = pipeline._build_run_env(
        "run_ios_20260917_120000_002", "ios", "invalid", "simulator", "udid-1"
    )

    assert child["QA_OBS_KEEP"] == "on_failure"


def test_execute_device_args_are_forwarded_for_every_execute_path():
    pipeline = _pipeline()

    args = pipeline._device_execute_args("ios", "simulator", "udid-1")

    assert args == ["--mode", "simulator", "--udid", "udid-1"]


def test_quick_run_without_healing_disables_pytest_reruns():
    pipeline = _pipeline()

    args = pipeline._quick_run_execute_args(
        "android", test_folder="obs_demo", test_file="", heal=False
    )

    assert args[-3:] == ["--tc-dir", "obs_demo", "--no-rerun"]


def test_quick_run_with_healing_keeps_pytest_reruns_enabled():
    pipeline = _pipeline()

    args = pipeline._quick_run_execute_args(
        "ios", test_folder="", test_file="settings/tc_wifi.py", heal=True
    )

    assert args[-2:] == ["--test-file", "settings/tc_wifi.py"]
    assert "--no-rerun" not in args


def test_run_summary_reads_latest_attempts(tmp_path, monkeypatch):
    pipeline = _pipeline()
    run_id = "run_android_20260917_120000_003"
    artifact_dir = tmp_path / "state" / "runs" / run_id / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "manifest.json").write_text(json.dumps({
        "entries": [
            {"attempts": [{"n": 1, "outcome": "failed", "video": {"path": "x"}, "syslog": None}]},
            {"attempts": [{"n": 1, "outcome": "passed", "video": None, "syslog": {"path": "y"}}]},
        ]
    }), encoding="utf-8")
    monkeypatch.setattr(pipeline, "PROJECT_ROOT", tmp_path)

    summary = pipeline._read_run_summary(run_id)

    assert summary["failed"] == 1
    assert summary["with_video"] == 1
    assert summary["with_syslog"] == 1
    assert summary["size_bytes"] > 0
