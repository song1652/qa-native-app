"""
Unit tests for save_devices_json() / load_devices_json() (US-3).
"""
import json
import sys
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).parents[3] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

from utils.state import load_devices_json, save_devices_json  # noqa: E402


# ── fixture ───────────────────────────────────────────────────────────

def _make_devices(tmp_path: Path, content: dict) -> Path:
    """tmp_path에 devices.json 작성 후 경로 반환."""
    p = tmp_path / "devices.json"
    p.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


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


# ── TestSaveDevicesJson ───────────────────────────────────────────────

class TestSaveDevicesJson:

    def test_atomic_replace(self, tmp_path, monkeypatch):
        """저장 후 .json.tmp 파일이 남지 않고 devices.json이 정상 기록된다."""
        import utils.state as state_mod
        devices_path = tmp_path / "devices.json"
        monkeypatch.setattr(state_mod, "_DEVICES_PATH", devices_path)

        data = _minimal_devices()
        save_devices_json(data)

        # .tmp 파일 없음
        tmp_file = tmp_path / "devices.json.tmp"
        assert not tmp_file.exists()

        # devices.json 내용 일치
        saved = json.loads(devices_path.read_text(encoding="utf-8"))
        assert saved["android"]["emulator"][0]["deviceName"] == "Pixel_7"

    def test_raises_when_multiple_defaults_android_emulator(self, tmp_path, monkeypatch):
        """android.emulator에 default:true가 2개면 ValueError."""
        import utils.state as state_mod
        monkeypatch.setattr(state_mod, "_DEVICES_PATH", tmp_path / "devices.json")

        data = _minimal_devices()
        data["android"]["emulator"].append(
            {"deviceName": "Pixel_8", "avd": "Pixel_8_API_34", "default": True}
        )
        with pytest.raises(ValueError, match="android.emulator"):
            save_devices_json(data)

    def test_raises_when_multiple_defaults_ios_simulator(self, tmp_path, monkeypatch):
        """ios.simulator에 default:true가 2개면 ValueError."""
        import utils.state as state_mod
        monkeypatch.setattr(state_mod, "_DEVICES_PATH", tmp_path / "devices.json")

        data = _minimal_devices()
        data["ios"]["simulator"].append({"deviceName": "iPhone 16", "default": True})
        with pytest.raises(ValueError, match="ios.simulator"):
            save_devices_json(data)

    def test_preserves_original_on_schema_error(self, tmp_path, monkeypatch):
        """스키마 오류 시 원본 devices.json이 변경되지 않는다."""
        import utils.state as state_mod
        devices_path = tmp_path / "devices.json"
        original = _minimal_devices()
        devices_path.write_text(json.dumps(original), encoding="utf-8")
        monkeypatch.setattr(state_mod, "_DEVICES_PATH", devices_path)

        bad_data = _minimal_devices()
        bad_data["android"]["emulator"].append(
            {"deviceName": "Extra", "avd": "Extra_AVD", "default": True}
        )
        with pytest.raises(ValueError):
            save_devices_json(bad_data)

        # 원본 파일은 그대로
        saved = json.loads(devices_path.read_text(encoding="utf-8"))
        assert len(saved["android"]["emulator"]) == 1

    def test_single_default_per_section_is_valid(self, tmp_path, monkeypatch):
        """각 섹션에 default:true가 1개면 정상 저장."""
        import utils.state as state_mod
        devices_path = tmp_path / "devices.json"
        monkeypatch.setattr(state_mod, "_DEVICES_PATH", devices_path)

        data = _minimal_devices()
        save_devices_json(data)  # 예외 없음

        assert devices_path.exists()

    def test_no_default_in_section_is_valid(self, tmp_path, monkeypatch):
        """default:true 항목이 0개인 섹션도 허용 (검증은 중복만 차단)."""
        import utils.state as state_mod
        devices_path = tmp_path / "devices.json"
        monkeypatch.setattr(state_mod, "_DEVICES_PATH", devices_path)

        data = _minimal_devices()
        data["android"]["emulator"][0]["default"] = False
        save_devices_json(data)  # 예외 없음

        assert devices_path.exists()


class TestLoadDevicesJson:

    def test_returns_dict_when_file_exists(self, tmp_path, monkeypatch):
        """파일이 있으면 dict 반환."""
        import utils.state as state_mod
        devices_path = _make_devices(tmp_path, _minimal_devices())
        monkeypatch.setattr(state_mod, "_DEVICES_PATH", devices_path)

        result = load_devices_json()
        assert isinstance(result, dict)
        assert "android" in result

    def test_returns_empty_dict_when_file_missing(self, tmp_path, monkeypatch):
        """파일이 없으면 빈 dict 반환."""
        import utils.state as state_mod
        monkeypatch.setattr(state_mod, "_DEVICES_PATH", tmp_path / "no_such.json")

        result = load_devices_json()
        assert result == {}


# ── F5: flock + fsync ────────────────────────────────────────────────────

class TestSaveDevicesJsonFlock:

    def test_flock_acquired_and_released(self, tmp_path, monkeypatch):
        """flock이 호출되고 정상 해제된다 (lock 파일 남지 않아도 됨, 파일은 정상 저장)."""
        import utils.state as state_mod
        devices_path = tmp_path / "devices.json"
        monkeypatch.setattr(state_mod, "_DEVICES_PATH", devices_path)

        flock_calls = []
        import fcntl as _fcntl

        original_flock = _fcntl.flock
        def patched_flock(fd, op):
            flock_calls.append(op)
            return original_flock(fd, op)

        monkeypatch.setattr("fcntl.flock", patched_flock)

        save_devices_json(_minimal_devices())

        # LOCK_EX(2) + LOCK_UN(8) 쌍으로 호출됐는지 확인
        assert _fcntl.LOCK_EX in flock_calls
        assert _fcntl.LOCK_UN in flock_calls
        assert devices_path.exists()

    def test_fsync_called_on_write(self, tmp_path, monkeypatch):
        """fsync가 기록 직후 호출된다."""
        import utils.state as state_mod
        import os as _os
        devices_path = tmp_path / "devices.json"
        monkeypatch.setattr(state_mod, "_DEVICES_PATH", devices_path)

        fsync_called = []
        original_fsync = _os.fsync
        def patched_fsync(fd):
            fsync_called.append(fd)
            return original_fsync(fd)

        monkeypatch.setattr("os.fsync", patched_fsync)

        save_devices_json(_minimal_devices())

        assert len(fsync_called) >= 1

    def test_lock_file_cleaned_up(self, tmp_path, monkeypatch):
        """lock 파일이 남아도 다음 저장에서 정상 동작한다."""
        import utils.state as state_mod
        devices_path = tmp_path / "devices.json"
        lock_path = devices_path.with_suffix(".json.lock")
        lock_path.touch()  # lock 파일 미리 생성
        monkeypatch.setattr(state_mod, "_DEVICES_PATH", devices_path)

        save_devices_json(_minimal_devices())
        assert devices_path.exists()
