"""
Unit tests for check_android_real_devices / check_ios_real_devices / _get_wifi_serial (M3.0).
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

DASHBOARD = Path(__file__).parents[3] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

from utils.system import check_android_real_devices, check_ios_real_devices  # noqa: E402
from routes.env import _get_wifi_serial  # noqa: E402


# ── Android ───────────────────────────────────────────────────────

class TestCheckAndroidRealDevices:

    def test_returns_connected_true_when_serial_in_adb(self, monkeypatch):
        """adb devices 출력에 serial 있으면 connected=True."""
        adb_output = "List of devices attached\nR3CN90YGLAP\tdevice\n"

        def fake_run(cmd, **kwargs):
            class R:
                stdout = adb_output
                returncode = 0
            return R()

        monkeypatch.setattr("subprocess.run", fake_run)
        result = check_android_real_devices(["R3CN90YGLAP"])
        assert result == {"R3CN90YGLAP": True}

    def test_returns_connected_false_when_serial_not_in_adb(self, monkeypatch):
        """adb devices 출력에 serial 없으면 connected=False."""
        adb_output = "List of devices attached\n"

        def fake_run(cmd, **kwargs):
            class R:
                stdout = adb_output
                returncode = 0
            return R()

        monkeypatch.setattr("subprocess.run", fake_run)
        result = check_android_real_devices(["R3CN90YGLAP"])
        assert result == {"R3CN90YGLAP": False}

    def test_returns_false_when_adb_fails(self, monkeypatch):
        """adb 실행 실패해도 connected=False 반환 (예외 없음)."""
        def fake_run(cmd, **kwargs):
            raise OSError("adb not found")

        monkeypatch.setattr("subprocess.run", fake_run)
        result = check_android_real_devices(["SOME_SERIAL"])
        assert result == {"SOME_SERIAL": False}

    def test_empty_serial_returns_false(self, monkeypatch):
        """빈 serial은 연결 안된 것으로 처리."""
        adb_output = "List of devices attached\nR3CN90YGLAP\tdevice\n"

        def fake_run(cmd, **kwargs):
            class R:
                stdout = adb_output
                returncode = 0
            return R()

        monkeypatch.setattr("subprocess.run", fake_run)
        result = check_android_real_devices([""])
        assert result == {"": False}

    def test_multiple_serials(self, monkeypatch):
        """여러 serial 중 일부만 연결된 경우."""
        adb_output = "List of devices attached\nSERIAL_A\tdevice\n"

        def fake_run(cmd, **kwargs):
            class R:
                stdout = adb_output
                returncode = 0
            return R()

        monkeypatch.setattr("subprocess.run", fake_run)
        result = check_android_real_devices(["SERIAL_A", "SERIAL_B"])
        assert result == {"SERIAL_A": True, "SERIAL_B": False}

    def test_empty_list_returns_empty_dict(self, monkeypatch):
        """serial 목록이 비어있으면 빈 dict 반환."""
        monkeypatch.setattr("subprocess.run", lambda *a, **k: None)
        result = check_android_real_devices([])
        assert result == {}


# ── iOS ──────────────────────────────────────────────────────────

class TestCheckIosRealDevices:

    def test_returns_connected_true_when_udid_found(self, monkeypatch):
        """xcrun 출력에 udid 있으면 connected=True."""
        xcrun_output = (
            "Known Devices:\n"
            "iPhone 16 (00008130-001234ABCDE12345) [physicalDevice]\n"
        )

        def fake_run(cmd, **kwargs):
            class R:
                stdout = xcrun_output
                stderr = ""
                returncode = 0
            return R()

        monkeypatch.setattr("subprocess.run", fake_run)
        result = check_ios_real_devices(["00008130-001234ABCDE12345"])
        assert result == {"00008130-001234ABCDE12345": True}

    def test_returns_false_when_udid_not_in_output(self, monkeypatch):
        """xcrun 출력에 udid 없으면 connected=False."""
        xcrun_output = "Known Devices:\n"

        def fake_run(cmd, **kwargs):
            class R:
                stdout = xcrun_output
                stderr = ""
                returncode = 0
            return R()

        monkeypatch.setattr("subprocess.run", fake_run)
        result = check_ios_real_devices(["SOME-UDID-1234"])
        assert result == {"SOME-UDID-1234": False}

    def test_returns_false_when_command_fails(self, monkeypatch):
        """xcrun 실행 실패해도 connected=False 반환 (예외 없음)."""
        def fake_run(cmd, **kwargs):
            raise OSError("xcrun not found")

        monkeypatch.setattr("subprocess.run", fake_run)
        result = check_ios_real_devices(["SOME-UDID"])
        assert result == {"SOME-UDID": False}

    def test_empty_udid_returns_false(self, monkeypatch):
        """빈 udid는 연결 안된 것으로 처리."""
        xcrun_output = "Known Devices:\nSomething (ABCD1234) [physicalDevice]\n"

        def fake_run(cmd, **kwargs):
            class R:
                stdout = xcrun_output
                stderr = ""
                returncode = 0
            return R()

        monkeypatch.setattr("subprocess.run", fake_run)
        result = check_ios_real_devices([""])
        assert result == {"": False}

    def test_empty_list_returns_empty_dict(self, monkeypatch):
        """udid 목록이 비어있으면 빈 dict 반환."""
        monkeypatch.setattr("subprocess.run", lambda *a, **k: None)
        result = check_ios_real_devices([])
        assert result == {}


# ── _get_wifi_serial ──────────────────────────────────────────────

class TestGetWifiSerial:

    def test_returns_ip_port_when_wifi_ip_set(self, monkeypatch):
        """wifi_ip가 설정된 기기 → ip:5555 형태 반환."""
        with patch("routes.env.get_default_device", return_value={"wifi_ip": "192.168.1.100"}):
            result = _get_wifi_serial()
        assert result == "192.168.1.100:5555"

    def test_returns_none_when_wifi_ip_empty(self, monkeypatch):
        """wifi_ip가 빈 문자열 → None 반환."""
        with patch("routes.env.get_default_device", return_value={"wifi_ip": ""}):
            result = _get_wifi_serial()
        assert result is None

    def test_returns_none_when_wifi_ip_missing(self, monkeypatch):
        """wifi_ip 키 자체가 없을 때 → None 반환."""
        with patch("routes.env.get_default_device", return_value={"deviceName": "Galaxy S24"}):
            result = _get_wifi_serial()
        assert result is None

    def test_returns_none_when_device_not_found(self, monkeypatch):
        """get_default_device가 None 반환할 때 → None 반환."""
        with patch("routes.env.get_default_device", return_value=None):
            result = _get_wifi_serial()
        assert result is None
