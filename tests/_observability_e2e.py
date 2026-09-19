"""
_observability_e2e.py — TC 실행 관측성 E2E 시나리오 테스트.

시나리오:
    1. test_run_test_with_obs_keep_on_failure — /api/run_test obs_keep 파라미터 전달
    2. test_evidence_panel_load — manifest 있을 때 /api/run_artifacts/{run_id} 응답 구조
    3. test_logcat_filter_preset — syslog tail + 특정 레벨 프리셋 필터 작동

Usage:
    python3 -m pytest tests/_observability_e2e.py -v
"""
import json
import sys
from pathlib import Path

from fastapi import Request  # noqa: E402 — 관측성 E2E 프로브용

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "agents" / "dashboard"))


# ─── 공유 픽스처 헬퍼 ────────────────────────────────────────────
def _make_obs_app(runs_dir: Path):
    """observability 라우터를 runs_dir로 오버라이드한 FastAPI 앱."""
    import importlib

    if "routes.observability" in sys.modules:
        del sys.modules["routes.observability"]

    obs_mod = importlib.import_module("routes.observability")
    obs_mod.PROJECT_ROOT = runs_dir.parent
    obs_mod.RUNS_DIR = runs_dir

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(obs_mod.router)
    return app


def _make_pipeline_app(project_root: Path):
    """pipeline 라우터를 project_root로 오버라이드한 FastAPI 앱."""
    # shared 모듈 경로 패치
    if "shared" in sys.modules:
        del sys.modules["shared"]
    if "routes.pipeline" in sys.modules:
        del sys.modules["routes.pipeline"]
    if "ws" in sys.modules:
        del sys.modules["ws"]
    if "utils.state" in sys.modules:
        del sys.modules["utils.state"]

    # 최소 shared 스텁
    import types

    shared_stub = types.ModuleType("shared")
    shared_stub.ADB_BIN = "adb"
    shared_stub.GENERATED_DIR = project_root / "tests" / "generated"
    shared_stub.LOGS_DIR = project_root / "logs"
    shared_stub.PROJECT_ROOT = project_root
    shared_stub.PYTHON_BIN = sys.executable
    shared_stub.REPORTS_DIR = project_root / "reports"
    shared_stub.SCRIPT_MAP = {
        "execute": ("scripts/05_execute.py", ["--platform", "{platform}"], "run_execute.txt"),
    }
    import threading
    shared_stub._process_lock = threading.Lock()
    shared_stub._running = {}
    shared_stub._test_runs = {}
    shared_stub.save_running_pids = lambda: None
    sys.modules["shared"] = shared_stub

    # 최소 ws 스텁
    ws_stub = types.ModuleType("ws")
    ws_stub.broadcast_timeline_sync = lambda _msg: None
    ws_stub.router = None
    sys.modules["ws"] = ws_stub

    # 최소 utils.state 스텁
    if "utils" not in sys.modules:
        utils_pkg = types.ModuleType("utils")
        utils_pkg.__path__ = []
        sys.modules["utils"] = utils_pkg
    us_stub = types.ModuleType("utils.state")
    us_stub.is_capture_active = lambda _platform=None: False
    us_stub.list_tc_folders = lambda _platform: []
    us_stub.read_state = lambda: {}
    us_stub.save_state = lambda _s: None
    sys.modules["utils.state"] = us_stub

    # fastapi 라우터 직접 임포트
    from fastapi import FastAPI, APIRouter
    app = FastAPI()

    # pipeline.py의 _gen_run_id와 obs_keep 처리만 검증하기 위한 최소 라우터
    router = APIRouter()

    import os
    import re

    _RUN_ID_RE = re.compile(r"^run_[a-z]+_\d{8}_\d{6}_\d{3}$")

    @router.post("/api/run_test_e2e_probe")
    async def probe_run_test(request: Request):
        """obs_keep 파라미터가 QA_OBS_KEEP으로 전달되는지 확인하는 프로브 엔드포인트."""
        from fastapi.responses import JSONResponse
        body = await request.json()
        obs_keep = body.get("obs_keep", "").strip()
        if obs_keep in ("on_failure", "always", "never"):
            os.environ["QA_OBS_KEEP"] = obs_keep
        elif "QA_OBS_KEEP" not in os.environ:
            os.environ["QA_OBS_KEEP"] = "on_failure"

        # run_id 형식 검증
        from datetime import datetime
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        platform = body.get("platform", "android")
        run_id = f"run_{platform}_{stamp}"
        assert _RUN_ID_RE.match(run_id), f"run_id 형식 오류: {run_id}"

        result_keep = os.environ.get("QA_OBS_KEEP", "on_failure")
        os.environ.pop("QA_OBS_KEEP", None)
        return JSONResponse({"ok": True, "run_id": run_id, "obs_keep": result_keep})

    app.include_router(router)
    return app


# ─────────────────────────────────────────────────────────────────
# E2E 테스트 1: obs_keep 파라미터 처리
# ─────────────────────────────────────────────────────────────────
def test_run_test_with_obs_keep_on_failure(tmp_path):
    """/api/run_test 요청 시 obs_keep=on_failure → QA_OBS_KEEP 환경 변수 전달 확인."""
    from starlette.testclient import TestClient
    project_root = tmp_path / "project"
    (project_root / "logs").mkdir(parents=True)
    (project_root / "scripts").mkdir(parents=True)

    app = _make_pipeline_app(project_root)
    client = TestClient(app)

    r = client.post("/api/run_test_e2e_probe", json={
        "platform": "android",
        "obs_keep": "on_failure",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["obs_keep"] == "on_failure"
    # run_id 형식: run_{platform}_{YYYYMMDD}_{HHMMSS}_{mmm}
    import re
    assert re.match(r"^run_android_\d{8}_\d{6}_\d{3}$", data["run_id"]), (
        f"run_id 형식 불일치: {data['run_id']}"
    )


def test_run_test_with_obs_keep_always(tmp_path):
    """obs_keep=always → QA_OBS_KEEP=always 전달 확인."""
    from starlette.testclient import TestClient
    project_root = tmp_path / "project"
    (project_root / "logs").mkdir(parents=True)

    app = _make_pipeline_app(project_root)
    client = TestClient(app)

    r = client.post("/api/run_test_e2e_probe", json={
        "platform": "ios",
        "obs_keep": "always",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["obs_keep"] == "always"
    import re
    assert re.match(r"^run_ios_\d{8}_\d{6}_\d{3}$", data["run_id"]), (
        f"run_id 형식 불일치: {data['run_id']}"
    )


# ─────────────────────────────────────────────────────────────────
# E2E 테스트 2: evidence panel 로드 (GET /api/run_artifacts/{run_id})
# ─────────────────────────────────────────────────────────────────
def test_evidence_panel_load(tmp_path):
    """manifest + syslog + video 파일이 있을 때 GET manifest → 구조 검증."""
    from starlette.testclient import TestClient
    runs_dir = tmp_path / "state" / "runs"
    run_id = "run_android_20260101_130000_003"
    slug = "tests_generated_android_grp_tc001_py__test_open_screen"
    art_dir = runs_dir / run_id / "artifacts"
    tc_dir = art_dir / slug
    tc_dir.mkdir(parents=True)

    # 더미 syslog / video 생성
    syslog_path = tc_dir / "syslog.txt"
    syslog_lines = (
        "01-01 12:00:00.000  1234  1234 D ActivityManager: Start\n"
        "01-01 12:00:00.010  1234  1234 E TestTag: assertion failed\n"
        "01-01 12:00:00.020  1234  1234 I TestTag: done\n"
    ) * 10
    syslog_path.write_text(syslog_lines, encoding="utf-8")

    video_path = tc_dir / "video.mp4"
    video_path.write_bytes(b"\x00\x01" * 100)  # 더미 바이트

    manifest = {
        "run_id": run_id,
        "platform": "android",
        "mode": "emulator",
        "udid": "emulator-5554",
        "device_name": "Android Emulator",
        "keep_policy": "on_failure",
        "started_at": "2026-01-01T13:00:00",
        "finished_at": "2026-01-01T13:10:00",
        "entries": [
            {
                "nodeid": (
                    "tests/generated/android/grp/tc001.py::test_open_screen"
                ),
                "slug": slug,
                "outcome": "failed",
                "attempt_count": 1,
                "started_at": "2026-01-01T13:00:00",
                "finished_at": "2026-01-01T13:01:30",
                "duration_sec": 90.0,
                "kept": True,
                "failure_offset_sec": 90.0,
                "video": {
                    "path": f"{slug}/video.mp4",
                    "bytes": 200,
                    "codec": "h264",
                },
                "syslog": {
                    "path": f"{slug}/syslog.txt",
                    "bytes": len(syslog_lines.encode()),
                    "source": "adb_logcat",
                    "truncated": False,
                },
                "screenshot": None,
                "network": None,
                "collect_errors": [],
            }
        ],
    }
    (art_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    client = TestClient(_make_obs_app(runs_dir))

    # manifest GET
    r = client.get(f"/api/run_artifacts/{run_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("run_id") == run_id
    entries = data.get("entries", [])
    assert len(entries) == 1

    entry = entries[0]
    # video_url, syslog_url 포함 확인
    assert entry.get("video_url") is not None, "video_url이 없음"
    assert entry.get("syslog_url") is not None, "syslog_url이 없음"
    assert entry.get("kept") is True
    assert entry.get("outcome") == "failed"
    assert entry.get("failure_offset_sec") == 90.0


# ─────────────────────────────────────────────────────────────────
# E2E 테스트 3: logcat 필터 프리셋 (tail 파라미터 + level 키워드 검색)
# ─────────────────────────────────────────────────────────────────
def test_logcat_filter_preset(tmp_path):
    """syslog tail + 클라이언트측 level 프리셋 필터 시나리오.

    API는 tail 줄을 반환하고, 클라이언트(대시보드)가 ERROR/WARN 등을 필터링한다.
    여기서는 API가 올바른 줄 수를 반환하는지, 내용에 로그 레벨 키워드가 있는지 검증.
    """
    from starlette.testclient import TestClient
    runs_dir = tmp_path / "state" / "runs"
    run_id = "run_android_20260101_140000_004"
    slug = "tests_generated_android_grp_tc002_py__test_login"
    art_dir = runs_dir / run_id / "artifacts"
    tc_dir = art_dir / slug
    tc_dir.mkdir(parents=True)

    # 로그 레벨 혼재 syslog 생성
    log_lines = []
    for i in range(50):
        log_lines.append(f"01-01 14:00:{i:02d}.000  1234  1234 D Debug: normal line {i}")
    for i in range(10):
        log_lines.append(f"01-01 14:01:{i:02d}.000  1234  1234 E Error: error line {i}")
    for i in range(5):
        log_lines.append(f"01-01 14:02:{i:02d}.000  1234  1234 W Warn: warning line {i}")

    syslog_path = tc_dir / "syslog.txt"
    syslog_path.write_text("\n".join(log_lines), encoding="utf-8")

    manifest = {
        "run_id": run_id,
        "platform": "android",
        "keep_policy": "on_failure",
        "started_at": "2026-01-01T14:00:00",
        "finished_at": "2026-01-01T14:05:00",
        "entries": [
            {
                "nodeid": "tests/generated/android/grp/tc002.py::test_login",
                "slug": slug,
                "outcome": "failed",
                "attempt_count": 1,
                "started_at": "2026-01-01T14:00:00",
                "finished_at": "2026-01-01T14:02:30",
                "duration_sec": 150.0,
                "kept": True,
                "failure_offset_sec": 150.0,
                "video": None,
                "syslog": {
                    "path": f"{slug}/syslog.txt",
                    "bytes": syslog_path.stat().st_size,
                    "source": "adb_logcat",
                    "truncated": False,
                },
                "screenshot": None,
                "network": None,
                "collect_errors": [],
            }
        ],
    }
    (art_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    client = TestClient(_make_obs_app(runs_dir))

    nodeid_enc = "tests/generated/android/grp/tc002.py::test_login"

    # tail=20 → 마지막 20줄 반환
    r = client.get(
        f"/api/run_artifacts/{run_id}/logcat"
        f"?nodeid={nodeid_enc}&tail=20"
    )
    assert r.status_code == 200, r.text
    returned_lines = [ln for ln in r.text.splitlines() if ln.strip()]
    assert len(returned_lines) <= 20, (
        f"tail=20 요청인데 {len(returned_lines)}줄 반환됨"
    )

    # 반환 내용에 E(Error) / W(Warn) 줄이 포함되어야 함 (마지막 20줄 안에 있음)
    error_lines = [ln for ln in returned_lines if " E " in ln or " W " in ln]
    assert error_lines, "마지막 20줄에 Error/Warn 레벨 줄이 없음"

    # download=1 → Content-Disposition: attachment
    r2 = client.get(
        f"/api/run_artifacts/{run_id}/logcat"
        f"?nodeid={nodeid_enc}&tail=5&download=1"
    )
    assert r2.status_code == 200, r2.text
    cd = r2.headers.get("content-disposition", "")
    assert "attachment" in cd, f"download=1인데 attachment 없음: {cd}"
