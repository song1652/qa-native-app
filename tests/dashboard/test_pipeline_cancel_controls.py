"""Cancellation never reaches real processes, state, logs or devices."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from agents.dashboard.routes import pipeline


@pytest.mark.parametrize('action', ['reset', 'cancel'])
@pytest.mark.parametrize('when', ['queued', 'running', 'between_folders'])
def test_stop_prevents_queued_batch_from_starting_next_folder(monkeypatch, tmp_path, action, when):
    targets, spawned, stopped, signals, gap_responses = [], [], [], [], []
    class Thread:
        def __init__(self, target, **_kwargs):
            targets.append(target)
        def start(self):
            pass
    class Process:
        pid = 123456
        returncode = 0
        def __init__(self, command, **_kwargs):
            self.finished = False
            spawned.append(command)
        def wait(self):
            if when == 'running' and not stopped:
                stopped.append(True)
                if action == 'reset':
                    client.post('/api/reset')
                else:
                    client.post('/api/cancel', json={'step': 'generate'})
                self.returncode = -15
            self.finished = True
            return self.returncode
        def poll(self):
            return self.returncode if self.finished else None
        def terminate(self):
            signals.append('terminate')
            self.returncode = -15
    monkeypatch.setattr(pipeline, '_running', {})
    monkeypatch.setattr(pipeline, '_test_runs', {})
    monkeypatch.setattr(pipeline, '_pipeline_batches', {})
    monkeypatch.setattr(pipeline, 'LOGS_DIR', tmp_path)
    monkeypatch.setattr(pipeline, 'list_tc_folders', lambda _: ['one', 'two'])
    monkeypatch.setattr(pipeline, 'is_capture_active', lambda _: False)
    monkeypatch.setattr(pipeline, 'read_state', lambda: {'execute_results': {'summary': {'failed': 0}}})
    monkeypatch.setattr(pipeline, 'save_state', lambda _: None)
    monkeypatch.setattr(pipeline, 'save_running_pids', lambda: None)
    monkeypatch.setattr(pipeline, 'broadcast_timeline_sync', lambda _: None)
    monkeypatch.setattr(pipeline, '_purge_old_runs', lambda: None)
    monkeypatch.setattr(pipeline, '_broadcast_run_summary', lambda *_: None)
    monkeypatch.setattr(pipeline, '_build_run_env', lambda *_: {'QA_OBS_KEEP': 'always'})
    monkeypatch.setattr(pipeline, '_SERIAL_FOLDER_GAP_SECONDS', 12345 if when == 'between_folders' else 0)
    import time
    original_sleep = time.sleep
    def sleep(seconds):
        if seconds == 12345:
            stopped.append(True)
            response = client.post('/api/reset' if action == 'reset' else '/api/cancel', json={'step': 'execute'})
            gap_responses.append(response.status_code)
        elif seconds:
            original_sleep(seconds)
    monkeypatch.setattr(time, 'sleep', sleep)
    from types import SimpleNamespace
    monkeypatch.setattr(pipeline, 'threading', SimpleNamespace(Thread=Thread))
    monkeypatch.setattr(pipeline.subprocess, 'Popen', Process)
    monkeypatch.setattr(pipeline.os, 'getpgid', lambda pid: pid)
    monkeypatch.setattr(pipeline.os, 'killpg', lambda *_: signals.append('killpg'))
    app = FastAPI()
    app.include_router(pipeline.router)
    client = TestClient(app)
    response = client.post('/api/run_all', json={'platform': 'android', 'tc_folders': ['one', 'two'], 'from_tc_studio': True})
    batch_id = response.json()['batch_id']
    if when == 'queued' and action == 'reset':
        client.post('/api/reset')
    elif when == 'queued':
        pipeline._pipeline_batches[batch_id]['step'] = 'generate'
        client.post('/api/cancel', json={'step': 'generate'})
    targets[0]()
    if when == 'between_folders':
        assert gap_responses == [200]
    assert len(spawned) == {'queued':0, 'running':1, 'between_folders':3}[when]
    assert pipeline._pipeline_batches[batch_id]['done'] is True
    assert pipeline._pipeline_batches[batch_id]['ok'] is False

    if when == 'running':
        assert signals == ['terminate' if action == 'reset' else 'killpg']
