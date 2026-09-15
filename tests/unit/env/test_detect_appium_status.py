"""
Unit tests for detect_appium_status() DI 구조 (M1-02).

RED: utils.system.detect_appium_status 가 아직 없으므로 ImportError로 실패.
"""
import json
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

DASHBOARD = Path(__file__).parents[3] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

from utils.system import _list_installed_appium_drivers, detect_appium_status  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_driver_cache(monkeypatch):
    monkeypatch.setattr("utils.system._APPIUM_DRIVER_CACHE", None, raising=False)
    monkeypatch.setattr("utils.system._APPIUM_SESSIONS_SUPPORT", {}, raising=False)


# ── 헬퍼 ─────────────────────────────────────────────────────────

def _write_env_session(tmp_path: Path, appium_status: str, pid=None, error_msg=None) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)
    data = {
        "appium": {
            "status": appium_status,
            "pid": pid,
            "port": 4723,
            "error_msg": error_msg,
            "started_at": None,
        },
        "android": {"status": "stopped", "avd": None, "started_at": None},
        "ios": {"status": "stopped", "simulator": None, "started_at": None},
    }
    (state_dir / "env_session.json").write_text(
        json.dumps(data), encoding="utf-8"
    )


# ── 테스트 ────────────────────────────────────────────────────────

class TestDetectAppiumStatus:

    def test_appium_three_sessions_404_is_not_retried_on_every_poll(
        self, tmp_path, monkeypatch
    ):
        """Unsupported Appium 3 routes must not flood its log every three seconds."""
        monkeypatch.setattr(
            "utils.system.ENV_SESSION_PATH", tmp_path / "state" / "env_session.json"
        )
        calls = {"sessions": 0}

        class _Response:
            def read(self):
                return json.dumps({"value": {"build": {"version": "3.5.2"}}}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def urlopen(url, timeout=2):
            if str(url).endswith("/sessions"):
                calls["sessions"] += 1
                raise urllib.error.HTTPError(str(url), 404, "Not Found", {}, None)
            return _Response()

        driver_result = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch("utils.system._http_check_appium", return_value=True), \
                patch("urllib.request.urlopen", side_effect=urlopen), \
                patch("utils.system.subprocess.run", return_value=driver_result):
            first = detect_appium_status(process_finder=lambda _pid: False)
            second = detect_appium_status(process_finder=lambda _pid: False)

        assert first["active_sessions"] == 0
        assert second["active_sessions"] == 0
        assert calls["sessions"] == 1

    def test_driver_discovery_is_cached_between_short_status_polls(self):
        """3초 상태 폴링마다 느린 Appium CLI를 다시 실행하지 않아야 한다."""
        installed = SimpleNamespace(
            returncode=0,
            stdout="uiautomator2 [installed]\nxcuitest [installed]",
            stderr="",
        )
        missing = SimpleNamespace(returncode=1, stdout="", stderr="missing")
        with patch("utils.system.time.monotonic", side_effect=[100.0, 105.0]), \
                patch("utils.system.subprocess.run", side_effect=[installed, missing]):
            first = _list_installed_appium_drivers()
            second = _list_installed_appium_drivers()

        assert first == {"uiautomator2": True, "xcuitest": True}
        assert second == {"uiautomator2": True, "xcuitest": True}

    def test_driver_discovery_uses_resolved_appium_binary(self, monkeypatch):
        """웹 서버 PATH와 무관하게 shared에서 찾은 Appium으로 드라이버를 조회한다."""
        monkeypatch.setattr("utils.system.APPIUM_BIN", "/nvm/bin/appium", raising=False)

        def runner(command, **_kwargs):
            if command[0] != "/nvm/bin/appium":
                raise FileNotFoundError(command[0])
            return SimpleNamespace(
                returncode=0,
                stdout="uiautomator2 [installed]\nxcuitest [installed]",
                stderr="",
            )

        with patch("utils.system.subprocess.run", side_effect=runner):
            result = _list_installed_appium_drivers()

        assert result == {"uiautomator2": True, "xcuitest": True}

    def test_driver_discovery_parses_appium_three_stderr_output(self):
        """Appium 3.5는 설치 목록을 stderr에 출력하므로 두 스트림을 모두 읽는다."""
        appium_three = SimpleNamespace(
            returncode=0,
            stdout="",
            stderr=(
                "- Listing installed drivers\n"
                "- uiautomator2@7.6.2 [installed (npm)]\n"
                "- xcuitest@12.12.1 [installed (npm)]\n"
            ),
        )
        with patch("utils.system.subprocess.run", return_value=appium_three):
            result = _list_installed_appium_drivers()

        assert result == {"uiautomator2": True, "xcuitest": True}

    def test_driver_discovery_adds_nvm_node_directory_to_process_path(self, monkeypatch):
        """절대경로 Appium의 env-node shebang도 GUI 서버에서 실행돼야 한다."""
        monkeypatch.setattr(
            "utils.system.APPIUM_BIN",
            "/Users/qa/.nvm/versions/node/v24.13.0/bin/appium",
        )

        def runner(_command, **kwargs):
            if not kwargs.get("env", {}).get("PATH", "").startswith(
                "/Users/qa/.nvm/versions/node/v24.13.0/bin:"
            ):
                return SimpleNamespace(
                    returncode=127, stdout="", stderr="env: node: No such file"
                )
            return SimpleNamespace(
                returncode=0,
                stdout="",
                stderr="uiautomator2 [installed]\nxcuitest [installed]",
            )

        with patch("utils.system.subprocess.run", side_effect=runner):
            result = _list_installed_appium_drivers()

        assert result == {"uiautomator2": True, "xcuitest": True}

    def test_managed_status_includes_user_visible_server_metadata(self, tmp_path, monkeypatch):
        """관리 중 카드가 버전·세션·드라이버·업타임 정보를 표시할 수 있어야 한다."""
        _write_env_session(tmp_path, "managed", pid=9999)
        session_path = tmp_path / "state" / "env_session.json"
        session = json.loads(session_path.read_text(encoding="utf-8"))
        session["appium"]["started_at"] = "2026-09-14T10:00:00"
        session_path.write_text(json.dumps(session), encoding="utf-8")
        monkeypatch.setattr("utils.system.ENV_SESSION_PATH", session_path)

        class _Response:
            def __init__(self, payload):
                self._payload = json.dumps(payload).encode("utf-8")

            def read(self):
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def _urlopen(url, timeout=2):
            if str(url).endswith("/sessions"):
                return _Response({"value": [{"id": "one"}, {"id": "two"}]})
            return _Response({"value": {"build": {"version": "3.1.2"}}})

        driver_result = SimpleNamespace(
            returncode=0,
            stdout='- uiautomator2@5.0.0 [installed]\n- xcuitest@10.0.0 [installed]\n',
            stderr="",
        )
        with patch("utils.system._http_check_appium", return_value=True), \
                patch("urllib.request.urlopen", side_effect=_urlopen), \
                patch("utils.system.subprocess.run", return_value=driver_result):
            result = detect_appium_status(process_finder=lambda _pid: True)

        assert result["version"] == "3.1.2"
        assert result["active_sessions"] == 2
        assert result["drivers"] == {"uiautomator2": True, "xcuitest": True}
        assert isinstance(result["uptime_seconds"], int)
        assert result["uptime_seconds"] >= 0

    def test_metadata_failures_keep_five_state_result_with_safe_defaults(self, tmp_path, monkeypatch):
        """정보 조회 실패가 Appium의 핵심 상태 판정을 깨뜨리면 안 된다."""
        monkeypatch.setattr("utils.system.ENV_SESSION_PATH", tmp_path / "state" / "env_session.json")
        failed_driver_result = SimpleNamespace(returncode=1, stdout="", stderr="not found")
        with patch("utils.system._http_check_appium", return_value=True), \
                patch("urllib.request.urlopen", side_effect=OSError("offline")), \
                patch("utils.system.subprocess.run", return_value=failed_driver_result):
            result = detect_appium_status(process_finder=lambda _pid: False)

        assert result["status"] == "external"
        assert result["version"] is None
        assert result["active_sessions"] == 0
        assert result["drivers"] == {"uiautomator2": False, "xcuitest": False}
        assert result["uptime_seconds"] is None

    def test_stopped_when_no_session_file_and_not_reachable(self, tmp_path, monkeypatch):
        """env_session.json 없고 HTTP 불가 → stopped."""
        monkeypatch.setattr("utils.system.ENV_SESSION_PATH", tmp_path / "state" / "env_session.json")
        with patch("utils.system._http_check_appium", return_value=False):
            result = detect_appium_status(process_finder=lambda pid: False)
        assert result["status"] == "stopped"
        assert result["pid"] is None
        assert result["port"] == 4723

    def test_external_when_reachable_but_no_managed_pid(self, tmp_path, monkeypatch):
        """HTTP 응답하지만 우리가 관리하는 PID 없음 → external."""
        monkeypatch.setattr("utils.system.ENV_SESSION_PATH", tmp_path / "state" / "env_session.json")
        with patch("utils.system._http_check_appium", return_value=True):
            result = detect_appium_status(process_finder=lambda pid: False)
        assert result["status"] == "external"
        assert result["pid"] is None

    def test_managed_when_pid_alive_and_reachable(self, tmp_path, monkeypatch):
        """관리 PID 살아있고 HTTP 응답 → managed."""
        _write_env_session(tmp_path, "managed", pid=9999)
        monkeypatch.setattr("utils.system.ENV_SESSION_PATH", tmp_path / "state" / "env_session.json")
        with patch("utils.system._http_check_appium", return_value=True):
            result = detect_appium_status(process_finder=lambda pid: True)
        assert result["status"] == "managed"
        assert result["pid"] == 9999

    def test_starting_when_pid_alive_but_not_reachable(self, tmp_path, monkeypatch):
        """관리 PID 살아있지만 HTTP 불가 → starting."""
        _write_env_session(tmp_path, "starting", pid=9999)
        monkeypatch.setattr("utils.system.ENV_SESSION_PATH", tmp_path / "state" / "env_session.json")
        with patch("utils.system._http_check_appium", return_value=False):
            result = detect_appium_status(process_finder=lambda pid: True)
        assert result["status"] == "starting"
        assert result["pid"] == 9999

    def test_starting_becomes_error_after_thirty_seconds(self, tmp_path, monkeypatch):
        """HTTP 준비가 30초를 넘으면 무한 스피너 대신 다시 시도 가능한 오류가 된다."""
        _write_env_session(tmp_path, "starting", pid=9999)
        session_path = tmp_path / "state" / "env_session.json"
        session = json.loads(session_path.read_text(encoding="utf-8"))
        session["appium"]["started_at"] = "2000-01-01T00:00:00"
        session_path.write_text(json.dumps(session), encoding="utf-8")
        monkeypatch.setattr("utils.system.ENV_SESSION_PATH", session_path)
        with patch("utils.system._http_check_appium", return_value=False):
            result = detect_appium_status(process_finder=lambda pid: True)

        assert result["status"] == "error"
        assert "30초" in result["error_msg"]

    def test_error_state_persists_regardless_of_http(self, tmp_path, monkeypatch):
        """env_session error 상태 → HTTP 응답해도 error 유지 (자동 해소 없음)."""
        _write_env_session(tmp_path, "error", error_msg="Appium failed to start")
        monkeypatch.setattr("utils.system.ENV_SESSION_PATH", tmp_path / "state" / "env_session.json")
        with patch("utils.system._http_check_appium", return_value=True):
            result = detect_appium_status(process_finder=lambda pid: True)
        assert result["status"] == "error"
        assert result["error_msg"] == "Appium failed to start"

    def test_port_defaults_to_4723(self, tmp_path, monkeypatch):
        """포트 기본값 4723 반환."""
        monkeypatch.setattr("utils.system.ENV_SESSION_PATH", tmp_path / "state" / "env_session.json")
        with patch("utils.system._http_check_appium", return_value=False):
            result = detect_appium_status(process_finder=lambda pid: False)
        assert result["port"] == 4723

    def test_status_is_one_of_five_values(self, tmp_path, monkeypatch):
        """반환 status는 5개 값 중 하나여야 한다."""
        monkeypatch.setattr("utils.system.ENV_SESSION_PATH", tmp_path / "state" / "env_session.json")
        valid = {"stopped", "starting", "managed", "external", "error"}
        with patch("utils.system._http_check_appium", return_value=False):
            result = detect_appium_status(process_finder=lambda pid: False)
        assert result["status"] in valid

    def test_pid_cleared_when_managed_process_dies(self, tmp_path, monkeypatch):
        """관리 PID가 죽으면 stopped로 전이하고 pid None."""
        _write_env_session(tmp_path, "managed", pid=9999)
        monkeypatch.setattr("utils.system.ENV_SESSION_PATH", tmp_path / "state" / "env_session.json")
        with patch("utils.system._http_check_appium", return_value=False):
            result = detect_appium_status(process_finder=lambda pid: False)
        assert result["status"] == "stopped"
        assert result["pid"] is None
