"""iOS Simulator stimulus for the execution-observability E2E demo.

The demo assertions are deterministic and do not require Appium. When a
simulator UDID is provided, Settings is launched so video and screenshots show
a real iOS screen while the observability hooks collect evidence.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest


@pytest.fixture(autouse=True)
def show_ios_settings_screen():
    xcrun = shutil.which("xcrun")
    udid = os.environ.get("DEVICE_UDID", "").strip()
    if not xcrun or not udid:
        yield
        return

    subprocess.run(
        [xcrun, "simctl", "launch", udid, "com.apple.Preferences"],
        capture_output=True,
        timeout=15,
        check=False,
    )
    yield
