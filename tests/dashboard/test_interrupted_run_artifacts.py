"""Artifact views retain run outcomes even when capture never produced a manifest."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from agents.dashboard.routes import observability


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(observability, 'RUNS_DIR', tmp_path / 'state/runs')
    monkeypatch.setattr(observability, 'PROJECT_ROOT', tmp_path)
    app = FastAPI()
    app.include_router(observability.router)
    return TestClient(app)


def result(tmp_path, status='interrupted'):
    rid = 'run_android_20261002_120000_000'
    folder = tmp_path / 'state/runs' / rid
    folder.mkdir(parents=True)
    (folder / 'execution_result.json').write_text(json.dumps({
        'run_id': rid, 'platform': 'android', 'status': status,
        'device_mode': 'emulator', 'device_udid': 'emulator-5554',
        'error': 'worker interrupted', 'recovered_after_restart': True,
        'started_at': '2026-10-02T03:00:00+00:00', 'finished_at': '2026-10-02T03:00:09+00:00',
        'execute_results': {'summary': {'total': 0, 'passed': 0, 'failed': 0}},
    }))
    return rid, folder


def test_result_only_run_is_listed_and_details_explain_missing_artifacts(client, tmp_path):
    rid, _ = result(tmp_path)
    records = client.get('/api/runs').json()['runs']
    assert len(records) == 1
    assert records[0]['run_id'] == rid
    assert records[0]['status'] == 'interrupted'
    assert records[0]['counts']['total'] == 0
    data = client.get('/api/run_artifacts/' + rid).json()
    assert data['ok'] is True
    assert data['status'] == 'interrupted'
    assert data['error'] == 'worker interrupted'
    assert data['entries'] == []


def test_terminal_result_overrides_partial_manifest_counts(client, tmp_path):
    rid, folder = result(tmp_path, 'timed_out')
    artifacts = folder / 'artifacts'
    artifacts.mkdir()
    (artifacts / 'manifest.json').write_text(json.dumps({
        'run_id': rid, 'platform': 'android', 'started_at': '2026-10-02T03:00:00+00:00',
        'finished_at': None, 'entries': [{'nodeid': 'tc.py::test_ok', 'outcome': 'passed'}],
    }))
    record = client.get('/api/runs').json()['runs'][0]
    assert record['status'] == 'timed_out'
    assert record['counts']['total'] == 0
    assert record['counts_complete'] is False
    details = client.get('/api/run_artifacts/' + rid).json()
    assert details['status'] == 'timed_out'
    assert len(details['entries']) == 1


def test_result_only_running_run_cannot_be_deleted(client, tmp_path):
    rid, folder = result(tmp_path, 'running')
    assert client.delete('/api/run_artifacts/' + rid).status_code == 409
    assert folder.exists()


def test_unfinished_manifest_without_result_never_reports_success(client, tmp_path):
    rid = 'run_android_20261002_120000_000'
    folder = tmp_path / 'state/runs' / rid / 'artifacts'
    folder.mkdir(parents=True)
    (folder / 'manifest.json').write_text(json.dumps({
        'run_id': rid, 'platform': 'android', 'started_at': '2026-10-02T03:00:00+00:00',
        'finished_at': None, 'entries': [{'nodeid': 'tc.py::test_ok', 'outcome': 'passed'}],
    }))
    data = client.get('/api/run_artifacts/' + rid).json()
    assert data['status'] == 'incomplete'
    assert data['counts_complete'] is False
