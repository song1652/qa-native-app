"""Persisted device state is reconciled with adb and simctl runtime state."""
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import patch


DASHBOARD = Path(__file__).parents[3] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

import utils.system as system  # noqa: E402


def _android(section):
    detector = getattr(system, "detect_android_runtime", lambda value: dict(value))
    return detector(section)


def _ios(section):
    detector = getattr(system, "detect_ios_runtime", lambda value: dict(value))
    return detector(section)


def test_android_starting_becomes_running_after_boot_completed():
    def runner(command, **_kwargs):
        if command[-1] == "devices":
            return SimpleNamespace(
                returncode=0,
                stdout="List of devices attached\nemulator-5554\tdevice\n",
                stderr="",
            )
        if command[-3:] == ["emu", "avd", "name"]:
            return SimpleNamespace(returncode=0, stdout="Pixel_7\nOK\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="1\n", stderr="")

    with patch("utils.system.subprocess.run", side_effect=runner):
        result = _android({"status": "starting", "avd": "Pixel_7", "started_at": None})

    assert result["status"] == "running"
    assert result["serial"] == "emulator-5554"


def test_android_timeout_error_recovers_when_emulator_finishes_booting():
    def runner(command, **_kwargs):
        if command[-1] == "devices":
            return SimpleNamespace(
                returncode=0,
                stdout="List of devices attached\nemulator-5554\tdevice\n",
                stderr="",
            )
        if command[-3:] == ["emu", "avd", "name"]:
            return SimpleNamespace(returncode=0, stdout="Pixel_7\nOK\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="1\n", stderr="")

    with patch("utils.system.subprocess.run", side_effect=runner):
        result = _android({
            "status": "error",
            "avd": "Pixel_7",
            "error_msg": "Android 에뮬레이터 부팅 시간이 180초를 초과했습니다.",
            "started_at": "2000-01-01T00:00:00",
        })

    assert result["status"] == "running"
    assert result["error_msg"] is None


def test_android_running_becomes_stopped_when_emulator_disappears():
    no_devices = SimpleNamespace(
        returncode=0, stdout="List of devices attached\n", stderr=""
    )
    with patch("utils.system.subprocess.run", return_value=no_devices):
        result = _android({
            "status": "running",
            "avd": "Pixel_7",
            "serial": "emulator-5554",
            "started_at": "2026-09-14T10:00:00",
        })

    assert result == {
        "status": "stopped",
        "avd": None,
        "serial": None,
        "started_at": None,
    }


def test_android_stopped_does_not_bounce_to_starting_during_shutdown():
    """종료 직후 잠깐 남은 adb transport가 stopped를 starting으로 되돌리지 않는다."""
    def runner(command, **_kwargs):
        if command[-1] == "devices":
            return SimpleNamespace(
                returncode=0,
                stdout="List of devices attached\nemulator-5554\tdevice\n",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="\n", stderr="")

    with patch("utils.system.subprocess.run", side_effect=runner):
        result = _android({
            "status": "stopped",
            "avd": None,
            "serial": None,
            "started_at": None,
        })

    assert result["status"] == "stopped"
    assert result["serial"] is None


def test_android_running_external_emulator_resolves_its_avd_name():
    """A running emulator must light up the matching configured row after refresh."""
    def runner(command, **_kwargs):
        if command[-1] == "devices":
            return SimpleNamespace(
                returncode=0,
                stdout="List of devices attached\nemulator-5554\tdevice\n",
                stderr="",
            )
        if command[-3:] == ["emu", "avd", "name"]:
            return SimpleNamespace(returncode=0, stdout="Pixel_8\nOK\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="1\n", stderr="")

    with patch("utils.system.subprocess.run", side_effect=runner):
        result = _android({
            "status": "stopped", "avd": None, "serial": None, "started_at": None,
        })

    assert result["status"] == "running"
    assert result["serial"] == "emulator-5554"
    assert result["avd"] == "Pixel_8"


def test_android_incomplete_start_without_target_recovers_to_stopped():
    """종료 레이스로 생긴 target 없는 starting 상태를 자동 복구한다."""
    no_devices = SimpleNamespace(
        returncode=0, stdout="List of devices attached\n", stderr=""
    )
    with patch("utils.system.subprocess.run", return_value=no_devices):
        result = _android({
            "status": "starting",
            "avd": None,
            "serial": "emulator-5554",
            "started_at": None,
        })

    assert result["status"] == "stopped"
    assert result["serial"] is None


def test_android_command_failure_preserves_last_known_state():
    with patch("utils.system.subprocess.run", side_effect=OSError("adb unavailable")):
        result = _android({"status": "starting", "avd": "Pixel_7", "started_at": None})

    assert result["status"] == "starting"
    assert result["avd"] == "Pixel_7"


def test_android_starting_times_out_when_no_emulator_appears():
    no_devices = SimpleNamespace(
        returncode=0, stdout="List of devices attached\n", stderr=""
    )
    with patch("utils.system.subprocess.run", return_value=no_devices):
        result = _android({
            "status": "starting",
            "avd": "Pixel_7",
            "started_at": "2000-01-01T00:00:00",
        })

    assert result["status"] == "error"
    assert "180초" in result["error_msg"]


def _simctl_result(state: str):
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps({
            "devices": {
                "com.apple.CoreSimulator.SimRuntime.iOS-27-0": [{
                    "name": "iPhone 18 Pro",
                    "udid": "E73939EF-741D-4A72-BEA7-97D31B15719A",
                    "state": state,
                    "isAvailable": True,
                }]
            }
        }),
        stderr="",
    )


def test_ios_starting_becomes_running_when_simulator_is_booted():
    with patch("utils.system.subprocess.run", return_value=_simctl_result("Booted")):
        result = _ios({
            "status": "starting",
            "simulator": "iPhone 18 Pro",
            "started_at": "2026-09-14T10:00:00",
        })

    assert result["status"] == "running"
    assert result["simulator"] == "iPhone 18 Pro"
    assert result["udid"] == "E73939EF-741D-4A72-BEA7-97D31B15719A"


def test_ios_pending_simctl_command_does_not_start_a_competing_list_command():
    section = {
        "status": "starting",
        "simulator": "iPhone 18 Pro",
        "udid": "E73939EF-741D-4A72-BEA7-97D31B15719A",
        "started_at": datetime.now().isoformat(),
        "_command_pending": True,
    }

    with patch("utils.system.subprocess.run") as runner:
        result = _ios(section)

    runner.assert_not_called()
    assert result == section


def test_ios_timeout_error_recovers_when_simulator_finishes_booting():
    with patch("utils.system.subprocess.run", return_value=_simctl_result("Booted")):
        result = _ios({
            "status": "error",
            "simulator": "iPhone 18 Pro",
            "error_msg": "iOS 시뮬레이터 부팅 시간이 120초를 초과했습니다.",
            "started_at": "2000-01-01T00:00:00",
        })

    assert result["status"] == "running"
    assert result["error_msg"] is None


def test_ios_running_becomes_stopped_when_target_is_shutdown():
    with patch("utils.system.subprocess.run", return_value=_simctl_result("Shutdown")):
        result = _ios({
            "status": "running",
            "simulator": "iPhone 18 Pro",
            "started_at": "2026-09-14T10:00:00",
        })

    assert result == {
        "status": "stopped",
        "simulator": None,
        "udid": None,
        "started_at": None,
    }


def test_ios_stopped_detects_already_booted_configured_simulator():
    with patch("utils.system.subprocess.run", return_value=_simctl_result("Booted")):
        result = _ios({
            "status": "stopped",
            "simulator": None,
            "started_at": None,
        })

    assert result["status"] == "running"
    assert result["simulator"] == "iPhone 18 Pro"


def test_ios_starting_times_out_when_simulator_stays_shutdown():
    with patch("utils.system.subprocess.run", return_value=_simctl_result("Shutdown")):
        result = _ios({
            "status": "starting",
            "simulator": "iPhone 18 Pro",
            "started_at": "2000-01-01T00:00:00",
        })

    assert result["status"] == "error"
    assert "120초" in result["error_msg"]
