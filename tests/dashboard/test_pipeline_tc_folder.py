from agents.dashboard.routes.pipeline import _pipeline_steps, _tc_folder_args
from agents.dashboard.shared import SCRIPT_MAP


def test_pipeline_scopes_generation_and_execution_to_selected_group():
    assert _tc_folder_args("generate", "android", "location") == [
        "--tc-dir", "android/location"
    ]
    assert _tc_folder_args("execute", "android", "location") == [
        "--tc-dir", "location"
    ]
    assert _tc_folder_args("lint", "android", "location") == []


def test_pipeline_scopes_platform_root_without_including_child_groups():
    assert _tc_folder_args("generate", "android", "__root__") == [
        "--tc-dir", "android", "--tc-root-only"
    ]
    assert _tc_folder_args("execute", "android", "__root__") == [
        "--tc-root-only"
    ]


def test_tc_studio_pipeline_starts_from_exported_markdown():
    assert _pipeline_steps(from_tc_studio=True) == ["generate", "lint", "execute"]
    assert _pipeline_steps(from_tc_studio=False) == ["analyze", "generate", "lint", "execute"]


def test_lint_step_reports_selected_platform():
    assert SCRIPT_MAP["lint"][1] == ["--platform", "{platform}"]


def test_pipeline_exposes_batch_completion_status(monkeypatch):
    from fastapi.testclient import TestClient
    from agents.dashboard.serve import app
    from routes import pipeline

    batch = {"done": False, "ok": True, "folder_index": 0,
             "folder_count": 2, "step": "execute", "log": "run_execute.txt"}
    monkeypatch.setitem(pipeline._pipeline_batches, "review-run", batch)
    client = TestClient(app)

    response = client.get("/api/run_all/status/review-run")
    assert response.status_code == 200
    assert response.json()["folder_count"] == 2
    assert response.json()["done"] is False
    batch["folder_index"] = 1
    batch["done"] = True
    assert client.get("/api/run_all/status/review-run").json()["done"] is True


def test_serial_run_stays_active_until_second_folder_finishes(monkeypatch, tmp_path):
    import threading
    from fastapi.testclient import TestClient
    from agents.dashboard.serve import app
    from routes import pipeline

    entered_second_execute = threading.Event()
    release_second_execute = threading.Event()
    calls = []

    class FakeProcess:
        returncode = 0
        pid = 99999

        def __init__(self, command, **_kwargs):
            self.command = command
            calls.append(command)

        def wait(self, timeout=None):
            if "05_execute.py" in self.command[2] and "second" in self.command:
                entered_second_execute.set()
                assert release_second_execute.wait(3)
            return 0

        def poll(self):
            return self.returncode

    monkeypatch.setattr(pipeline, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "_SERIAL_FOLDER_GAP_SECONDS", 0)
    monkeypatch.setattr(pipeline, "list_tc_folders", lambda _platform: ["first", "second"])
    monkeypatch.setattr(pipeline, "is_capture_active", lambda _platform: False)
    monkeypatch.setattr(pipeline, "read_state", lambda: {"execute_results": {"summary": {"failed": 0}}})
    monkeypatch.setattr(pipeline, "save_state", lambda _state: None)
    monkeypatch.setattr(pipeline, "save_running_pids", lambda: None)
    monkeypatch.setattr(pipeline, "_purge_old_runs", lambda: None)
    monkeypatch.setattr(pipeline, "_broadcast_run_summary", lambda *_args: None)
    monkeypatch.setattr(pipeline, "broadcast_timeline_sync", lambda *_args: None)
    monkeypatch.setattr(pipeline, "_build_run_env", lambda *_args: {"QA_OBS_KEEP": "none"})
    monkeypatch.setattr(pipeline.subprocess, "Popen", FakeProcess)

    client = TestClient(app)
    response = client.post("/api/run_all", json={
        "platform": "android", "tc_folders": ["first", "second"],
        "from_tc_studio": True,
    })
    assert response.status_code == 200 and response.json()["ok"]
    batch_id = response.json()["batch_id"]
    try:
        assert entered_second_execute.wait(3)
        running = client.get(f"/api/run_all/status/{batch_id}").json()
        assert running["folder_index"] == 1
        assert running["done"] is False
    finally:
        release_second_execute.set()
    for _ in range(100):
        finished = client.get(f"/api/run_all/status/{batch_id}").json()
        if finished["done"]:
            break
    assert finished["done"] is True and finished["ok"] is True
    assert sum("02_generate.py" in command[2] for command in calls) == 2
