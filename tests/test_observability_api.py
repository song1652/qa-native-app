import importlib
import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "agents" / "dashboard"))


def _client(runs_dir: Path) -> TestClient:
    module = importlib.import_module("routes.observability")
    module.RUNS_DIR = runs_dir
    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app)


def _write_manifest(runs_dir: Path, run_id: str, entries: list, finished_at="2026-09-17T12:01:00"):
    artifact_dir = runs_dir / run_id / "artifacts"
    artifact_dir.mkdir(parents=True)
    manifest = {
        "run_id": run_id,
        "platform": "android",
        "mode": "emulator",
        "udid": "emulator-5554",
        "device_name": "Android Emulator",
        "keep_policy": "on_failure",
        "started_at": "2026-09-17T12:00:00",
        "finished_at": finished_at,
        "entries": entries,
    }
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return artifact_dir


def test_canonical_runs_endpoint_lists_runs(tmp_path):
    runs = tmp_path / "runs"
    run_id = "run_android_20260917_120000_001"
    _write_manifest(runs, run_id, [])

    response = _client(runs).get("/api/runs")

    assert response.status_code == 200
    assert response.json()["runs"][0]["run_id"] == run_id


def test_legacy_entry_is_normalized_to_one_attempt(tmp_path):
    runs = tmp_path / "runs"
    run_id = "run_android_20260917_120000_002"
    legacy = {
        "nodeid": "tests/generated/android/a.py::test_a",
        "slug": "a",
        "outcome": "failed",
        "attempt_count": 1,
        "kept": True,
        "video": None,
        "syslog": None,
        "screenshot": None,
        "collect_errors": ["video_pull_failed"],
    }
    _write_manifest(runs, run_id, [legacy])

    data = _client(runs).get(f"/api/run_artifacts/{run_id}").json()

    assert data["entries"][0]["attempts"][0]["n"] == 1
    assert data["entries"][0]["attempts"][0]["outcome"] == "failed"


def test_video_endpoint_selects_requested_attempt(tmp_path):
    runs = tmp_path / "runs"
    run_id = "run_android_20260917_120000_003"
    entries = [{
        "nodeid": "tests/generated/android/a.py::test_a",
        "slug": "a",
        "outcome": "failed",
        "attempt_count": 2,
        "attempts": [
            {"n": 1, "kept": True, "video": {"path": "a/attempt1/video.mp4"}},
            {"n": 2, "kept": True, "video": {"path": "a/attempt2/video.mp4"}},
        ],
    }]
    artifact_dir = _write_manifest(runs, run_id, entries)
    (artifact_dir / "a" / "attempt1").mkdir(parents=True)
    (artifact_dir / "a" / "attempt2").mkdir(parents=True)
    (artifact_dir / "a" / "attempt1" / "video.mp4").write_bytes(b"first")
    (artifact_dir / "a" / "attempt2" / "video.mp4").write_bytes(b"second")

    response = _client(runs).get(
        f"/api/run_artifacts/{run_id}/video",
        params={"nodeid": entries[0]["nodeid"], "attempt": 1},
    )

    assert response.status_code == 200
    assert response.content == b"first"


def test_internal_screenshot_is_exposed_through_artifact_endpoint(tmp_path):
    runs = tmp_path / "runs"
    run_id = "run_ios_20260917_120000_004"
    nodeid = "tests/generated/ios/a.py::test_a"
    entries = [{
        "nodeid": nodeid,
        "slug": "a",
        "outcome": "passed",
        "attempts": [{
            "n": 1,
            "outcome": "passed",
            "kept": True,
            "screenshot": {"path": "a/attempt1/screenshot.png", "bytes": 12},
        }],
    }]
    artifact_dir = _write_manifest(runs, run_id, entries)
    shot = artifact_dir / "a" / "attempt1" / "screenshot.png"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"\x89PNG\r\n\x1a\nshot")

    manifest_response = _client(runs).get(f"/api/run_artifacts/{run_id}")
    attempt = manifest_response.json()["entries"][0]["attempts"][0]
    response = _client(runs).get(attempt["screenshot_url"])

    assert attempt["screenshot_url"].startswith(
        f"/api/run_artifacts/{run_id}/screenshot?"
    )
    assert response.status_code == 200
    assert response.content == b"\x89PNG\r\n\x1a\nshot"


def test_active_run_is_never_manually_deleted_even_when_old(tmp_path):
    runs = tmp_path / "runs"
    run_id = "run_android_20200101_000000_001"
    _write_manifest(runs, run_id, [], finished_at=None)

    response = _client(runs).delete(f"/api/run_artifacts/{run_id}")

    assert response.status_code == 409
    assert (runs / run_id).exists()
