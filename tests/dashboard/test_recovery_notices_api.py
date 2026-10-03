"""Recovery notices use owned results and safe copy; never operate a device."""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.dashboard.routes import api
from scripts.run_results import write_execution_result


@pytest.fixture
def notice_client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(api, 'REPORTS_DIR', tmp_path / 'reports')
    monkeypatch.setattr(api, 'load_capture_session', lambda: {})
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as client:
        yield client, tmp_path


def result(root, status='failed', error='AssertionError: expected title', **extra):
    rid = 'run_ios_20261003_101000_001'
    write_execution_result(root, rid, {
        'platform': 'ios', 'status': status, 'error': error,
        'started_at': '2026-10-03T01:10:00+00:00',
        'execute_results': {'summary': {}, 'errors': []}, **extra,
    })
    return rid


@pytest.mark.parametrize('status,error,category', [
    ('failed', 'AssertionError: expected title', 'assertion'),
    ('failed', 'Appium server not running', 'appium_unavailable'),
    ('failed', 'InvalidSessionIdException', 'session_lost'),
    ('timed_out', 'stage took too long', 'timeout'),
    ('interrupted', 'server restarted', 'interrupted'),
])
def test_failed_run_has_stable_actionable_notice(notice_client, status, error, category):
    client, root = notice_client
    rid = result(root, status, error)
    response = client.get('/api/recovery-notices')
    assert response.status_code == 200
    notice = response.json()['notices'][0]
    assert notice['run_id'] == rid
    assert notice['category'] == category
    assert notice['title'] and notice['message'] and notice['action_label']
    assert notice['href'].startswith('/?view=')
    if category == 'session_lost':
        assert notice['href'] == '/?view=config'
    assert client.get('/api/recovery-notices').json()['notices'][0]['id'] == notice['id']


def test_passed_run_has_no_error_notice(notice_client):
    client, root = notice_client
    result(root, 'passed', '')
    assert client.get('/api/recovery-notices').json()['notices'] == []


def test_completed_folder_still_notifies_interrupted_workflow(notice_client):
    client, root = notice_client
    result(root, 'passed', '', workflow_status='interrupted', workflow_error='restart')
    notice = client.get('/api/recovery-notices').json()['notices'][0]
    assert notice['category'] == 'interrupted'
    assert notice['severity'] == 'warning'


def test_unknown_error_notice_does_not_leak_raw_secrets(notice_client):
    client, root = notice_client
    result(root, error='request https://user:secret-token@host/private failed')
    notice = client.get('/api/recovery-notices').json()['notices'][0]
    assert notice['category'] == 'unknown'
    assert 'secret-token' not in str(notice)
    assert 'https://' not in notice['message']


def test_disconnected_capture_notice_keeps_incident_identity(notice_client, monkeypatch):
    client, _ = notice_client
    session = {'active': True, 'session_id': 'draft', 'platform': 'ios',
               'udid': 'original', 'connection_issue_at': '2026-10-03T01:00:00',
               'last_activity_at': '2026-10-03T01:00:00'}
    monkeypatch.setattr(api, 'load_capture_session', lambda: session)
    with patch('shared.get_capture_driver', return_value=None):
        first = client.get('/api/recovery-notices').json()['notices'][0]
        session['last_activity_at'] = '2026-10-03T01:01:00'
        second = client.get('/api/recovery-notices').json()['notices'][0]
    assert first['id'] == second['id']
    assert first['href'] == '/?view=capture'
    assert first['category'] == 'session_lost'


def test_capture_launch_does_not_emit_disconnected_notice(notice_client, monkeypatch):
    client, _ = notice_client
    monkeypatch.setattr(api, 'load_capture_session', lambda: {'active': True, 'session_id': 'draft'})
    with patch('shared.get_capture_driver', return_value=None), patch('shared._capture_launch_active', True):
        assert client.get('/api/recovery-notices').json()['notices'] == []


def test_failure_still_being_repaired_does_not_emit_terminal_notice(notice_client):
    client, root = notice_client
    rid = result(root)
    with patch('shared._execution_reservation', {'run': {'run_id': rid}}):
        assert client.get('/api/recovery-notices').json()['notices'] == []


def test_new_server_restart_creates_new_capture_incident_after_reconnect(notice_client, monkeypatch):
    client, _ = notice_client
    monkeypatch.setattr(api, 'load_capture_session', lambda: {
        'active': True, 'session_id': 'same-draft', 'started_at': 'original-session-start',
    })
    with patch('shared.get_capture_driver', return_value=None):
        monkeypatch.setattr(api, '_RECOVERY_SERVER_STARTED_AT', 'restart-one', raising=False)
        first = client.get('/api/recovery-notices').json()['notices'][0]['id']
        monkeypatch.setattr(api, '_RECOVERY_SERVER_STARTED_AT', 'restart-two', raising=False)
        second = client.get('/api/recovery-notices').json()['notices'][0]['id']
    assert first != second


def test_preflight_failed_notice_preserves_selected_groups(notice_client):
    client, root = notice_client
    result(root, error='Selected ios device unavailable', groups=['settings', 'settings', None, ''])
    notice = client.get('/api/recovery-notices').json()['notices'][0]
    assert notice['groups'] == ['settings']
    assert notice['platform'] == 'ios'
