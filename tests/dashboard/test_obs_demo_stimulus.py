"""Regression tests for best-effort observability demo device stimuli."""
import importlib.util
from pathlib import Path
import subprocess

import pytest


def _load_android_obs_demo_conftest():
    path = (
        Path(__file__).parents[2]
        / "tests"
        / "generated"
        / "android"
        / "obs_demo"
        / "conftest.py"
    )
    spec = importlib.util.spec_from_file_location("android_obs_demo_conftest", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_android_demo_stimulus_timeout_does_not_change_test_outcome(monkeypatch):
    """A slow ADB animation must not add a fixture ERROR to intentional results."""
    module = _load_android_obs_demo_conftest()
    monkeypatch.setenv("DEVICE_UDID", "emulator-5554")
    monkeypatch.setattr(module.shutil, "which", lambda _name: "/opt/homebrew/bin/adb")

    def time_out(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, timeout=5)

    monkeypatch.setattr(module.subprocess, "run", time_out)
    fixture = module.exercise_emulator_screen.__wrapped__()

    next(fixture)
    with pytest.raises(StopIteration):
        next(fixture)
