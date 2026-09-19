import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _module():
    path = Path(__file__).parent.parent / "scripts" / "05_execute.py"
    spec = importlib.util.spec_from_file_location("execute_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_html_report_options_are_omitted_when_plugin_is_missing(monkeypatch):
    module = _module()
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)

    assert module._pytest_html_options(Path("report.html")) == []


def test_html_report_options_are_added_when_plugin_exists(monkeypatch):
    module = _module()
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: object())

    assert module._pytest_html_options(Path("report.html")) == [
        "--html=report.html", "--self-contained-html"
    ]


def test_rerun_options_are_omitted_when_single_attempt_is_requested(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "_has_rerun_plugin", lambda: True)

    assert module._pytest_rerun_options(disabled=True) == []


def test_rerun_options_keep_existing_policy_when_enabled(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "_has_rerun_plugin", lambda: True)

    assert module._pytest_rerun_options(disabled=False) == [
        "--reruns", "2", "--reruns-delay", "5"
    ]


def test_run_recording_tracks_device_pid(monkeypatch):
    module = _module()
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if len(args) == 5 and "screenrecord" in args[-1]:
            return SimpleNamespace(returncode=0, stdout="7654\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._start_screen_recording("emulator-5554") == 7654
    assert any("echo $!" in call[-1] for call in calls if len(call) == 5)


def test_run_recording_stop_uses_sigint(monkeypatch, tmp_path):
    module = _module()
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if "kill" in args and "-0" in args:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="pull failed")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    module._stop_and_pull_recording(7654, "emulator-5554", tmp_path / "run.mp4")

    assert any(call[-3:] == ["kill", "-2", "7654"] for call in calls)
    assert not any(call[-3:] == ["kill", "-15", "7654"] for call in calls)
