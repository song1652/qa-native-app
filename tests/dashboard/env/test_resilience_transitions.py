"""Fault-injected recovery transitions for local virtual-device tooling."""

import json
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import patch


DASHBOARD = Path(__file__).parents[3] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

from utils import system  # noqa: E402


def test_android_emulator_disconnect_then_reconnect_recovers_running_state():
    connected = {"value": True}

    def runner(command, **_kwargs):
        if command[-1] == "devices":
            body = "emulator-5554\tdevice\n" if connected["value"] else ""
            return SimpleNamespace(
                returncode=0, stdout=f"List of devices attached\n{body}", stderr=""
            )
        if command[-3:] == ["emu", "avd", "name"]:
            return SimpleNamespace(returncode=0, stdout="Pixel_7\nOK\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="1\n", stderr="")

    state = {
        "status": "running",
        "avd": "Pixel_7",
        "serial": "emulator-5554",
        "started_at": "2026-09-19T00:00:00",
    }
    with patch("utils.system.subprocess.run", side_effect=runner):
        connected["value"] = False
        stopped = system.detect_android_runtime(state)
        connected["value"] = True
        recovered = system.detect_android_runtime(stopped)

    assert stopped == {
        "status": "stopped",
        "avd": None,
        "serial": None,
        "started_at": None,
    }
    assert recovered["status"] == "running"
    assert recovered["avd"] == "Pixel_7"
    assert recovered["serial"] == "emulator-5554"


def test_ios_simulator_shutdown_then_boot_recovers_running_state():
    booted = {"value": False}

    def runner(_command, **_kwargs):
        state = "Booted" if booted["value"] else "Shutdown"
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "devices": {
                        "runtime": [
                            {
                                "name": "iPhone 18 Pro",
                                "udid": "SIM-1",
                                "state": state,
                                "isAvailable": True,
                            }
                        ]
                    }
                }
            ),
            stderr="",
        )

    state = {
        "status": "running",
        "simulator": "iPhone 18 Pro",
        "udid": "SIM-1",
        "started_at": "2026-09-19T00:00:00",
    }
    with patch("utils.system.subprocess.run", side_effect=runner):
        stopped = system.detect_ios_runtime(state)
        booted["value"] = True
        recovered = system.detect_ios_runtime(stopped)

    assert stopped == {
        "status": "stopped",
        "simulator": None,
        "udid": None,
        "started_at": None,
    }
    assert recovered["status"] == "running"
    assert recovered["simulator"] == "iPhone 18 Pro"
    assert recovered["udid"] == "SIM-1"


def test_appium_managed_process_exit_then_external_restart_is_detected(
    tmp_path, monkeypatch
):
    env_file = tmp_path / "env_session.json"
    env_file.write_text(
        json.dumps(
            {
                "appium": {
                    "status": "managed",
                    "pid": 12345,
                    "port": 4723,
                    "started_at": "2026-09-19T00:00:00",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(system, "ENV_SESSION_PATH", env_file)
    alive = iter([True, False, False])
    reachable = iter([True, False, True])

    with (
        patch.object(system, "_list_installed_appium_drivers", return_value={}),
        patch.object(system, "_http_check_appium", side_effect=lambda _port: next(reachable)),
        patch.object(
            system,
            "_fetch_appium_server_metadata",
            return_value={"version": "3.5.2", "active_sessions": 0},
        ),
    ):
        managed = system.detect_appium_status(process_finder=lambda _pid: next(alive))
        stopped = system.detect_appium_status(process_finder=lambda _pid: next(alive))
        external = system.detect_appium_status(process_finder=lambda _pid: next(alive))

    assert managed["status"] == "managed"
    assert managed["pid"] == 12345
    assert stopped["status"] == "stopped"
    assert stopped["pid"] is None
    assert external["status"] == "external"
    assert external["pid"] is None
