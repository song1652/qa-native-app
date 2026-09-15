"""Installed Android AVD and iOS simulator discovery contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


DASHBOARD = Path(__file__).parents[3] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

import utils.system as system  # noqa: E402


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def test_list_system_avds_returns_display_name_and_android_release(
    tmp_path, monkeypatch
):
    """A config target change must change the version shown in the add modal."""
    avd_home = tmp_path / "avd"
    avd_home.mkdir()
    avd_dir = avd_home / "Pixel_8_Android16.avd"
    avd_dir.mkdir()
    (avd_home / "Pixel_8_Android16.ini").write_text(
        f"path={avd_dir}\n", encoding="utf-8"
    )
    (avd_dir / "config.ini").write_text(
        "avd.ini.displayname=Pixel 8\ntarget=android-36\n", encoding="utf-8"
    )
    monkeypatch.setenv("ANDROID_AVD_HOME", str(avd_home))

    with patch(
        "utils.system.subprocess.run",
        return_value=_completed("Pixel_8_Android16\n"),
    ):
        result = system.list_system_avds()

    assert result == [
        {
            "avd": "Pixel_8_Android16",
            "deviceName": "Pixel 8",
            "platformVersion": "16",
        }
    ]


def test_list_system_avds_reads_api_from_image_directory(tmp_path, monkeypatch):
    """AVDs without target still expose a correct Android release."""
    avd_home = tmp_path / "avd"
    avd_dir = avd_home / "Pixel_7.avd"
    avd_dir.mkdir(parents=True)
    (avd_home / "Pixel_7.ini").write_text(
        "path.rel=avd/Pixel_7.avd\n", encoding="utf-8"
    )
    (avd_dir / "config.ini").write_text(
        "image.sysdir.1=system-images;android-35;google_apis;arm64-v8a\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANDROID_AVD_HOME", str(avd_home))
    monkeypatch.setenv("ANDROID_USER_HOME", str(tmp_path))

    with patch(
        "utils.system.subprocess.run", return_value=_completed("Pixel_7\n")
    ):
        result = system.list_system_avds()

    assert result[0]["deviceName"] == "Pixel 7"
    assert result[0]["platformVersion"] == "15"


def test_list_system_avds_keeps_avd_usable_when_metadata_is_missing(
    tmp_path, monkeypatch
):
    """A missing config file must not hide an installed AVD from the user."""
    monkeypatch.setenv("ANDROID_AVD_HOME", str(tmp_path / "missing"))
    with patch(
        "utils.system.subprocess.run", return_value=_completed("My_Test_AVD\n")
    ):
        result = system.list_system_avds()

    assert result == [
        {"avd": "My_Test_AVD", "deviceName": "My Test AVD", "platformVersion": ""}
    ]


def test_list_system_avds_surfaces_emulator_command_failure():
    """A broken SDK command must become a visible discovery error, not an empty list."""
    with patch(
        "utils.system.subprocess.run",
        return_value=_completed(stderr="SDK is unavailable", returncode=1),
    ):
        with pytest.raises(RuntimeError, match="SDK is unavailable"):
            system.list_system_avds()


def test_list_system_simulators_joins_devices_to_available_runtime():
    """The dropdown version must come from the runtime owning each simulator."""
    runtime_id = "com.apple.CoreSimulator.SimRuntime.iOS-26-5"
    payload = {
        "devices": {
            runtime_id: [
                {
                    "name": "iPhone 16 Plus",
                    "udid": "A1B2C3D4-E5F6-7890-ABCD-EF1234567890",
                    "state": "Shutdown",
                    "isAvailable": True,
                }
            ]
        },
        "runtimes": [
            {
                "identifier": runtime_id,
                "version": "26.5",
                "isAvailable": True,
            }
        ],
    }
    with patch(
        "utils.system.subprocess.run",
        return_value=_completed(json.dumps(payload)),
    ):
        result = system.list_system_simulators()

    assert result == [
        {
            "deviceName": "iPhone 16 Plus",
            "platformVersion": "26.5",
            "udid": "A1B2C3D4-E5F6-7890-ABCD-EF1234567890",
            "state": "Shutdown",
        }
    ]


def test_list_system_simulators_excludes_unavailable_runtime_and_device():
    """Unavailable simulator records must never be selectable."""
    available_id = "com.apple.CoreSimulator.SimRuntime.iOS-26-5"
    unavailable_id = "com.apple.CoreSimulator.SimRuntime.iOS-18-0"
    payload = {
        "devices": {
            available_id: [
                {
                    "name": "Unavailable Device",
                    "udid": "11111111-1111-1111-1111-111111111111",
                    "state": "Shutdown",
                    "isAvailable": False,
                }
            ],
            unavailable_id: [
                {
                    "name": "Old iPhone",
                    "udid": "22222222-2222-2222-2222-222222222222",
                    "state": "Shutdown",
                    "isAvailable": True,
                }
            ],
        },
        "runtimes": [
            {"identifier": available_id, "version": "26.5", "isAvailable": True},
            {"identifier": unavailable_id, "version": "18.0", "isAvailable": False},
        ],
    }
    with patch(
        "utils.system.subprocess.run",
        return_value=_completed(json.dumps(payload)),
    ):
        result = system.list_system_simulators()

    assert result == []


def test_list_system_simulators_surfaces_invalid_json():
    """Malformed simctl output must be reported as discovery failure."""
    with patch(
        "utils.system.subprocess.run", return_value=_completed("not-json")
    ):
        with pytest.raises(RuntimeError, match="simctl"):
            system.list_system_simulators()

