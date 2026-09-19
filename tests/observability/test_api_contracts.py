"""HTTP contracts for observability artifact routes."""

import json
import sys
from pathlib import Path

from .runtime import ROOT, _should_keep


def _make_obs_app(runs_dir: Path):
    """테스트용 FastAPI 앱 — PROJECT_ROOT를 오버라이드한 observability 라우터."""
    sys.path.insert(0, str(ROOT / "agents" / "dashboard"))
    import importlib
    import types

    # 모듈을 신선하게 로드
    if "routes.observability" in sys.modules:
        del sys.modules["routes.observability"]

    obs_mod = importlib.import_module("routes.observability")
    # PROJECT_ROOT와 RUNS_DIR을 테스트 tmp_path로 교체
    obs_mod.PROJECT_ROOT = runs_dir.parent
    obs_mod.RUNS_DIR = runs_dir

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(obs_mod.router)
    return app


def test_manifest_not_found(tmp_path):
    """없는 run_id → 404."""
    from starlette.testclient import TestClient
    runs_dir = tmp_path / "state" / "runs"
    runs_dir.mkdir(parents=True)
    client = TestClient(_make_obs_app(runs_dir))
    r = client.get("/api/run_artifacts/run_android_20260101_000000_000")
    assert r.status_code == 404, r.text


def test_manifest_invalid_run_id(tmp_path):
    """정규식 불통과 run_id → 400."""
    from starlette.testclient import TestClient
    runs_dir = tmp_path / "state" / "runs"
    runs_dir.mkdir(parents=True)
    client = TestClient(_make_obs_app(runs_dir))
    r = client.get("/api/run_artifacts/invalid_id_format")
    assert r.status_code == 400, r.text


def test_manifest_valid(tmp_path):
    """manifest.json 생성 후 GET → 200 + JSON."""
    from starlette.testclient import TestClient
    runs_dir = tmp_path / "state" / "runs"
    run_id = "run_android_20260101_120000_001"
    art_dir = runs_dir / run_id / "artifacts"
    art_dir.mkdir(parents=True)
    manifest = {
        "run_id": run_id,
        "platform": "android",
        "mode": "emulator",
        "udid": "emulator-5554",
        "device_name": "Android Emulator",
        "keep_policy": "on_failure",
        "started_at": "2026-01-01T12:00:00",
        "finished_at": "2026-01-01T12:05:00",
        "entries": [],
    }
    (art_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    client = TestClient(_make_obs_app(runs_dir))
    r = client.get(f"/api/run_artifacts/{run_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("run_id") == run_id


def test_logcat_tail(tmp_path):
    """syslog 생성 후 tail=5 → 5줄 이하."""
    from starlette.testclient import TestClient
    runs_dir = tmp_path / "state" / "runs"
    run_id = "run_android_20260101_120001_002"
    slug = "tests_generated_android_tc_py__test_fn"
    art_dir = runs_dir / run_id / "artifacts"
    (art_dir / slug).mkdir(parents=True)
    lines = [f"line {i}" for i in range(100)]
    (art_dir / slug / "syslog.txt").write_text("\n".join(lines), encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "platform": "android",
        "keep_policy": "on_failure",
        "started_at": "2026-01-01T12:00:01",
        "finished_at": "2026-01-01T12:01:00",
        "entries": [{
            "nodeid": "tests/generated/android/tc.py::test_fn",
            "slug": slug,
            "outcome": "failed",
            "kept": True,
            "syslog": {
                "path": f"{slug}/syslog.txt",
                "bytes": 1000,
                "source": "adb_logcat",
                "truncated": False,
            },
            "video": None,
            "screenshot": None,
            "collect_errors": [],
        }],
    }
    (art_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    client = TestClient(_make_obs_app(runs_dir))
    r = client.get(
        f"/api/run_artifacts/{run_id}/logcat"
        "?nodeid=tests/generated/android/tc.py::test_fn&tail=5"
    )
    assert r.status_code == 200, r.text
    result_lines = [l for l in r.text.splitlines() if l]
    assert len(result_lines) <= 5


def test_video_not_found(tmp_path):
    """video 없는 nodeid → 404."""
    from starlette.testclient import TestClient
    runs_dir = tmp_path / "state" / "runs"
    run_id = "run_android_20260101_120002_003"
    art_dir = runs_dir / run_id / "artifacts"
    art_dir.mkdir(parents=True)
    manifest = {
        "run_id": run_id,
        "platform": "android",
        "keep_policy": "on_failure",
        "started_at": "2026-01-01T12:00:02",
        "finished_at": "2026-01-01T12:01:00",
        "entries": [],
    }
    (art_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    client = TestClient(_make_obs_app(runs_dir))
    r = client.get(
        f"/api/run_artifacts/{run_id}/video"
        "?nodeid=tests/generated/android/tc.py::test_fn"
    )
    assert r.status_code == 404, r.text


def test_run_list(tmp_path):
    """run 목록 GET → 200 + array."""
    from starlette.testclient import TestClient
    runs_dir = tmp_path / "state" / "runs"
    run_id = "run_android_20260101_120003_004"
    art_dir = runs_dir / run_id / "artifacts"
    art_dir.mkdir(parents=True)
    manifest = {
        "run_id": run_id,
        "platform": "android",
        "mode": "emulator",
        "udid": "emulator-5554",
        "device_name": "Android Emulator",
        "keep_policy": "on_failure",
        "started_at": "2026-01-01T12:00:03",
        "finished_at": "2026-01-01T12:05:00",
        "entries": [],
    }
    (art_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    client = TestClient(_make_obs_app(runs_dir))
    r = client.get("/api/run_artifacts")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "runs" in data
    assert isinstance(data["runs"], list)
    found = any(x["run_id"] == run_id for x in data["runs"])
    assert found, f"{run_id} not found in {data['runs']}"


def test_should_keep_policy():
    """_should_keep 함수 유닛 테스트."""
    # always: 항상 보존
    assert _should_keep("always", "passed") is True
    assert _should_keep("always", "failed") is True
    # never: 항상 미보존
    assert _should_keep("never", "passed") is False
    assert _should_keep("never", "failed") is False
    # on_failure 기본: 실패만 보존
    assert _should_keep("on_failure", "passed") is False
    assert _should_keep("on_failure", "failed") is True
    assert _should_keep("on_failure", "error") is True
    # on_failure + 재시도 발생: 통과해도 보존
    assert _should_keep("on_failure", "passed", attempt_count=2) is True
    assert _should_keep("on_failure", "passed", attempt_count=3) is True
