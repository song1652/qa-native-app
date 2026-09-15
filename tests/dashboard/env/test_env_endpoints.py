"""
Integration tests for ENV Setup endpoints (M1-01, M1-03, M1-04, M1-07, M3.0).
"""
import json
import signal
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

DASHBOARD = Path(__file__).parents[3] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

from routes.env import router as env_router  # noqa: E402


ANDROID_AVD = {
    "avd": "Pixel_8_Android16",
    "deviceName": "Pixel 8",
    "platformVersion": "16",
}
IOS_SIMULATOR = {
    "deviceName": "iPhone 16 Plus",
    "platformVersion": "26.5",
    "udid": "A1B2C3D4-E5F6-7890-ABCD-EF1234567890",
    "state": "Shutdown",
}


# ── 앱 픽스처 ──────────────────────────────────────────────────────

@pytest.fixture
def app():
    _app = FastAPI()
    _app.include_router(env_router)
    return _app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# ── 헬퍼 ─────────────────────────────────────────────────────────────

def _session_file(tmp_path: Path, appium_status: str = "stopped", pid=None) -> Path:
    """tmp_path에 env_session.json 작성 후 경로 반환."""
    f = tmp_path / "env_session.json"
    f.write_text(json.dumps({
        "appium": {
            "status": appium_status,
            "pid": pid,
            "port": 4723,
            "error_msg": None,
            "started_at": None,
        },
        "android": {"status": "stopped", "avd": None, "started_at": None},
        "ios": {"status": "stopped", "simulator": None, "started_at": None},
    }), encoding="utf-8")
    return f


# ── M1-01: GET /api/env/status ────────────────────────────────────

class TestGetEnvStatus:

    def test_returns_200(self, client, tmp_path, monkeypatch):
        """GET /api/env/status → 200."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with patch("routes.env.detect_appium_status", return_value={
            "status": "stopped", "pid": None, "port": 4723, "error_msg": None,
            "started_at": None,
        }):
            res = client.get("/api/env/status")
        assert res.status_code == 200

    def test_response_has_appium_android_ios_keys(self, client, tmp_path, monkeypatch):
        """응답에 appium, android, ios 키 포함."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with patch("routes.env.detect_appium_status", return_value={
            "status": "stopped", "pid": None, "port": 4723, "error_msg": None,
            "started_at": None,
        }):
            res = client.get("/api/env/status")
        body = res.json()
        assert "appium" in body
        assert "android" in body
        assert "ios" in body

    def test_appium_status_is_five_value_model(self, client, tmp_path, monkeypatch):
        """appium.status는 5개 값 중 하나."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with patch("routes.env.detect_appium_status", return_value={
            "status": "external", "pid": None, "port": 4723, "error_msg": None,
            "started_at": None,
        }):
            res = client.get("/api/env/status")
        body = res.json()
        assert body["appium"]["status"] in ("stopped", "starting", "managed", "external", "error")

    def test_error_msg_included_when_error_state(self, client, tmp_path, monkeypatch):
        """error 상태이면 error_msg 포함."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with patch("routes.env.detect_appium_status", return_value={
            "status": "error", "pid": None, "port": 4723, "error_msg": "spawn failed",
            "started_at": None,
        }):
            res = client.get("/api/env/status")
        body = res.json()
        assert body["appium"]["error_msg"] == "spawn failed"

    def test_reconciles_and_persists_booted_ios_runtime(self, client, tmp_path, monkeypatch):
        """새로고침하면 stale starting 대신 실제 Booted 상태를 저장·반환한다."""
        session_file = _session_file(tmp_path, "stopped")
        session = json.loads(session_file.read_text(encoding="utf-8"))
        session["ios"] = {
            "status": "starting",
            "simulator": "iPhone 18 Pro",
            "started_at": "2026-09-14T09:00:00",
        }
        session_file.write_text(json.dumps(session), encoding="utf-8")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        simctl = MagicMock(
            returncode=0,
            stdout=json.dumps({"devices": {"runtime": [{
                "name": "iPhone 18 Pro",
                "udid": "E73939EF-741D-4A72-BEA7-97D31B15719A",
                "state": "Booted",
                "isAvailable": True,
            }]}}),
            stderr="",
        )
        with patch("routes.env.detect_appium_status", return_value={
            "status": "stopped", "pid": None, "port": 4723,
            "error_msg": None, "started_at": None,
        }), patch("routes.env.check_android_real_devices", return_value={}), \
                patch("routes.env.check_ios_real_devices", return_value={}), \
                patch("utils.system.subprocess.run", return_value=simctl):
            response = client.get("/api/env/status")

        assert response.json()["ios"]["status"] == "running"
        saved = json.loads(session_file.read_text(encoding="utf-8"))
        assert saved["ios"]["status"] == "running"

    def test_reconciles_and_persists_appium_ownership_state(self, client, tmp_path, monkeypatch):
        """실제 외부 Appium 감지 결과를 저장해 후속 시작 요청의 중복 실행을 막는다."""
        session_file = _session_file(tmp_path, "stopped")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        detected = {
            "status": "external", "pid": None, "port": 4723,
            "error_msg": None, "started_at": None, "version": "3.5.2",
            "drivers": {"uiautomator2": True, "xcuitest": True},
            "active_sessions": 0, "uptime_seconds": None, "mjpeg_enabled": None,
        }
        with patch("routes.env.detect_appium_status", return_value=detected), \
                patch("routes.env.detect_android_runtime", side_effect=lambda value: value), \
                patch("routes.env.detect_ios_runtime", side_effect=lambda value: value), \
                patch("routes.env.check_android_real_devices", return_value={}), \
                patch("routes.env.check_ios_real_devices", return_value={}):
            response = client.get("/api/env/status")

        assert response.status_code == 200
        saved = json.loads(session_file.read_text(encoding="utf-8"))
        assert saved["appium"]["status"] == "external"
        assert "drivers" not in saved["appium"]


class TestSystemVirtualDeviceDiscovery:

    def test_android_endpoint_returns_metadata_for_add_modal(self, client):
        """Removing the discovery route must break the Android add flow."""
        with patch("routes.env.list_system_avds", return_value=[ANDROID_AVD]):
            response = client.get("/api/env/android/list_system_avds")

        assert response.status_code == 200
        assert response.json() == {"ok": True, "avds": [ANDROID_AVD]}

    def test_ios_endpoint_returns_metadata_for_add_modal(self, client):
        """The iOS add flow receives version and UDID in one response."""
        with patch("routes.env.list_system_simulators", return_value=[IOS_SIMULATOR]):
            response = client.get("/api/env/ios/list_system_simulators")

        assert response.status_code == 200
        assert response.json() == {"ok": True, "simulators": [IOS_SIMULATOR]}

    def test_android_discovery_failure_is_structured(self, client):
        """SDK failures must be visible to the modal instead of looking empty."""
        with patch(
            "routes.env.list_system_avds",
            side_effect=RuntimeError("emulator binary not found"),
        ):
            response = client.get("/api/env/android/list_system_avds")

        assert response.status_code == 500
        assert response.json() == {
            "ok": False,
            "error": "discovery_failed",
            "message": "emulator binary not found",
        }

    def test_ios_discovery_failure_is_structured(self, client):
        """Malformed simctl output must produce actionable JSON."""
        with patch(
            "routes.env.list_system_simulators",
            side_effect=RuntimeError("simctl JSON 파싱 실패"),
        ):
            response = client.get("/api/env/ios/list_system_simulators")

        assert response.status_code == 500
        assert response.json() == {
            "ok": False,
            "error": "discovery_failed",
            "message": "simctl JSON 파싱 실패",
        }


def test_configured_android_avds_endpoint_includes_row_runtime_identity(
    client, tmp_path, monkeypatch
):
    monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
    configured = [{"deviceName": "Pixel 8", "avd": "Pixel_8", "platformVersion": "16"}]
    with patch("routes.env.load_devices_json", return_value={"android": {"emulator": configured}}), \
            patch("routes.env.detect_android_runtime", return_value={
                "status": "running", "avd": "Pixel_8", "serial": "emulator-5554",
            }):
        response = client.get("/api/env/android/avds")

    assert response.status_code == 200
    assert response.json()["avds"][0]["status"] == "running"
    assert response.json()["avds"][0]["serial"] == "emulator-5554"


def test_configured_ios_simulators_endpoint_includes_row_runtime_identity(
    client, tmp_path, monkeypatch
):
    monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
    configured = [{"deviceName": "iPhone 16", "udid": IOS_SIMULATOR["udid"], "platformVersion": "26.5"}]
    with patch("routes.env.load_devices_json", return_value={"ios": {"simulator": configured}}), \
            patch("routes.env.detect_ios_runtime", return_value={
                "status": "running", "simulator": "iPhone 16", "udid": IOS_SIMULATOR["udid"],
            }):
        response = client.get("/api/env/ios/simulators")

    assert response.status_code == 200
    assert response.json()["simulators"][0]["status"] == "running"
    assert response.json()["simulators"][0]["udid"] == IOS_SIMULATOR["udid"]


# ── M1-02: GET /api/env/appium/log ───────────────────────────────

class TestGetAppiumLog:

    def test_returns_empty_lines_when_log_missing(self, client, tmp_path, monkeypatch):
        """로그 파일 없을 때 ok=True, lines=[] 반환."""
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        res = client.get("/api/env/appium/log")
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["lines"] == []

    def test_returns_last_n_lines_when_log_exists(self, client, tmp_path, monkeypatch):
        """로그 파일 있을 때 마지막 N줄 반환."""
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        log_file = log_dir / "appium_server.log"
        log_file.write_text("\n".join(f"line{i}" for i in range(1, 11)), encoding="utf-8")

        res = client.get("/api/env/appium/log?lines=5")
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["lines"] == ["line6", "line7", "line8", "line9", "line10"]

    def test_returns_all_lines_when_fewer_than_requested(self, client, tmp_path, monkeypatch):
        """파일 줄 수가 요청 N보다 적으면 전체 반환."""
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        log_file = log_dir / "appium_server.log"
        log_file.write_text("only line", encoding="utf-8")

        res = client.get("/api/env/appium/log?lines=200")
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        assert body["lines"] == ["only line"]


# ── M1-03: POST /api/env/appium/start ────────────────────────────

class TestPostAppiumStart:

    def test_returns_409_when_already_managed(self, client, tmp_path, monkeypatch):
        """managed 상태이면 409 already_running."""
        session_file = _session_file(tmp_path, "managed", pid=1111)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        res = client.post("/api/env/appium/start")
        assert res.status_code == 409
        assert res.json()["error"] == "already_running"

    def test_returns_409_when_already_external(self, client, tmp_path, monkeypatch):
        """external 상태이면 409 already_running."""
        session_file = _session_file(tmp_path, "external")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        res = client.post("/api/env/appium/start")
        assert res.status_code == 409
        assert res.json()["error"] == "already_running"

    def test_returns_409_while_first_appium_process_is_starting(self, client, tmp_path, monkeypatch):
        """드라이버 로딩 중 연속 클릭이 두 번째 Appium으로 상태를 덮어쓰지 않는다."""
        session_file = _session_file(tmp_path, "starting", pid=55061)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        with patch("routes.env.subprocess.Popen") as popen:
            response = client.post("/api/env/appium/start")

        assert response.status_code == 409
        assert response.json()["error"] == "already_running"
        popen.assert_not_called()
        assert json.loads(session_file.read_text())["appium"]["pid"] == 55061

    def test_start_sets_starting_status(self, client, tmp_path, monkeypatch):
        """Appium 시작 성공 → 202, status=starting, pid·port 기록."""
        session_file = _session_file(tmp_path, "stopped")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        mock_proc = MagicMock()
        mock_proc.pid = 7777
        with patch("routes.env.subprocess.Popen", return_value=mock_proc):
            res = client.post("/api/env/appium/start")
        assert res.status_code == 202
        body = res.json()
        assert body["ok"] is True
        assert body["status"] == "starting"
        assert body["pid"] == 7777
        assert body["port"] == 4723
        saved = json.loads(session_file.read_text())
        assert saved["appium"]["status"] == "starting"
        assert saved["appium"]["pid"] == 7777

    def test_start_error_sets_error_state(self, client, tmp_path, monkeypatch):
        """Popen 실패 → error 상태 저장, 500 반환."""
        session_file = _session_file(tmp_path, "stopped")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        with patch("routes.env.subprocess.Popen", side_effect=FileNotFoundError("appium not found")):
            res = client.post("/api/env/appium/start")
        assert res.status_code == 500
        saved = json.loads(session_file.read_text())
        assert saved["appium"]["status"] == "error"
        assert "appium not found" in saved["appium"]["error_msg"]

    def test_retry_terminates_timed_out_managed_process_before_start(self, client, tmp_path, monkeypatch):
        """30초 타임아웃 뒤 재시도할 때 기존 Node 프로세스를 중복으로 남기지 않는다."""
        session_file = _session_file(tmp_path, "error", pid=2468)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        process = MagicMock(pid=7777)
        with patch("routes.env.os.kill") as kill, \
                patch("routes.env._wait_for_appium_exit", return_value=True), \
                patch("routes.env.subprocess.Popen", return_value=process):
            response = client.post("/api/env/appium/start")

        assert response.status_code == 202
        kill.assert_called_once_with(2468, signal.SIGTERM)


# ── M1-04: POST /api/env/appium/stop ─────────────────────────────

class TestPostAppiumStop:

    def test_stop_does_not_clear_ownership_until_process_and_port_are_gone(
        self, client, tmp_path, monkeypatch
    ):
        session_file = _session_file(tmp_path, "managed", pid=8888)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.is_pipeline_active", return_value=False), \
                patch("routes.env.os.kill"), \
                patch("routes.env._wait_for_appium_exit", return_value=False):
            response = client.post("/api/env/appium/stop")

        assert response.status_code == 504
        assert response.json()["error"] == "appium_stop_timeout"
        saved = json.loads(session_file.read_text())
        assert saved["appium"]["status"] == "error"
        assert saved["appium"]["pid"] == 8888

    def test_returns_403_when_capture_active(self, client, tmp_path, monkeypatch):
        """Capture Studio 세션 활성 → 403 capture_session_active."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with patch("routes.env.is_capture_active", return_value=True):
            res = client.post("/api/env/appium/stop")
        assert res.status_code == 403
        assert res.json()["error"] == "capture_session_active"

    def test_returns_409_when_pipeline_running(self, client, tmp_path, monkeypatch):
        """파이프라인 실행 중 → 409 pipeline_running."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with patch("routes.env.is_capture_active", return_value=False):
            with patch("routes.env.is_pipeline_active", return_value=True):
                res = client.post("/api/env/appium/stop")
        assert res.status_code == 409
        assert res.json()["error"] == "pipeline_running"

    def test_external_status_stops_the_process_owning_the_port(self, client, tmp_path, monkeypatch):
        """external 상태이면 포트를 점유한 프로세스를 안전하게 종료한다."""
        session_file = _session_file(tmp_path, "external")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        owner = MagicMock(stdout="4242\n", stderr="", returncode=0)
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.is_pipeline_active", return_value=False), \
                patch("routes.env.subprocess.run", return_value=owner), \
                patch("routes.env.os.kill") as kill, \
                patch("routes.env._wait_for_appium_exit", return_value=True):
            res = client.post("/api/env/appium/stop")
        assert res.status_code == 200
        assert res.json()["status"] == "stopped"
        kill.assert_called_once_with(4242, signal.SIGTERM)

    def test_stop_sends_sigterm_and_clears_pid(self, client, tmp_path, monkeypatch):
        """정상 stop → SIGTERM 전송 후 pid=None, status=stopped."""
        session_file = _session_file(tmp_path, "managed", pid=8888)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        with patch("routes.env.is_capture_active", return_value=False):
            with patch("routes.env.is_pipeline_active", return_value=False):
                with patch("routes.env.os.kill") as mock_kill, \
                        patch("routes.env._wait_for_appium_exit", return_value=True):
                    res = client.post("/api/env/appium/stop")
        assert res.status_code == 200
        assert res.json()["ok"] is True
        mock_kill.assert_called_once_with(8888, signal.SIGTERM)
        saved = json.loads(session_file.read_text())
        assert saved["appium"]["status"] == "stopped"
        assert saved["appium"]["pid"] is None

    def test_stop_ok_when_no_pid(self, client, tmp_path, monkeypatch):
        """pid 없어도 stop 성공."""
        session_file = _session_file(tmp_path, "stopped")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        with patch("routes.env.is_capture_active", return_value=False):
            with patch("routes.env.is_pipeline_active", return_value=False):
                res = client.post("/api/env/appium/stop")
        assert res.status_code == 200


# ── M1-07: POST /api/env/android/avd/stop ────────────────────────

class TestPostAvdStop:

    @pytest.fixture(autouse=True)
    def _matching_avd_identity(self, monkeypatch):
        monkeypatch.setattr("routes.env.get_android_avd_name", lambda _serial: "Pixel_7")

    def test_refuses_to_kill_when_stored_serial_belongs_to_another_avd(
        self, client, tmp_path, monkeypatch
    ):
        f = tmp_path / "env_session.json"
        f.write_text(json.dumps({
            "appium": {"status": "stopped", "pid": None, "port": 4723},
            "android": {"status": "running", "avd": "Pixel_7", "serial": "emulator-5556"},
            "ios": {"status": "stopped"},
        }))
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.get_android_avd_name", return_value="Other_AVD"), \
                patch("routes.env.subprocess.run") as runner:
            response = client.post(
                "/api/env/android/avd/stop", json={"avd": "Pixel_7"}
            )

        assert response.status_code == 409
        assert response.json()["error"] == "emulator_identity_mismatch"
        runner.assert_not_called()

    def test_rejects_stop_for_a_different_row(self, client, tmp_path, monkeypatch):
        """Clicking an inactive row must not terminate the active emulator."""
        f = tmp_path / "env_session.json"
        f.write_text(json.dumps({
            "appium": {"status": "stopped"},
            "android": {"status": "running", "avd": "Pixel_7", "serial": "emulator-5556"},
            "ios": {"status": "stopped"},
        }))
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.subprocess.run") as runner:
            response = client.post(
                "/api/env/android/avd/stop", json={"avd": "Pixel_8"}
            )

        assert response.status_code == 409
        assert response.json()["error"] == "different_avd_running"
        runner.assert_not_called()

    def test_returns_403_when_capture_active(self, client, tmp_path, monkeypatch):
        """Capture Studio 세션 활성 → 403 capture_session_active."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with patch("routes.env.is_capture_active", return_value=True):
            res = client.post("/api/env/android/avd/stop")
        assert res.status_code == 403
        assert res.json()["error"] == "capture_session_active"

    def test_avd_stop_updates_android_status(self, client, tmp_path, monkeypatch):
        """AVD stop → android.status=stopped, avd=None."""
        f = tmp_path / "env_session.json"
        f.write_text(json.dumps({
            "appium": {"status": "stopped", "pid": None, "port": 4723, "error_msg": None, "started_at": None},
            "android": {"status": "running", "avd": "Pixel_7", "serial": "emulator-5554", "started_at": "2026-01-01T00:00:00"},
            "ios": {"status": "stopped", "simulator": None, "started_at": None},
        }))
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        success = MagicMock(returncode=0, stdout="", stderr="")
        with patch("routes.env.is_capture_active", return_value=False):
            with patch("routes.env.subprocess.run", return_value=success):
                res = client.post("/api/env/android/avd/stop")
        assert res.status_code == 200
        saved = json.loads(f.read_text())
        assert saved["android"]["status"] == "stopped"
        assert saved["android"]["avd"] is None

    def test_avd_stop_calls_adb_emu_kill(self, client, tmp_path, monkeypatch):
        """AVD stop → adb emu kill 실행."""
        f = tmp_path / "env_session.json"
        f.write_text(json.dumps({
            "appium": {"status": "stopped", "pid": None, "port": 4723, "error_msg": None, "started_at": None},
            "android": {"status": "running", "avd": "Pixel_7", "serial": "emulator-5554", "started_at": "2026-01-01T00:00:00"},
            "ios": {"status": "stopped", "simulator": None, "started_at": None},
        }))
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        success = MagicMock(returncode=0, stdout="", stderr="")
        with patch("routes.env.is_capture_active", return_value=False):
            with patch("routes.env.subprocess.run", return_value=success) as mock_run:
                client.post("/api/env/android/avd/stop")
        mock_run.assert_called_once()
        call_args = mock_run.call_args.args[0]
        assert Path(call_args[0]).name == "adb"
        assert "emu" in call_args
        assert "kill" in call_args

    def test_avd_stop_uses_resolved_adb_binary(self, client, tmp_path, monkeypatch):
        """GUI 서버 PATH에 adb가 없어도 탐색된 절대경로로 종료한다."""
        f = tmp_path / "env_session.json"
        f.write_text(json.dumps({
            "appium": {"status": "stopped", "pid": None, "port": 4723, "error_msg": None, "started_at": None},
            "android": {"status": "running", "avd": "Pixel_7", "serial": "emulator-5554", "started_at": None},
            "ios": {"status": "stopped", "simulator": None, "started_at": None},
        }))
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        monkeypatch.setattr("routes.env.ADB_BIN", "/sdk/platform-tools/adb", raising=False)
        commands = []

        def runner(command, **_kwargs):
            commands.append(command)
            stdout = "Pixel_7\nOK\n" if command[-3:] == ["emu", "avd", "name"] else ""
            return MagicMock(returncode=0, stdout=stdout, stderr="")

        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.subprocess.run", side_effect=runner):
            response = client.post("/api/env/android/avd/stop")

        assert response.status_code == 200
        assert commands == [["/sdk/platform-tools/adb", "-s", "emulator-5554", "emu", "kill"]]

    def test_avd_stop_targets_the_persisted_emulator_serial(self, client, tmp_path, monkeypatch):
        """다른 adb 기기가 있어도 대시보드가 추적한 에뮬레이터만 종료한다."""
        f = tmp_path / "env_session.json"
        f.write_text(json.dumps({
            "appium": {"status": "stopped", "pid": None, "port": 4723, "error_msg": None, "started_at": None},
            "android": {"status": "running", "avd": "Pixel_7", "serial": "emulator-5556", "started_at": None},
            "ios": {"status": "stopped", "simulator": None, "started_at": None},
        }))
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        def run(command, **_kwargs):
            stdout = "Pixel_7\nOK\n" if command[-3:] == ["emu", "avd", "name"] else ""
            return MagicMock(returncode=0, stdout=stdout, stderr="")
        runner = MagicMock(side_effect=run)
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.subprocess.run", runner):
            response = client.post("/api/env/android/avd/stop")

        assert response.status_code == 200
        command = runner.call_args_list[-1].args[0]
        assert Path(command[0]).name == "adb"
        assert command[1:] == ["-s", "emulator-5556", "emu", "kill"]

    def test_returns_native_error_when_adb_shutdown_fails(self, client, tmp_path, monkeypatch):
        """adb 종료 실패를 stopped 성공으로 위장하지 않는다."""
        f = tmp_path / "env_session.json"
        f.write_text(json.dumps({
            "appium": {"status": "stopped", "pid": None, "port": 4723, "error_msg": None, "started_at": None},
            "android": {"status": "running", "avd": "Pixel_7", "serial": "emulator-5554", "started_at": None},
            "ios": {"status": "stopped", "simulator": None, "started_at": None},
        }))
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        failure = MagicMock(returncode=2, stdout="", stderr="Emulator refused shutdown")
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.subprocess.run", return_value=failure):
            response = client.post("/api/env/android/avd/stop")

        assert response.status_code == 500
        assert response.json() == {
            "ok": False,
            "error": "emulator_shutdown_failed",
            "detail": "Emulator refused shutdown",
        }
        assert json.loads(f.read_text())["android"]["status"] == "running"


# ── M2.1: POST /api/env/android/avd/start ────────────────────────

class TestPostAndroidAvdStart:

    def _session_with_android(self, tmp_path: Path, android_status: str = "stopped", avd=None) -> Path:
        f = tmp_path / "env_session.json"
        f.write_text(json.dumps({
            "appium": {"status": "managed", "pid": 100, "port": 4723, "error_msg": None, "started_at": None},
            "android": {"status": android_status, "avd": avd, "started_at": None},
            "ios": {"status": "stopped", "simulator": None, "started_at": None},
        }), encoding="utf-8")
        return f

    def test_returns_202_on_success(self, client, tmp_path, monkeypatch):
        """정상 시작 → 202, ok=true, status=starting."""
        f = self._session_with_android(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        with patch("routes.env.is_capture_active", return_value=False):
            with patch("routes.env.subprocess.Popen", return_value=mock_proc) as mock_popen:
                with patch("routes.env.get_default_device", return_value={"avd": "Pixel_7_Android15"}), \
                        patch("routes.env._list_installed_avds", return_value=["Pixel_7_Android15"]):
                    res = client.post("/api/env/android/avd/start")
        assert res.status_code == 202
        body = res.json()
        assert body["ok"] is True
        assert body["status"] == "starting"
        assert "avd" in body
        saved = json.loads(f.read_text())
        assert saved["android"]["status"] == "starting"

    def test_returns_409_when_already_running(self, client, tmp_path, monkeypatch):
        """android.status=running이면 409 already_running."""
        f = self._session_with_android(tmp_path, android_status="running", avd="Pixel_7")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        with patch("routes.env.is_capture_active", return_value=False):
            res = client.post("/api/env/android/avd/start")
        assert res.status_code == 409
        assert res.json()["error"] == "already_running"

    def test_returns_409_when_starting(self, client, tmp_path, monkeypatch):
        """android.status=starting이면 409 already_running."""
        f = self._session_with_android(tmp_path, android_status="starting")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        with patch("routes.env.is_capture_active", return_value=False):
            res = client.post("/api/env/android/avd/start")
        assert res.status_code == 409
        assert res.json()["error"] == "already_running"

    def test_returns_403_when_capture_active(self, client, tmp_path, monkeypatch):
        """Capture 세션 활성 → 403 capture_session_active."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with patch("routes.env.is_capture_active", return_value=True):
            res = client.post("/api/env/android/avd/start")
        assert res.status_code == 403
        assert res.json()["error"] == "capture_session_active"

    def test_uses_default_avd_when_body_empty(self, client, tmp_path, monkeypatch):
        """body 없으면 default avd 사용."""
        f = self._session_with_android(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        with patch("routes.env.is_capture_active", return_value=False):
            with patch("routes.env.subprocess.Popen", return_value=mock_proc):
                with patch("routes.env.get_default_device", return_value={"avd": "Default_AVD"}) as mock_default, \
                        patch("routes.env._list_installed_avds", return_value=["Default_AVD"]):
                    res = client.post("/api/env/android/avd/start", json={})
        assert res.status_code == 202
        mock_default.assert_called_once_with("android", "emulator")
        saved = json.loads(f.read_text())
        assert saved["android"]["avd"] == "Default_AVD"

    def test_uses_body_avd_when_provided(self, client, tmp_path, monkeypatch):
        """body에 avd 지정 시 해당 AVD 사용."""
        f = self._session_with_android(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        mock_proc = MagicMock()
        mock_proc.pid = 5678
        with patch("routes.env.is_capture_active", return_value=False):
            with patch("routes.env.subprocess.Popen", return_value=mock_proc) as mock_popen, \
                    patch("routes.env._list_installed_avds", return_value=["Custom_AVD"]):
                res = client.post("/api/env/android/avd/start", json={"avd": "Custom_AVD"})
        assert res.status_code == 202
        saved = json.loads(f.read_text())
        assert saved["android"]["avd"] == "Custom_AVD"
        call_cmd = mock_popen.call_args[0][0]
        assert "Custom_AVD" in call_cmd

    def test_uses_resolved_android_sdk_emulator_binary(self, client, tmp_path, monkeypatch):
        """PATH에 emulator가 없어도 SDK 절대경로로 AVD를 시작한다."""
        f = self._session_with_android(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(
            "routes.env.EMULATOR_BIN", "/sdk/emulator/emulator", raising=False
        )
        proc = MagicMock(pid=1234)
        commands = []

        def popen(command, **_kwargs):
            commands.append(command)
            return proc

        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.subprocess.run", return_value=MagicMock(returncode=0, stdout="Pixel_7\n", stderr="")), \
                patch("routes.env.subprocess.Popen", side_effect=popen), \
                patch("routes.env.get_default_device", return_value={"avd": "Pixel_7"}):
            response = client.post("/api/env/android/avd/start")

        assert response.status_code == 202
        assert commands[0][0] == "/sdk/emulator/emulator"

    def test_rejects_avd_that_is_not_installed_on_the_machine(self, client, tmp_path, monkeypatch):
        """웹 요청이 로컬 AVD 화이트리스트 밖의 이름을 실행하면 안 된다."""
        f = self._session_with_android(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.subprocess.run", return_value=MagicMock(returncode=0, stdout="Pixel_7\n", stderr="")), \
                patch("routes.env.subprocess.Popen"):
            response = client.post(
                "/api/env/android/avd/start", json={"avd": "Unknown_AVD"}
            )

        assert response.status_code == 400
        assert response.json()["error"] == "invalid_avd"


# ── M2.1: POST /api/env/ios/simulator/start ──────────────────────

class TestPostIosSimulatorStart:

    def test_rejects_a_different_simulator_while_one_is_running(
        self, client, tmp_path, monkeypatch
    ):
        f = self._session_with_ios(tmp_path, ios_status="running")
        session = json.loads(f.read_text())
        session["ios"]["udid"] = "BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB"
        f.write_text(json.dumps(session))
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        requested = "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"
        configured = [{"deviceName": "iPhone 16 Plus", "udid": requested}]
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.load_devices_json", return_value={"ios": {"simulator": configured}}), \
                patch("routes.env.detect_ios_runtime", side_effect=lambda value: value), \
                patch("routes.env.subprocess.run") as runner:
            response = client.post("/api/env/ios/simulator/start", json={"udid": requested})

        assert response.status_code == 409
        assert response.json()["error"] == "already_running"
        runner.assert_not_called()

    def test_slow_simctl_boot_does_not_block_status_requests(
        self, app, tmp_path, monkeypatch
    ):
        """A long simctl boot must not freeze every dashboard button and poll."""
        f = self._session_with_ios(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        def slow_popen(*_args, **_kwargs):
            time.sleep(0.4)
            return MagicMock()

        stopped = {
            "status": "stopped", "pid": None, "port": 4723,
            "error_msg": None, "started_at": None,
        }
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.get_default_device", return_value={"deviceName": "iPhone 18 Pro"}), \
                patch("routes.env.detect_appium_status", return_value=stopped), \
                patch("routes.env.detect_android_runtime", side_effect=lambda value: value), \
                patch("routes.env.detect_ios_runtime", side_effect=lambda value: value), \
                patch("routes.env._load_real_devices", return_value=([], [])), \
                patch("routes.env.check_android_real_devices", return_value={}), \
                patch("routes.env.check_ios_real_devices", return_value={}):
            entered = threading.Event()

            def marked_slow_popen(*args, **kwargs):
                entered.set()
                return slow_popen(*args, **kwargs)

            with patch("routes.env.subprocess.Popen", side_effect=marked_slow_popen), \
                    TestClient(app, raise_server_exceptions=False) as live_client:
                boot = threading.Thread(
                    target=lambda: live_client.post("/api/env/ios/simulator/start")
                )
                boot.start()
                assert entered.wait(timeout=1)
                started = time.monotonic()
                response = live_client.get("/api/env/status")
                elapsed = time.monotonic() - started
                boot.join(timeout=2)

        assert response.status_code == 200
        assert elapsed < 0.25

    def test_uses_configured_udid_as_simctl_identity(self, client, tmp_path, monkeypatch):
        """Duplicate simulator names cannot redirect a row action to another UDID."""
        udid = "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"
        f = self._session_with_ios(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        configured = {
            "ios": {"simulator": [{
                "deviceName": "iPhone 16 Plus",
                "platformVersion": "26.5",
                "udid": udid,
                "default": True,
            }]}
        }
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.load_devices_json", return_value=configured), \
                patch("routes.env.subprocess.Popen") as runner:
            response = client.post(
                "/api/env/ios/simulator/start", json={"udid": udid}
            )

        assert response.status_code == 202
        assert runner.call_args.args[0] == ["xcrun", "simctl", "boot", udid]
        saved = json.loads(f.read_text())
        assert saved["ios"]["simulator"] == "iPhone 16 Plus"
        assert saved["ios"]["udid"] == udid

    def _session_with_ios(self, tmp_path: Path, ios_status: str = "stopped") -> Path:
        f = tmp_path / "env_session.json"
        f.write_text(json.dumps({
            "appium": {"status": "managed", "pid": 100, "port": 4723, "error_msg": None, "started_at": None},
            "android": {"status": "stopped", "avd": None, "started_at": None},
            "ios": {"status": ios_status, "simulator": None, "started_at": None},
        }), encoding="utf-8")
        return f

    def test_returns_202_on_success(self, client, tmp_path, monkeypatch):
        """정상 시작 → 202, ok=true, status=starting."""
        f = self._session_with_ios(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        with patch("routes.env.is_capture_active", return_value=False):
            with patch("routes.env.subprocess.Popen"):
                with patch("routes.env.get_default_device", return_value={"deviceName": "iPhone 18 Pro"}):
                    res = client.post("/api/env/ios/simulator/start")
        assert res.status_code == 202
        body = res.json()
        assert body["ok"] is True
        assert body["status"] == "starting"
        saved = json.loads(f.read_text())
        assert saved["ios"]["status"] == "starting"

    def test_returns_403_when_capture_active(self, client, tmp_path, monkeypatch):
        """Capture 세션 활성 → 403 capture_session_active."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with patch("routes.env.is_capture_active", return_value=True):
            res = client.post("/api/env/ios/simulator/start")
        assert res.status_code == 403
        assert res.json()["error"] == "capture_session_active"

    def test_uses_default_simulator_when_body_empty(self, client, tmp_path, monkeypatch):
        """body 없으면 default simulator 사용."""
        f = self._session_with_ios(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        with patch("routes.env.is_capture_active", return_value=False):
            with patch("routes.env.subprocess.Popen"):
                with patch("routes.env.get_default_device", return_value={"deviceName": "iPhone 18 Pro"}) as mock_d:
                    res = client.post("/api/env/ios/simulator/start", json={})
        assert res.status_code == 202
        mock_d.assert_called_once_with("ios", "simulator")

    def test_uses_body_simulator_when_provided(self, client, tmp_path, monkeypatch):
        """body에 simulator 지정 시 해당 이름 사용."""
        f = self._session_with_ios(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        with patch("routes.env.is_capture_active", return_value=False):
            with patch("routes.env.subprocess.Popen") as mock_run:
                res = client.post("/api/env/ios/simulator/start", json={"simulator": "iPhone 15"})
        assert res.status_code == 202
        saved = json.loads(f.read_text())
        assert saved["ios"]["simulator"] == "iPhone 15"
        call_cmd = mock_run.call_args[0][0]
        assert "iPhone 15" in call_cmd

    def test_returns_native_error_when_simctl_boot_fails(self, client, tmp_path, monkeypatch):
        """simctl 오류를 성공처럼 저장하지 않고 웹 사용자에게 반환한다."""
        f = self._session_with_ios(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.subprocess.Popen", side_effect=OSError("Unable to boot device")), \
                patch("routes.env.get_default_device", return_value={"deviceName": "iPhone 18 Pro"}):
            response = client.post("/api/env/ios/simulator/start")

        assert response.status_code == 500
        assert response.json() == {
            "ok": False,
            "error": "simulator_boot_failed",
            "detail": "Unable to boot device",
        }

    def test_already_booted_simulator_is_an_idempotent_success(self, client, tmp_path, monkeypatch):
        """상태 조회와 클릭 사이에 이미 Booted가 되어도 사용자 요청은 성공한다."""
        f = self._session_with_ios(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.subprocess.Popen"), \
                patch("routes.env.get_default_device", return_value={"deviceName": "iPhone 18 Pro"}):
            response = client.post("/api/env/ios/simulator/start")

        assert response.status_code == 202
        assert response.json()["ok"] is True


# ── M2.1: POST /api/env/ios/simulator/stop ───────────────────────

class TestPostIosSimulatorStop:

    _UDID = "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"

    @pytest.fixture(autouse=True)
    def _configured_simulator(self, monkeypatch):
        monkeypatch.setattr(
            "routes.env.load_devices_json",
            lambda: {"ios": {"simulator": [{
                "deviceName": "iPhone 18 Pro", "udid": self._UDID,
            }]}},
        )

    def test_missing_running_udid_never_uses_broad_booted_selector(
        self, client, tmp_path, monkeypatch
    ):
        f = self._session_with_ios(tmp_path, ios_status="stopped")
        session = json.loads(f.read_text())
        session["ios"]["udid"] = None
        f.write_text(json.dumps(session))
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.subprocess.run") as runner:
            response = client.post("/api/env/ios/simulator/stop")

        assert response.status_code == 404
        assert response.json()["error"] == "not_running"
        runner.assert_not_called()

    def test_rejects_unconfigured_shutdown_udid(self, client, tmp_path, monkeypatch):
        f = self._session_with_ios(tmp_path, ios_status="stopped")
        session = json.loads(f.read_text())
        session["ios"]["udid"] = None
        f.write_text(json.dumps(session))
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        requested = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.load_devices_json", return_value={"ios": {"simulator": []}}), \
                patch("routes.env.subprocess.run") as runner:
            response = client.post("/api/env/ios/simulator/stop", json={"udid": requested})

        assert response.status_code == 400
        assert response.json()["error"] == "invalid_udid"
        runner.assert_not_called()

    def test_shutdown_targets_requested_udid(self, client, tmp_path, monkeypatch):
        """A row shutdown must not use the broad 'booted' selector."""
        udid = "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"
        f = self._session_with_ios(tmp_path)
        session = json.loads(f.read_text())
        session["ios"]["udid"] = udid
        f.write_text(json.dumps(session))
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        success = MagicMock(returncode=0, stdout="", stderr="")
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.subprocess.run", return_value=success) as runner:
            response = client.post(
                "/api/env/ios/simulator/stop", json={"udid": udid}
            )

        assert response.status_code == 200
        assert runner.call_args.args[0] == ["xcrun", "simctl", "shutdown", udid]

    def _session_with_ios(self, tmp_path: Path, ios_status: str = "running") -> Path:
        f = tmp_path / "env_session.json"
        f.write_text(json.dumps({
            "appium": {"status": "managed", "pid": 100, "port": 4723, "error_msg": None, "started_at": None},
            "android": {"status": "stopped", "avd": None, "started_at": None},
            "ios": {"status": ios_status, "simulator": "iPhone 18 Pro", "udid": self._UDID, "started_at": "2026-01-01T00:00:00"},
        }), encoding="utf-8")
        return f

    def test_returns_200_on_success(self, client, tmp_path, monkeypatch):
        """정상 종료 → 200, ok=true."""
        f = self._session_with_ios(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        with patch("routes.env.is_capture_active", return_value=False):
            with patch("routes.env.subprocess.run"):
                res = client.post("/api/env/ios/simulator/stop")
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True
        saved = json.loads(f.read_text())
        assert saved["ios"]["status"] == "stopped"
        assert saved["ios"]["simulator"] is None

    def test_returns_403_when_capture_active(self, client, tmp_path, monkeypatch):
        """Capture 세션 활성 → 403 capture_session_active."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with patch("routes.env.is_capture_active", return_value=True):
            res = client.post("/api/env/ios/simulator/stop")
        assert res.status_code == 403
        assert res.json()["error"] == "capture_session_active"

    def test_calls_xcrun_simctl_shutdown(self, client, tmp_path, monkeypatch):
        """xcrun simctl shutdown이 저장된 UDID를 대상으로 하는지 확인."""
        f = self._session_with_ios(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        with patch("routes.env.is_capture_active", return_value=False):
            with patch("routes.env.subprocess.run") as mock_run:
                client.post("/api/env/ios/simulator/stop")
        mock_run.assert_called_once()
        call_cmd = mock_run.call_args[0][0]
        assert call_cmd == ["xcrun", "simctl", "shutdown", self._UDID]

    def test_shutdown_passes_exactly_one_command_argument(self, client, tmp_path, monkeypatch):
        """subprocess.run에 중복 명령 인자를 넘겨 종료가 무시되는 회귀를 막는다."""
        f = self._session_with_ios(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as runner:
            response = client.post("/api/env/ios/simulator/stop")

        assert response.status_code == 200
        assert runner.call_args.args == (["xcrun", "simctl", "shutdown", self._UDID],)

    def test_returns_native_error_when_simctl_shutdown_fails(self, client, tmp_path, monkeypatch):
        """시뮬레이터 종료 실패를 stopped 성공으로 위장하지 않는다."""
        f = self._session_with_ios(tmp_path)
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", f)
        failure = MagicMock(returncode=2, stdout="", stderr="Shutdown failed")
        with patch("routes.env.is_capture_active", return_value=False), \
                patch("routes.env.subprocess.run", return_value=failure):
            response = client.post("/api/env/ios/simulator/stop")

        assert response.status_code == 500
        assert response.json()["error"] == "simulator_shutdown_failed"


# ── M3.0: GET /api/env/status — real_devices ─────────────────────

class TestGetEnvStatusRealDevices:
    """GET /api/env/status 응답에 real_devices 배열 포함 (M3.0)."""

    def _patch_appium(self):
        return patch("routes.env.detect_appium_status", return_value={
            "status": "stopped", "pid": None, "port": 4723,
            "error_msg": None, "started_at": None,
        })

    def test_includes_real_devices_in_android(self, client, tmp_path, monkeypatch):
        """android 응답에 real_devices 배열 포함."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with self._patch_appium():
            with patch("routes.env.check_android_real_devices", return_value={"R3CN": False}):
                with patch("routes.env.check_ios_real_devices", return_value={}):
                    with patch("routes.env._load_real_devices", return_value=(
                        [{"deviceName": "Galaxy S24", "udid": "R3CN"}],
                        [],
                    )):
                        res = client.get("/api/env/status")
        body = res.json()
        assert "real_devices" in body["android"]
        assert isinstance(body["android"]["real_devices"], list)

    def test_includes_real_devices_in_ios(self, client, tmp_path, monkeypatch):
        """ios 응답에 real_devices 배열 포함."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with self._patch_appium():
            with patch("routes.env.check_android_real_devices", return_value={}):
                with patch("routes.env.check_ios_real_devices", return_value={"UDID-1": False}):
                    with patch("routes.env._load_real_devices", return_value=(
                        [],
                        [{"deviceName": "iPhone 16", "udid": "UDID-1"}],
                    )):
                        res = client.get("/api/env/status")
        body = res.json()
        assert "real_devices" in body["ios"]
        assert isinstance(body["ios"]["real_devices"], list)

    def test_real_device_connected_false_when_adb_fails(self, client, tmp_path, monkeypatch):
        """adb 실패 → connected=False 가 응답에 포함."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with self._patch_appium():
            with patch("routes.env.check_android_real_devices", return_value={"SER1": False}):
                with patch("routes.env.check_ios_real_devices", return_value={}):
                    with patch("routes.env._load_real_devices", return_value=(
                        [{"deviceName": "Pixel 7", "udid": "SER1"}],
                        [],
                    )):
                        res = client.get("/api/env/status")
        body = res.json()
        devs = body["android"]["real_devices"]
        assert len(devs) == 1
        assert devs[0]["connected"] is False

    def test_real_device_includes_wifi_ip(self, client, tmp_path, monkeypatch):
        """android real_device에 wifi_ip 필드 포함."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with self._patch_appium():
            with patch("routes.env.check_android_real_devices", return_value={"SER1": False}):
                with patch("routes.env.check_ios_real_devices", return_value={}):
                    with patch("routes.env._load_real_devices", return_value=(
                        [{"deviceName": "Galaxy S24", "udid": "SER1", "wifi_ip": "192.168.1.100"}],
                        [],
                    )):
                        res = client.get("/api/env/status")
        body = res.json()
        devs = body["android"]["real_devices"]
        assert devs[0]["wifi_ip"] == "192.168.1.100"

    def test_real_device_wifi_ip_empty_when_not_set(self, client, tmp_path, monkeypatch):
        """wifi_ip 미설정 기기는 wifi_ip 빈 문자열."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        with self._patch_appium():
            with patch("routes.env.check_android_real_devices", return_value={"SER1": False}):
                with patch("routes.env.check_ios_real_devices", return_value={}):
                    with patch("routes.env._load_real_devices", return_value=(
                        [{"deviceName": "Galaxy S24", "udid": "SER1"}],
                        [],
                    )):
                        res = client.get("/api/env/status")
        body = res.json()
        devs = body["android"]["real_devices"]
        assert devs[0]["wifi_ip"] == ""


# ── M3.0: POST /api/env/android/real/connect ─────────────────────

class TestPostAndroidRealConnect:

    def test_returns_ok_on_success(self, client, monkeypatch):
        """adb connect 성공 → ok=True."""
        def fake_run(cmd, **kwargs):
            class R:
                stdout = "connected to 192.168.1.100:5555"
                returncode = 0
            return R()

        monkeypatch.setattr("routes.env.subprocess.run", fake_run)
        with patch("routes.env._get_wifi_serial", return_value="192.168.1.100:5555"):
            res = client.post("/api/env/android/real/connect",
                              json={})
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True

    def test_uses_wifi_ip_from_devices_json(self, client, monkeypatch):
        """body에 serial 없으면 devices.json wifi_ip 사용."""
        called_with = {}

        def fake_run(cmd, **kwargs):
            called_with["cmd"] = cmd

            class R:
                stdout = "connected to 192.168.1.100:5555"
                returncode = 0
            return R()

        monkeypatch.setattr("routes.env.subprocess.run", fake_run)
        with patch("routes.env._get_wifi_serial", return_value="192.168.1.100:5555"):
            client.post("/api/env/android/real/connect", json={})

        assert "192.168.1.100:5555" in called_with["cmd"]

    def test_uses_serial_from_body_when_provided(self, client, monkeypatch):
        """body에 serial 있으면 그 값을 adb connect에 사용."""
        called_with = {}

        def fake_run(cmd, **kwargs):
            called_with["cmd"] = cmd

            class R:
                stdout = "connected to 10.0.0.5:5555"
                returncode = 0
            return R()

        monkeypatch.setattr("routes.env.subprocess.run", fake_run)
        res = client.post("/api/env/android/real/connect",
                          json={"serial": "10.0.0.5:5555"})
        assert res.status_code == 200
        assert "10.0.0.5:5555" in called_with["cmd"]

    def test_returns_ok_false_when_adb_fails(self, client, monkeypatch):
        """adb 실행 중 예외 → ok=False, 200 반환."""
        def fake_run(cmd, **kwargs):
            raise OSError("adb not found")

        monkeypatch.setattr("routes.env.subprocess.run", fake_run)
        with patch("routes.env._get_wifi_serial", return_value="192.168.1.100:5555"):
            res = client.post("/api/env/android/real/connect", json={})
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is False
        assert "error" in body

    def test_returns_ok_false_when_adb_process_returns_error(self, client, monkeypatch):
        """adb가 실행됐어도 비정상 종료면 연결 성공으로 표시하지 않는다."""
        failure = MagicMock(returncode=1, stdout="", stderr="connection refused")
        monkeypatch.setattr("routes.env.subprocess.run", lambda *_args, **_kwargs: failure)
        with patch("routes.env._get_wifi_serial", return_value="192.168.1.100:5555"):
            res = client.post("/api/env/android/real/connect", json={})
        assert res.status_code == 200
        assert res.json()["ok"] is False
        assert "connection refused" in res.json()["error"]

    def test_returns_ok_false_when_no_serial(self, client, monkeypatch):
        """wifi_ip 미설정이고 serial도 없으면 ok=False."""
        with patch("routes.env._get_wifi_serial", return_value=None):
            res = client.post("/api/env/android/real/connect", json={})
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is False


# ── M3.0: POST /api/env/android/real/disconnect ──────────────────

class TestPostAndroidRealDisconnect:

    def test_returns_ok_on_success(self, client, monkeypatch):
        """adb disconnect 성공 → ok=True."""
        def fake_run(cmd, **kwargs):
            class R:
                stdout = "disconnected 192.168.1.100:5555"
                returncode = 0
            return R()

        monkeypatch.setattr("routes.env.subprocess.run", fake_run)
        with patch("routes.env._get_wifi_serial", return_value="192.168.1.100:5555"):
            res = client.post("/api/env/android/real/disconnect", json={})
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is True

    def test_uses_serial_from_body_when_provided(self, client, monkeypatch):
        """body에 serial 있으면 그 값을 adb disconnect에 사용."""
        called_with = {}

        def fake_run(cmd, **kwargs):
            called_with["cmd"] = cmd

            class R:
                stdout = "disconnected 10.0.0.5:5555"
                returncode = 0
            return R()

        monkeypatch.setattr("routes.env.subprocess.run", fake_run)
        res = client.post("/api/env/android/real/disconnect",
                          json={"serial": "10.0.0.5:5555"})
        assert res.status_code == 200
        assert "10.0.0.5:5555" in called_with["cmd"]

    def test_returns_ok_false_when_adb_fails(self, client, monkeypatch):
        """adb 실행 중 예외 → ok=False, 200 반환."""
        def fake_run(cmd, **kwargs):
            raise OSError("adb not found")

        monkeypatch.setattr("routes.env.subprocess.run", fake_run)
        with patch("routes.env._get_wifi_serial", return_value="192.168.1.100:5555"):
            res = client.post("/api/env/android/real/disconnect", json={})
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is False
        assert "error" in body

    def test_returns_ok_false_when_adb_process_returns_error(self, client, monkeypatch):
        """adb가 실행됐어도 비정상 종료면 해제 성공으로 표시하지 않는다."""
        failure = MagicMock(returncode=1, stdout="", stderr="device not found")
        monkeypatch.setattr("routes.env.subprocess.run", lambda *_args, **_kwargs: failure)
        with patch("routes.env._get_wifi_serial", return_value="192.168.1.100:5555"):
            res = client.post("/api/env/android/real/disconnect", json={})
        assert res.status_code == 200
        assert res.json()["ok"] is False
        assert "device not found" in res.json()["error"]

    def test_returns_ok_false_when_no_serial(self, client, monkeypatch):
        """wifi_ip 미설정이고 serial도 없으면 ok=False."""
        with patch("routes.env._get_wifi_serial", return_value=None):
            res = client.post("/api/env/android/real/disconnect", json={})
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is False

    def test_returns_403_when_android_capture_active(self, client, monkeypatch):
        """Android Capture 세션 활성 → 403 capture_session_active (F6)."""
        with patch("routes.env.is_capture_active", return_value=True):
            res = client.post("/api/env/android/real/disconnect", json={})
        assert res.status_code == 403
        assert res.json()["error"] == "capture_session_active"


# ── F3: POST /api/env/appium/start 127.0.0.1 바인딩 ─────────────────


class TestAppiumStartLocalhostBinding:

    def test_start_uses_localhost_address(self, client, tmp_path, monkeypatch):
        """Appium 시작 시 --address 127.0.0.1 사용 (F3)."""
        session_file = _session_file(tmp_path, "stopped")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        called_cmd = {}
        orig_popen = __import__("subprocess").Popen

        def fake_popen(cmd, **kwargs):
            called_cmd["cmd"] = cmd
            return mock_proc

        with patch("routes.env.subprocess.Popen", side_effect=fake_popen):
            client.post("/api/env/appium/start")

        assert "--address" in called_cmd.get("cmd", [])
        idx = called_cmd["cmd"].index("--address")
        assert called_cmd["cmd"][idx + 1] == "127.0.0.1"

    def test_start_does_not_use_0000(self, client, tmp_path, monkeypatch):
        """Appium 시작 명령에 0.0.0.0이 포함되지 않아야 한다 (F3)."""
        session_file = _session_file(tmp_path, "stopped")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        called_cmd = {}

        def fake_popen(cmd, **kwargs):
            called_cmd["cmd"] = cmd
            return mock_proc

        with patch("routes.env.subprocess.Popen", side_effect=fake_popen):
            client.post("/api/env/appium/start")

        assert "0.0.0.0" not in called_cmd.get("cmd", [])

    def test_start_uses_resolved_appium_and_node_environment(self, client, tmp_path, monkeypatch):
        """NVM Appium을 찾은 동일 bin PATH로 서버 프로세스를 시작한다."""
        session_file = _session_file(tmp_path, "stopped")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        monkeypatch.setattr("routes.env.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("routes.env.APPIUM_BIN", "/nvm/v24/bin/appium", raising=False)
        monkeypatch.setattr(
            "routes.env.subprocess_env_for",
            lambda _binary: {"PATH": "/nvm/v24/bin:/usr/bin"},
            raising=False,
        )
        captured = {}

        def popen(command, **kwargs):
            captured["command"] = command
            captured["env"] = kwargs.get("env")
            return MagicMock(pid=4321)

        with patch("routes.env.subprocess.Popen", side_effect=popen):
            response = client.post("/api/env/appium/start")

        assert response.status_code == 202
        assert captured["command"][0] == "/nvm/v24/bin/appium"
        assert captured["env"]["PATH"].startswith("/nvm/v24/bin:")


# ── F6: AVD stop / Simulator stop 플랫폼 인자 확인 ──────────────────


class TestCaptureActiveCallsitesPlatformArg:

    def test_avd_stop_checks_android_capture(self, client, tmp_path, monkeypatch):
        """Android AVD stop → is_capture_active("android") 호출 (F6)."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        captured = {}

        def fake_is_capture_active(platform=None):
            captured["platform"] = platform
            return False

        with patch("routes.env.is_capture_active", side_effect=fake_is_capture_active):
            with patch("routes.env.subprocess.run"):
                client.post("/api/env/android/avd/stop")

        assert captured.get("platform") == "android"

    def test_simulator_stop_checks_ios_capture(self, client, tmp_path, monkeypatch):
        """iOS Simulator stop → is_capture_active("ios") 호출 (F6)."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        captured = {}

        def fake_is_capture_active(platform=None):
            captured["platform"] = platform
            return False

        with patch("routes.env.is_capture_active", side_effect=fake_is_capture_active):
            with patch("routes.env.subprocess.run"):
                client.post("/api/env/ios/simulator/stop")

        assert captured.get("platform") == "ios"

    def test_wifi_connect_checks_android_capture(self, client, monkeypatch):
        """Android WiFi connect → is_capture_active("android") 호출 (F6)."""
        captured = {}

        def fake_is_capture_active(platform=None):
            captured["platform"] = platform
            return False

        with patch("routes.env.is_capture_active", side_effect=fake_is_capture_active):
            with patch("routes.env._get_wifi_serial", return_value=None):
                client.post("/api/env/android/real/connect", json={})

        assert captured.get("platform") == "android"

    def test_wifi_disconnect_checks_android_capture(self, client, monkeypatch):
        """Android WiFi disconnect → is_capture_active("android") 호출 (F6)."""
        captured = {}

        def fake_is_capture_active(platform=None):
            captured["platform"] = platform
            return False

        with patch("routes.env.is_capture_active", side_effect=fake_is_capture_active):
            with patch("routes.env._get_wifi_serial", return_value=None):
                client.post("/api/env/android/real/disconnect", json={})

        assert captured.get("platform") == "android"


# ── US-3: 공용 fixture ────────────────────────────────────────────────

def _minimal_devices() -> dict:
    return {
        "android": {
            "emulator": [{"deviceName": "Pixel_7", "avd": "Pixel_7_API_34", "default": True}],
            "real_device": [{"deviceName": "Galaxy S24", "udid": "SER1", "default": True}],
        },
        "ios": {
            "simulator": [{"deviceName": "iPhone 15", "default": True}],
            "real_device": [{"deviceName": "iPhone 16", "udid": "UDID1", "default": True}],
        },
    }


@pytest.fixture
def tmp_devices_json(tmp_path, monkeypatch):
    """devices.json을 tmp_path에 격리하고 _DEVICES_PATH를 패치."""
    import utils.state as state_mod
    devices_path = tmp_path / "devices.json"
    devices_path.write_text(
        json.dumps(_minimal_devices(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(state_mod, "_DEVICES_PATH", devices_path)
    monkeypatch.setattr(
        "routes.env.list_system_avds",
        lambda: [
            {"avd": "Pixel_7_API_34", "deviceName": "Pixel 7", "platformVersion": "14"},
            {"avd": "Pixel_8_API_35", "deviceName": "Pixel 8", "platformVersion": "15"},
        ],
    )
    monkeypatch.setattr(
        "routes.env.list_system_simulators",
        lambda: [
            {
                "deviceName": f"iPhone {number}",
                "platformVersion": "26.5",
                "udid": f"00000000-0000-0000-0000-{number:012d}",
                "state": "Shutdown",
            }
            for number in (16, 17, 99)
        ] + [IOS_SIMULATOR],
    )
    return devices_path


# ── US-3: POST /api/env/android/add ──────────────────────────────────

class TestPostAndroidAdd:

    def test_adds_emulator_to_devices_json(self, client, tmp_devices_json):
        """에뮬레이터 추가 → devices.json에 항목이 늘어난다."""
        res = client.post("/api/env/android/add", json={
            "mode": "emulator",
            "deviceName": "Pixel 8",
            "avd": "Pixel_8_API_35",
            "platformVersion": "15",
            "default": False,
        })
        assert res.status_code == 200
        assert res.json()["ok"] is True
        saved = json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        names = [x["deviceName"] for x in saved["android"]["emulator"]]
        assert "Pixel 8" in names

    def test_returns_400_when_deviceName_missing(self, client, tmp_devices_json):
        """deviceName 없으면 400."""
        res = client.post("/api/env/android/add", json={
            "mode": "emulator",
            "avd": "Pixel_7_API_34",
        })
        assert res.status_code == 400
        assert "deviceName" in res.json()["error"]

    def test_returns_400_when_avd_missing_for_emulator(self, client, tmp_devices_json):
        """emulator 모드에서 avd 없으면 400."""
        res = client.post("/api/env/android/add", json={
            "mode": "emulator",
            "deviceName": "Pixel 8",
        })
        assert res.status_code == 400
        assert "avd" in res.json()["error"]

    def test_returns_400_when_udid_missing_for_real_device(self, client, tmp_devices_json):
        """real_device 모드에서 udid 없으면 400."""
        res = client.post("/api/env/android/add", json={
            "mode": "real_device",
            "deviceName": "Galaxy S25",
        })
        assert res.status_code == 400
        assert "udid" in res.json()["error"]

    def test_sets_default_when_requested(self, client, tmp_devices_json):
        """default=True로 추가하면 기존 default가 해제된다."""
        res = client.post("/api/env/android/add", json={
            "mode": "emulator",
            "deviceName": "Pixel_8",
            "avd": "Pixel_8_API_35",
            "platformVersion": "15",
            "default": True,
        })
        assert res.status_code == 200
        saved = json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        defaults = [x for x in saved["android"]["emulator"] if x.get("default")]
        assert len(defaults) == 1
        assert defaults[0]["deviceName"] == "Pixel 8"

    def test_adds_real_device(self, client, tmp_devices_json):
        """real_device 추가 → devices.json에 항목이 늘어난다."""
        res = client.post("/api/env/android/add", json={
            "mode": "real_device",
            "deviceName": "Pixel_7a",
            "udid": "NEWSER",
            "default": False,
        })
        assert res.status_code == 200
        saved = json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        names = [x["deviceName"] for x in saved["android"]["real_device"]]
        assert "Pixel_7a" in names

    def test_returns_400_for_invalid_mode(self, client, tmp_devices_json):
        """잘못된 mode 값이면 400."""
        res = client.post("/api/env/android/add", json={
            "mode": "tablet",
            "deviceName": "Something",
        })
        assert res.status_code == 400


# ── US-3: POST /api/env/android/remove ───────────────────────────────

class TestPostAndroidRemove:

    def test_removes_device_from_json(self, client, tmp_devices_json):
        """존재하는 디바이스 추가 후 삭제 → 항목이 줄어든다."""
        client.post("/api/env/android/add", json={
            "mode": "emulator", "deviceName": "Pixel 8",
            "avd": "Pixel_8_API_35", "platformVersion": "15", "default": False,
        })
        res = client.post("/api/env/android/remove", json={
            "mode": "emulator", "deviceName": "Pixel 8",
        })
        assert res.status_code == 200
        assert res.json()["ok"] is True
        saved = json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        names = [x["deviceName"] for x in saved["android"]["emulator"]]
        assert "Pixel 8" not in names

    def test_returns_400_when_last_item(self, client, tmp_devices_json):
        """마지막 에뮬레이터 삭제 시도 → 400, error code는 정확히 last_device."""
        res = client.post("/api/env/android/remove", json={
            "mode": "emulator", "deviceName": "Pixel_7",
        })
        assert res.status_code == 400
        assert res.json()["error"] == "last_device"

    def test_auto_sets_default_after_remove(self, client, tmp_devices_json):
        """삭제 후 default:true 없으면 첫 번째에 자동 설정."""
        client.post("/api/env/android/add", json={
            "mode": "emulator", "deviceName": "Pixel 8",
            "avd": "Pixel_8_API_35", "platformVersion": "15", "default": False,
        })
        client.post("/api/env/android/remove", json={
            "mode": "emulator", "deviceName": "Pixel_7",
        })
        saved = json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        emulators = saved["android"]["emulator"]
        assert len(emulators) == 1
        assert emulators[0]["default"] is True

    def test_returns_400_when_deviceName_missing(self, client, tmp_devices_json):
        """deviceName 없으면 400."""
        res = client.post("/api/env/android/remove", json={"mode": "emulator"})
        assert res.status_code == 400

    def test_real_device_allows_deletion_to_zero(self, client, tmp_devices_json):
        """실기기(real_device)는 마지막 1대도 삭제 가능 — 0대 허용."""
        res = client.post("/api/env/android/remove", json={
            "mode": "real_device", "deviceName": "Galaxy S24",
        })
        assert res.status_code == 200
        assert res.json()["ok"] is True
        import json as _json
        saved = _json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        assert saved["android"]["real_device"] == []

    def test_emulator_empty_section_returns_404_not_400(self, client, tmp_devices_json):
        """에뮬레이터 0개 상태에서 remove 요청 → 404 (기기 없음), 400 아님."""
        import json as _json
        data = _json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        data["android"]["emulator"] = []
        tmp_devices_json.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")
        res = client.post("/api/env/android/remove", json={
            "mode": "emulator", "deviceName": "anything",
        })
        assert res.status_code == 404

    def test_android_remove_returns_403_when_capture_active(self, client, tmp_devices_json):
        """Capture Studio 활성 중 remove → 403 capture_session_active."""
        from unittest.mock import patch as _patch
        with _patch("routes.env.is_capture_active", return_value=True):
            res = client.post("/api/env/android/remove", json={
                "mode": "emulator", "deviceName": "Pixel_7",
            })
        assert res.status_code == 403
        assert res.json()["error"] == "capture_session_active"

    def test_android_remove_returns_409_when_pipeline_running(self, client, tmp_devices_json):
        """파이프라인 실행 중 remove → 409 pipeline_running."""
        from unittest.mock import patch as _patch
        with _patch("routes.env.is_capture_active", return_value=False), \
             _patch("routes.env.is_pipeline_active", return_value=True):
            res = client.post("/api/env/android/remove", json={
                "mode": "emulator", "deviceName": "Pixel_7",
            })
        assert res.status_code == 409
        assert res.json()["error"] == "pipeline_running"


# ── US-3: POST /api/env/ios/add ──────────────────────────────────────

class TestPostIosAdd:

    def test_adds_simulator(self, client, tmp_devices_json):
        """시뮬레이터 추가 → devices.json에 항목이 늘어난다."""
        res = client.post("/api/env/ios/add", json={
            "mode": "simulator",
            "deviceName": "iPhone 16",
            "platformVersion": "26.5",
            "udid": "00000000-0000-0000-0000-000000000016",
            "default": False,
        })
        assert res.status_code == 200
        assert res.json()["ok"] is True
        saved = json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        names = [x["deviceName"] for x in saved["ios"]["simulator"]]
        assert "iPhone 16" in names

    def test_returns_400_when_deviceName_missing(self, client, tmp_devices_json):
        """deviceName 없으면 400."""
        res = client.post("/api/env/ios/add", json={"mode": "simulator"})
        assert res.status_code == 400

    def test_returns_400_when_udid_missing_for_real_device(self, client, tmp_devices_json):
        """real_device 모드에서 udid 없으면 400."""
        res = client.post("/api/env/ios/add", json={
            "mode": "real_device",
            "deviceName": "iPhone 16 Pro",
        })
        assert res.status_code == 400
        assert "udid" in res.json()["error"]

    def test_adds_real_device(self, client, tmp_devices_json):
        """iOS 실기기 추가 → devices.json에 항목이 늘어난다."""
        res = client.post("/api/env/ios/add", json={
            "mode": "real_device",
            "deviceName": "iPhone 16 Pro",
            "udid": "NEWUDID",
            "default": False,
        })
        assert res.status_code == 200
        saved = json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        names = [x["deviceName"] for x in saved["ios"]["real_device"]]
        assert "iPhone 16 Pro" in names

    def test_sets_default_when_requested(self, client, tmp_devices_json):
        """default=True로 추가하면 기존 default가 해제된다."""
        res = client.post("/api/env/ios/add", json={
            "mode": "simulator",
            "deviceName": "iPhone 16",
            "platformVersion": "26.5",
            "udid": "00000000-0000-0000-0000-000000000016",
            "default": True,
        })
        assert res.status_code == 200
        saved = json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        defaults = [x for x in saved["ios"]["simulator"] if x.get("default")]
        assert len(defaults) == 1
        assert defaults[0]["deviceName"] == "iPhone 16"


# ── US-3: POST /api/env/ios/remove ───────────────────────────────────

class TestPostIosRemove:

    def test_removes_simulator(self, client, tmp_devices_json):
        """시뮬레이터 추가 후 삭제 → 항목이 줄어든다."""
        client.post("/api/env/ios/add", json={
            "mode": "simulator", "deviceName": "iPhone 16",
            "platformVersion": "26.5", "udid": "00000000-0000-0000-0000-000000000016",
            "default": False,
        })
        res = client.post("/api/env/ios/remove", json={
            "mode": "simulator", "deviceName": "iPhone 16",
        })
        assert res.status_code == 200
        assert res.json()["ok"] is True
        saved = json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        names = [x["deviceName"] for x in saved["ios"]["simulator"]]
        assert "iPhone 16" not in names

    def test_returns_400_when_last_item(self, client, tmp_devices_json):
        """마지막 시뮬레이터 삭제 시도 → 400, error code는 정확히 last_device."""
        res = client.post("/api/env/ios/remove", json={
            "mode": "simulator", "deviceName": "iPhone 15",
        })
        assert res.status_code == 400
        assert res.json()["error"] == "last_device"

    def test_auto_sets_default_after_remove(self, client, tmp_devices_json):
        """삭제 후 default:true 없으면 첫 번째에 자동 설정."""
        client.post("/api/env/ios/add", json={
            "mode": "simulator", "deviceName": "iPhone 16",
            "platformVersion": "26.5", "udid": "00000000-0000-0000-0000-000000000016",
            "default": False,
        })
        client.post("/api/env/ios/remove", json={
            "mode": "simulator", "deviceName": "iPhone 15",
        })
        saved = json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        sims = saved["ios"]["simulator"]
        assert len(sims) == 1
        assert sims[0]["default"] is True

    def test_returns_400_when_deviceName_missing(self, client, tmp_devices_json):
        """deviceName 없으면 400."""
        res = client.post("/api/env/ios/remove", json={"mode": "simulator"})
        assert res.status_code == 400

    def test_real_device_allows_deletion_to_zero(self, client, tmp_devices_json):
        """iOS 실기기(real_device)는 마지막 1대도 삭제 가능 — 0대 허용."""
        res = client.post("/api/env/ios/remove", json={
            "mode": "real_device", "deviceName": "iPhone 16",
        })
        assert res.status_code == 200
        assert res.json()["ok"] is True
        import json as _json
        saved = _json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        assert saved["ios"]["real_device"] == []

    def test_simulator_empty_section_returns_404_not_400(self, client, tmp_devices_json):
        """시뮬레이터 0개 상태에서 remove 요청 → 404 (기기 없음), 400 아님."""
        import json as _json
        data = _json.loads(tmp_devices_json.read_text(encoding="utf-8"))
        data["ios"]["simulator"] = []
        tmp_devices_json.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")
        res = client.post("/api/env/ios/remove", json={
            "mode": "simulator", "deviceName": "anything",
        })
        assert res.status_code == 404

    def test_ios_remove_returns_403_when_capture_active(self, client, tmp_devices_json):
        """Capture Studio 활성 중 iOS remove → 403 capture_session_active."""
        from unittest.mock import patch as _patch
        with _patch("routes.env.is_capture_active", return_value=True):
            res = client.post("/api/env/ios/remove", json={
                "mode": "simulator", "deviceName": "iPhone 15",
            })
        assert res.status_code == 403
        assert res.json()["error"] == "capture_session_active"

    def test_ios_remove_returns_409_when_pipeline_running(self, client, tmp_devices_json):
        """파이프라인 실행 중 iOS remove → 409 pipeline_running."""
        from unittest.mock import patch as _patch
        with _patch("routes.env.is_capture_active", return_value=False), \
             _patch("routes.env.is_pipeline_active", return_value=True):
            res = client.post("/api/env/ios/remove", json={
                "mode": "simulator", "deviceName": "iPhone 15",
            })
        assert res.status_code == 409
        assert res.json()["error"] == "pipeline_running"

# ── US-3 확장: 중복 409 + auto-fill caps ─────────────────────────────────

class TestAndroidAddDuplicate:

    def test_emulator_requires_platform_version(self, client, tmp_devices_json):
        """Dropping the auto-filled version must not create an incomplete entry."""
        res = client.post("/api/env/android/add", json={
            "mode": "emulator", "deviceName": "Pixel 8", "avd": "Pixel_8_API_35",
        })
        assert res.status_code == 400
        assert res.json()["error"] == "platformVersion is required for emulator"

    def test_emulator_rejects_avd_not_reported_by_sdk(self, client, tmp_devices_json):
        """Hand-written AVD names must never reach a subprocess later."""
        res = client.post("/api/env/android/add", json={
            "mode": "emulator", "deviceName": "Fake", "avd": "Injected_AVD",
            "platformVersion": "15",
        })
        assert res.status_code == 400
        assert res.json()["error"] == "invalid_avd"

    def test_duplicate_avd_returns_409(self, client, tmp_devices_json):
        """같은 avd로 두 번 추가 시 409."""
        client.post("/api/env/android/add", json={
            "mode": "emulator", "deviceName": "Pixel 7",
            "avd": "Pixel_7_API_34", "platformVersion": "14", "default": False,
        })
        res = client.post("/api/env/android/add", json={
            "mode": "emulator", "deviceName": "Pixel_B",
            "avd": "Pixel_7_API_34", "platformVersion": "14", "default": False,
        })
        assert res.status_code == 409
        assert "duplicate" in res.json()["error"]

    def test_duplicate_udid_returns_409(self, client, tmp_devices_json):
        """같은 udid로 두 번 추가 시 409."""
        client.post("/api/env/android/add", json={
            "mode": "real_device", "deviceName": "Dev A",
            "udid": "SERXXX", "default": False,
        })
        res = client.post("/api/env/android/add", json={
            "mode": "real_device", "deviceName": "Dev B",
            "udid": "SERXXX", "default": False,
        })
        assert res.status_code == 409

    def test_emulator_auto_fills_caps(self, client, tmp_devices_json):
        """에뮬레이터 추가 → automationName·MJPEG caps 자동 채움."""
        res = client.post("/api/env/android/add", json={
            "mode": "emulator", "deviceName": "Pixel 8",
            "avd": "Pixel_8_API_35", "platformVersion": "15", "default": False,
        })
        assert res.status_code == 200
        entry = res.json().get("entry", {})
        assert entry == {
            "deviceName": "Pixel 8",
            "platformVersion": "15",
            "avd": "Pixel_8_API_35",
            "automationName": "UiAutomator2",
            "noReset": True,
            "forceAppLaunch": True,
            "shouldTerminateApp": True,
            "mjpegServerPort": 8093,
            "mjpegScalingFactor": 75,
            "mjpegServerScreenshotQuality": 70,
            "appPackage": "",
            "appActivity": "",
            "default": False,
        }

    def test_real_device_auto_fills_automation_name(self, client, tmp_devices_json):
        """실기기 추가 → automationName 자동 채움."""
        res = client.post("/api/env/android/add", json={
            "mode": "real_device", "deviceName": "Galaxy",
            "udid": "GXYABC", "default": False,
        })
        assert res.status_code == 200
        entry = res.json().get("entry", {})
        assert entry.get("automationName") == "UiAutomator2"


class TestIosAddDuplicate:

    def test_simulator_requires_udid_and_platform_version(self, client, tmp_devices_json):
        """The old name-only contract must be rejected before writing config."""
        res = client.post("/api/env/ios/add", json={
            "mode": "simulator", "deviceName": "iPhone 16",
        })
        assert res.status_code == 400
        assert res.json()["error"] == "udid is required for simulator"

    def test_simulator_rejects_invalid_udid(self, client, tmp_devices_json):
        """Malformed UDIDs must not reach simctl or devices.json."""
        res = client.post("/api/env/ios/add", json={
            "mode": "simulator", "deviceName": "iPhone 16",
            "platformVersion": "26.5", "udid": "not-a-udid",
        })
        assert res.status_code == 400
        assert res.json()["error"] == "invalid_udid"

    def test_simulator_rejects_udid_not_reported_by_simctl(self, client, tmp_devices_json):
        """A well-formed but unknown UDID is not selectable."""
        res = client.post("/api/env/ios/add", json={
            "mode": "simulator", "deviceName": "Unknown",
            "platformVersion": "26.5", "udid": "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
        })
        assert res.status_code == 400
        assert res.json()["error"] == "invalid_udid"

    def test_duplicate_simulator_name_returns_409(self, client, tmp_devices_json):
        """같은 deviceName 시뮬레이터 두 번 추가 시 409."""
        client.post("/api/env/ios/add", json={
            "mode": "simulator", "deviceName": "iPhone 99",
            "platformVersion": "26.5", "udid": "00000000-0000-0000-0000-000000000099",
            "default": False,
        })
        res = client.post("/api/env/ios/add", json={
            "mode": "simulator", "deviceName": "iPhone 99",
            "platformVersion": "26.5", "udid": "00000000-0000-0000-0000-000000000099",
            "default": False,
        })
        assert res.status_code == 409
        assert "duplicate" in res.json()["error"]

    def test_duplicate_real_device_udid_returns_409(self, client, tmp_devices_json):
        """같은 udid 실기기 두 번 추가 시 409."""
        client.post("/api/env/ios/add", json={
            "mode": "real_device", "deviceName": "iPhone R1",
            "udid": "UDIDAAA", "default": False,
        })
        res = client.post("/api/env/ios/add", json={
            "mode": "real_device", "deviceName": "iPhone R2",
            "udid": "UDIDAAA", "default": False,
        })
        assert res.status_code == 409

    def test_simulator_auto_fills_automation_name(self, client, tmp_devices_json):
        """시뮬레이터 추가 → automationName 자동 채움."""
        res = client.post("/api/env/ios/add", json={
            "mode": "simulator", "deviceName": "iPhone 17",
            "platformVersion": "26.5", "udid": "00000000-0000-0000-0000-000000000017",
            "default": False,
        })
        assert res.status_code == 200
        entry = res.json().get("entry", {})
        assert entry.get("automationName") == "XCUITest"
        assert entry.get("udid") == "00000000-0000-0000-0000-000000000017"
        assert entry.get("platformVersion") == "26.5"

    def test_real_device_accepts_team_id(self, client, tmp_devices_json):
        """실기기 추가 시 team_id 저장."""
        res = client.post("/api/env/ios/add", json={
            "mode": "real_device", "deviceName": "iPhone Real",
            "udid": "RUID001", "team_id": "TEAM123456", "default": False,
        })
        assert res.status_code == 200
        entry = res.json().get("entry", {})
        assert entry.get("team_id") == "TEAM123456"
        assert entry.get("automationName") == "XCUITest"


# ── Phase 3: WiFi 페어링 ──────────────────────────────────────────────────

class TestAndroidRealPair:

    def test_pair_returns_400_when_ip_missing(self, client, tmp_devices_json):
        """ip 없으면 400."""
        res = client.post("/api/env/android/real/pair", json={"port": "37177", "code": "123456"})
        assert res.status_code == 400
        assert "ip" in res.json()["error"]

    def test_pair_returns_400_when_port_missing(self, client, tmp_devices_json):
        """port 없으면 400."""
        res = client.post("/api/env/android/real/pair", json={"ip": "1.2.3.4", "code": "123456"})
        assert res.status_code == 400
        assert "port" in res.json()["error"]

    def test_pair_returns_400_when_code_missing(self, client, tmp_devices_json):
        """code 없으면 400."""
        res = client.post("/api/env/android/real/pair", json={"ip": "1.2.3.4", "port": "37177"})
        assert res.status_code == 400
        assert "code" in res.json()["error"]

    def test_pair_calls_adb_pair(self, client, tmp_devices_json, monkeypatch):
        """adb pair 명령이 실행된다."""
        calls = []
        def mock_run(cmd, **kwargs):
            calls.append(cmd)
            m = MagicMock()
            m.returncode = 0
            m.stdout = "Successfully paired"
            m.stderr = ""
            return m
        monkeypatch.setattr("routes.env.subprocess.run", mock_run)
        res = client.post("/api/env/android/real/pair", json={
            "ip": "192.168.1.5", "port": "37177", "code": "123456",
        })
        assert res.status_code == 200
        assert res.json()["ok"] is True
        assert Path(calls[0][0]).name == "adb"
        assert calls[0][1:] == ["pair", "192.168.1.5:37177", "123456"]

    def test_pair_returns_403_when_capture_active(self, client, tmp_path, monkeypatch):
        """Capture 세션 활성 시 403."""
        sess = tmp_path / "capture_session.json"
        sess.write_text(json.dumps({"active": True, "platform": "android"}))
        monkeypatch.setattr("utils.state.CAPTURE_SESSION_PATH", sess)
        res = client.post("/api/env/android/real/pair", json={
            "ip": "1.2.3.4", "port": "37177", "code": "123456",
        })
        assert res.status_code == 403


# ── Phase 3: iOS WDA 빌드 ────────────────────────────────────────────────

class TestIosRealWdaBuild:

    def test_wda_build_returns_400_when_udid_missing(self, client, tmp_devices_json):
        """udid 없으면 400."""
        res = client.post("/api/env/ios/real/wda_build", json={"team_id": "ABCD123456"})
        assert res.status_code == 400
        assert "udid" in res.json()["error"]

    def test_wda_build_returns_400_when_team_id_missing(self, client, tmp_devices_json):
        """team_id 없으면 400."""
        res = client.post("/api/env/ios/real/wda_build", json={"udid": "UDID001"})
        assert res.status_code == 400
        assert "team_id" in res.json()["error"]

    def test_wda_build_returns_500_when_wda_not_found(self, client, tmp_devices_json, monkeypatch):
        """WDA 소스가 없으면 500 wda_not_found."""
        monkeypatch.setattr("routes.env.Path.exists", lambda self: False)
        res = client.post("/api/env/ios/real/wda_build", json={
            "udid": "UDID001", "team_id": "ABCD123456",
        })
        assert res.status_code == 500
        assert "not_found" in res.json()["error"]

    def test_wda_build_returns_403_when_ios_capture_active(self, client, tmp_path, monkeypatch):
        """iOS Capture 세션 활성 시 403."""
        sess = tmp_path / "capture_session.json"
        sess.write_text(json.dumps({"active": True, "platform": "ios"}))
        monkeypatch.setattr("utils.state.CAPTURE_SESSION_PATH", sess)
        res = client.post("/api/env/ios/real/wda_build", json={
            "udid": "UDID001", "team_id": "ABCD123456",
        })
        assert res.status_code == 403
