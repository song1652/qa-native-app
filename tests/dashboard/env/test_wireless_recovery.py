"""Wireless recovery never changes the Capture target or trusts adb exit code alone."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.dashboard.env.test_env_endpoints import client, app, isolated_capture_state
from routes import env


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(env, 'is_pipeline_active', lambda: False)
    monkeypatch.setattr(env, '_get_wifi_serial', lambda: '10.0.0.2:5555')


@pytest.mark.parametrize('explicit', [True, False])
def test_same_wireless_capture_target_can_reconnect_without_losing_draft(client, monkeypatch, tmp_path, explicit):
    import utils.state as state
    session = {'active': True, 'session_id': 'draft', 'platform': 'android', 'target': 'device', 'udid': '10.0.0.2:5555', 'actions': [{'action': 'tap'}]}
    path = tmp_path / 'capture_session.json'
    path.write_text(json.dumps(session))
    monkeypatch.setattr(state, 'CAPTURE_SESSION_PATH', path)
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        assert kwargs['timeout'] == 10
        return SimpleNamespace(returncode=0, stdout='device\n' if cmd[-1] == 'get-state' else 'connected', stderr='')
    monkeypatch.setattr(env.subprocess, 'run', run)
    monkeypatch.setattr(env, '_get_wifi_serial', lambda: '10.0.0.99:5555')
    response = client.post('/api/env/android/real/connect', json={'serial': session['udid']} if explicit else {})
    assert response.json()['ok'] is True
    assert calls[-1][-3:] == ['-s', session['udid'], 'get-state']
    assert json.loads(path.read_text()) == session


def test_active_capture_cannot_reconnect_a_different_target(client, monkeypatch, tmp_path):
    import utils.state as state
    path = tmp_path / 'capture_session.json'
    path.write_text(json.dumps({'active': True, 'platform': 'android', 'target': 'device', 'udid': '10.0.0.2:5555'}))
    monkeypatch.setattr(state, 'CAPTURE_SESSION_PATH', path)
    runner = Mock();monkeypatch.setattr(env.subprocess, 'run', runner)
    response = client.post('/api/env/android/real/connect', json={'serial': '10.0.0.3:5555'})
    assert response.status_code == 403
    runner.assert_not_called()


@pytest.mark.parametrize('connected', ['offline', 'unauthorized', ''])
def test_adb_zero_exit_is_not_success_without_ready_selected_device(client, monkeypatch, connected):
    monkeypatch.setattr(env, 'is_capture_active', lambda platform: False)
    monkeypatch.setattr(env.subprocess, 'run', lambda cmd, **kwargs: SimpleNamespace(returncode=0, stdout=connected if cmd[-1] == 'get-state' else 'unable to connect', stderr=''))
    response = client.post('/api/env/android/real/connect', json={})
    assert response.json()['ok'] is False


@pytest.mark.parametrize('action', ['connect', 'disconnect'])
def test_wireless_changes_are_blocked_during_execution(client, monkeypatch, action):
    monkeypatch.setattr(env, 'is_pipeline_active', lambda: True)
    runner = Mock();monkeypatch.setattr(env.subprocess, 'run', runner)
    response = client.post('/api/env/android/real/' + action, json={'serial': '10.0.0.2:5555'})
    assert response.status_code == 403
    assert response.json()['error'] == 'pipeline_running'
    runner.assert_not_called()
