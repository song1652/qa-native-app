"""
Unit tests for env_session.json 읽기/쓰기 + 스키마 (M1-05, M1-06).

RED: utils.state.load_env_session / save_env_session 가 아직 없으므로 ImportError.
"""
import json
import sys
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).parents[3] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

from utils.state import (  # noqa: E402
    ENV_SESSION_DEFAULT,
    is_capture_active,
    load_env_session,
    save_capture_session,
    save_env_session,
    update_env_session_sections,
)


class TestEnvSessionSchema:

    def test_default_schema_has_required_top_keys(self):
        """기본 스키마에 appium, android, ios 키가 있어야 한다."""
        schema = ENV_SESSION_DEFAULT
        assert "appium" in schema
        assert "android" in schema
        assert "ios" in schema

    def test_appium_default_has_five_fields(self):
        """appium 기본값에 status, pid, port, error_msg, started_at 포함."""
        a = ENV_SESSION_DEFAULT["appium"]
        assert a["status"] == "stopped"
        assert a["pid"] is None
        assert a["port"] == 4723
        assert a["error_msg"] is None
        assert "started_at" in a

    def test_android_default_has_required_fields(self):
        """android 기본값 확인."""
        android = ENV_SESSION_DEFAULT["android"]
        assert android["status"] == "stopped"
        assert android["avd"] is None

    def test_ios_default_has_required_fields(self):
        """ios 기본값 확인."""
        ios = ENV_SESSION_DEFAULT["ios"]
        assert ios["status"] == "stopped"
        assert ios["simulator"] is None


class TestLoadEnvSession:

    def test_returns_default_when_file_missing(self, tmp_path, monkeypatch):
        """파일 없을 때 기본값 반환."""
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", tmp_path / "env_session.json")
        result = load_env_session()
        assert result["appium"]["status"] == "stopped"
        assert result["appium"]["port"] == 4723

    def test_returns_stored_data_when_file_exists(self, tmp_path, monkeypatch):
        """파일 있을 때 저장된 데이터 반환."""
        session_file = tmp_path / "env_session.json"
        session_file.write_text(json.dumps({
            "appium": {"status": "managed", "pid": 1234, "port": 4723, "error_msg": None, "started_at": None},
            "android": {"status": "stopped", "avd": None, "started_at": None},
            "ios": {"status": "stopped", "simulator": None, "started_at": None},
        }), encoding="utf-8")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        result = load_env_session()
        assert result["appium"]["status"] == "managed"
        assert result["appium"]["pid"] == 1234

    def test_returns_default_when_file_corrupted(self, tmp_path, monkeypatch):
        """파일 깨진 경우 기본값 반환."""
        session_file = tmp_path / "env_session.json"
        session_file.write_text("{ not valid json", encoding="utf-8")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        result = load_env_session()
        assert result["appium"]["status"] == "stopped"

    def test_error_state_preserved_across_loads(self, tmp_path, monkeypatch):
        """error 상태는 로드 후에도 유지되어야 한다 (자동 해소 없음)."""
        session_file = tmp_path / "env_session.json"
        session_file.write_text(json.dumps({
            "appium": {
                "status": "error",
                "pid": None,
                "port": 4723,
                "error_msg": "connection refused",
                "started_at": None,
            },
            "android": {"status": "stopped", "avd": None, "started_at": None},
            "ios": {"status": "stopped", "simulator": None, "started_at": None},
        }), encoding="utf-8")
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        result = load_env_session()
        assert result["appium"]["status"] == "error"
        assert result["appium"]["error_msg"] == "connection refused"


class TestSaveEnvSession:

    def test_save_creates_file(self, tmp_path, monkeypatch):
        """save_env_session이 파일을 생성한다."""
        session_file = tmp_path / "env_session.json"
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        data = dict(ENV_SESSION_DEFAULT)
        save_env_session(data)
        assert session_file.exists()

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        """저장 후 로드하면 동일한 데이터."""
        session_file = tmp_path / "env_session.json"
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        data = {
            "appium": {"status": "managed", "pid": 5678, "port": 4723, "error_msg": None, "started_at": "2026-01-01T00:00:00"},
            "android": {"status": "stopped", "avd": None, "started_at": None},
            "ios": {"status": "stopped", "simulator": None, "started_at": None},
        }
        save_env_session(data)
        loaded = load_env_session()
        assert loaded["appium"]["pid"] == 5678
        assert loaded["appium"]["status"] == "managed"

    def test_conditional_section_update_does_not_overwrite_newer_state(self, tmp_path, monkeypatch):
        """느린 상태 폴링이 더 최신인 버튼 액션 결과를 덮어쓰지 않는다."""
        session_file = tmp_path / "env_session.json"
        monkeypatch.setattr("utils.state.ENV_SESSION_PATH", session_file)
        initial = json.loads(json.dumps(ENV_SESSION_DEFAULT))
        save_env_session(initial)
        newer = {**initial["android"], "status": "starting", "avd": "Pixel_7"}
        update_env_session_sections({"android": newer})

        stale_result = {**initial["android"], "status": "stopped"}
        result = update_env_session_sections(
            {"android": stale_result}, expected={"android": initial["android"]}
        )

        assert result["android"]["status"] == "starting"
        assert load_env_session()["android"]["avd"] == "Pixel_7"


# ── F6: TestIsCaptureActive ──────────────────────────────────────────


class TestIsCaptureActive:
    """is_capture_active(platform) 시그니처 및 동작 검증 (F6)."""

    def _write_capture_session(self, tmp_path, active: bool, platform: str = "") -> None:
        import json
        capture_file = tmp_path / "capture_session.json"
        session = {"active": active}
        if platform:
            session["platform"] = platform
        capture_file.write_text(json.dumps(session), encoding="utf-8")

    def test_returns_false_when_not_active(self, tmp_path, monkeypatch):
        """active=False → 항상 False."""
        self._write_capture_session(tmp_path, active=False, platform="android")
        monkeypatch.setattr("utils.state.CAPTURE_SESSION_PATH", tmp_path / "capture_session.json")
        assert is_capture_active() is False
        assert is_capture_active("android") is False
        assert is_capture_active("ios") is False

    def test_returns_true_when_active_and_no_platform_arg(self, tmp_path, monkeypatch):
        """active=True, platform 인자 없음 → True (전체 확인)."""
        self._write_capture_session(tmp_path, active=True, platform="android")
        monkeypatch.setattr("utils.state.CAPTURE_SESSION_PATH", tmp_path / "capture_session.json")
        assert is_capture_active() is True

    def test_returns_true_when_active_and_platform_matches(self, tmp_path, monkeypatch):
        """active=True, platform 일치 → True."""
        self._write_capture_session(tmp_path, active=True, platform="android")
        monkeypatch.setattr("utils.state.CAPTURE_SESSION_PATH", tmp_path / "capture_session.json")
        assert is_capture_active("android") is True

    def test_returns_false_when_active_but_platform_differs(self, tmp_path, monkeypatch):
        """active=True, platform 불일치 → False."""
        self._write_capture_session(tmp_path, active=True, platform="ios")
        monkeypatch.setattr("utils.state.CAPTURE_SESSION_PATH", tmp_path / "capture_session.json")
        assert is_capture_active("android") is False

    def test_returns_true_when_active_and_platform_is_none(self, tmp_path, monkeypatch):
        """platform=None은 전체 확인 — platform 필드 있어도 True."""
        self._write_capture_session(tmp_path, active=True, platform="ios")
        monkeypatch.setattr("utils.state.CAPTURE_SESSION_PATH", tmp_path / "capture_session.json")
        assert is_capture_active(None) is True

    def test_fallback_when_session_has_no_platform_field(self, tmp_path, monkeypatch):
        """세션에 platform 필드 없으면 (구버전) platform 인자 무시하고 True 반환."""
        self._write_capture_session(tmp_path, active=True, platform="")
        monkeypatch.setattr("utils.state.CAPTURE_SESSION_PATH", tmp_path / "capture_session.json")
        # platform 필드 없는 구버전 세션은 android/ios 인자 모두 True로 fallback
        assert is_capture_active("android") is True
        assert is_capture_active("ios") is True
