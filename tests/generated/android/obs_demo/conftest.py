"""Real-device stimulus for the execution-observability E2E demo.

The demo test bodies intentionally avoid Appium.  A short pair of swipes keeps the
emulator video stream non-static so Android's screenrecord encoder emits more
than its initial frame; failures still come exclusively from the demo tests.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest


def _run_best_effort(command):
    """Drive visible emulator motion without changing the demo test outcome."""
    try:
        subprocess.run(
            command,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pass


@pytest.fixture(autouse=True)
def exercise_emulator_screen():
    adb = shutil.which("adb")
    udid = os.environ.get("DEVICE_UDID", "").strip()
    if not adb or not udid:
        yield
        return
    setup_commands = (
        [adb, "-s", udid, "shell", "am", "start", "-a", "android.settings.SETTINGS"],
        [adb, "-s", udid, "shell", "input", "swipe", "500", "1200", "500", "400", "500"],
        [adb, "-s", udid, "shell", "input", "swipe", "500", "400", "500", "1200", "500"],
    )
    teardown_commands = (
        [adb, "-s", udid, "shell", "input", "swipe", "500", "1200", "500", "400", "500"],
        [adb, "-s", udid, "shell", "input", "swipe", "500", "400", "500", "1200", "500"],
    )
    for command in setup_commands:
        _run_best_effort(command)
    yield
    for command in teardown_commands:
        _run_best_effort(command)
