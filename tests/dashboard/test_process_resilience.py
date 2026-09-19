"""Process registry recovery without touching user-owned processes."""

import json
from pathlib import Path
import subprocess
import sys


DASHBOARD = Path(__file__).parents[2] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

import shared  # noqa: E402


def test_restore_running_process_keeps_test_owned_live_pid(tmp_path, monkeypatch):
    registry = tmp_path / "running_procs.json"
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    registry.write_text(json.dumps({"execute:android": child.pid}), encoding="utf-8")
    monkeypatch.setattr(shared, "_RUNNING_PIDS_PATH", registry)
    monkeypatch.setattr(shared, "_running", {})

    try:
        result = shared.restore_running_procs()

        assert result == {"restored": ["execute:android"], "discarded": []}
        assert shared._running["execute:android"].poll() is None
        assert json.loads(registry.read_text(encoding="utf-8")) == {
            "execute:android": child.pid
        }
    finally:
        child.terminate()
        child.wait(timeout=5)


def test_restore_running_process_discards_dead_pid_and_rewrites_registry(
    tmp_path, monkeypatch
):
    registry = tmp_path / "running_procs.json"
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=5)
    registry.write_text(json.dumps({"execute:ios": child.pid}), encoding="utf-8")
    monkeypatch.setattr(shared, "_RUNNING_PIDS_PATH", registry)
    monkeypatch.setattr(shared, "_running", {})

    result = shared.restore_running_procs()

    assert result == {"restored": [], "discarded": ["execute:ios"]}
    assert shared._running == {}
    assert json.loads(registry.read_text(encoding="utf-8")) == {}
