"""Bounded Capture read retries. No device, server, or production state I/O."""
import asyncio
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'agents/dashboard'))
from routes import capture
from utils import capture_driver


def run(coroutine):
    result = {}
    def worker():
        try:
            result['value'] = asyncio.run(coroutine)
        except BaseException as exc:
            result['error'] = exc
    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(5)
    assert not thread.is_alive()
    if 'error' in result:
        raise result['error']
    return result['value']


@pytest.fixture
def target(monkeypatch, tmp_path):
    session = {'session_id': 'draft', 'platform': 'android', 'target': 'emulator',
               'udid': 'emulator-1', 'active': True, 'actions': [{'action': 'tap'}]}
    driver = SimpleNamespace(get_window_size=Mock(return_value={'width': 100}),
                             get_screenshot_as_base64=Mock(return_value='image'))
    monkeypatch.setattr(capture, 'load_capture_session', lambda: dict(session))
    monkeypatch.setattr(capture, 'get_capture_driver', lambda: driver)
    monkeypatch.setattr(capture.shared, 'get_capture_driver', lambda: driver)
    monkeypatch.setattr(capture, 'is_capture_active', lambda: session['active'])
    monkeypatch.setattr(capture, 'save_capture_session', Mock())
    monkeypatch.setattr(capture_driver, 'CAPTURES_DIR', tmp_path)
    monkeypatch.setattr(capture, 'CAPTURE_READ_RETRY_DELAY', .001, raising=False)
    return session, driver


def test_transient_read_timeout_retries_same_driver_once(target):
    _, driver = target
    driver.get_screenshot_as_base64.side_effect = [TimeoutError('read timed out'), 'image']
    data = json.loads(run(capture.capture_screenshot()).body)
    assert data['ok'] and data['data'] == 'image'
    assert data['attempts'] == 2
    assert driver.get_screenshot_as_base64.call_count == 2
    assert not getattr(driver, '_capture_disconnected', False)


@pytest.mark.parametrize('message', ['invalid session id', 'ECONNREFUSED', 'device offline', 'unknown failure'])
def test_permanent_or_unknown_failure_never_retries(target, message):
    _, driver = target
    driver.get_screenshot_as_base64.side_effect = RuntimeError(message)
    data = json.loads(run(capture.capture_screenshot()).body)
    assert not data['ok']
    assert data['recovery']['attempts'] == 1
    assert driver.get_screenshot_as_base64.call_count == 1


def test_session_change_between_attempts_stops_retry(target):
    session, driver = target
    def fail():
        session['session_id'] = 'new-draft'
        raise TimeoutError('read timed out')
    driver.get_screenshot_as_base64.side_effect = fail
    data = json.loads(run(capture.capture_screenshot()).body)
    assert not data['ok'] and data['code'] == 'capture_session_changed'
    assert driver.get_screenshot_as_base64.call_count == 1


def test_late_success_from_old_session_is_rejected(target):
    session, driver = target
    def changed():
        session['udid'] = 'emulator-2'
        return 'old screen'
    driver.get_screenshot_as_base64.side_effect = changed
    data = json.loads(run(capture.capture_screenshot()).body)
    assert not data['ok'] and 'data' not in data
    assert data['code'] == 'capture_session_changed'


def test_outer_deadline_never_retries_still_running_read(target, monkeypatch):
    _, driver = target
    release = threading.Event()
    driver.get_screenshot_as_base64.side_effect = lambda: release.wait(1)
    monkeypatch.setattr(capture, 'CAPTURE_READ_TIMEOUT', .01, raising=False)
    async def scenario():
        try:
            result = await capture.capture_screenshot()
            assert json.loads(result.body)['recovery']['attempts'] == 1
            assert not json.loads(result.body)['recovery']['retryable']
            assert driver.get_screenshot_as_base64.call_count == 1
            return result
        finally:
            release.set()
    assert not json.loads(run(scenario()).body)['ok']


def test_snapshot_disk_failure_is_not_retried_or_disconnected(target, monkeypatch):
    _, driver = target
    driver.page_source = '<hierarchy/>'
    save = Mock(side_effect=OSError('disk full'))
    monkeypatch.setattr(capture, '_save_hierarchy_snapshot', save, raising=False)
    class Request:
        async def json(self):
            return {'session_id': 'draft'}
    data = json.loads(run(capture.capture_snapshot(Request())).body)
    assert not data['ok'] and data['recovery']['category'] == 'configuration'
    assert data['recovery']['retryable'] is False
    assert not data['reconnect_required']
    assert save.call_count == 1
    assert not getattr(driver, '_capture_disconnected', False)


def test_confirmed_disconnect_preserves_latest_actions_and_stable_incident(target, monkeypatch):
    session, driver = target
    saved = []
    def save(data):
        saved.append(data)
        session.update(data)
    monkeypatch.setattr(capture, 'save_capture_session', save)
    def failed_read():
        session['actions'] = [{'action': 'input', 'value': 'latest draft'}]
        raise RuntimeError('invalid session id')
    driver.get_window_size.side_effect = failed_read
    data = json.loads(run(capture.capture_driver_alive()).body)
    assert data['recovery']['category'] == 'session_lost'
    assert saved[0]['actions'] == [{'action': 'input', 'value': 'latest draft'}]
    incident = session['connection_issue_at']
    run(capture.capture_driver_alive())
    assert session['connection_issue_at'] == incident
    assert len(saved) == 1


def test_successful_launch_clears_previous_connection_incident(target, monkeypatch):
    session, driver = target
    session.update(connection_issue_at='old', connection_recovery={'category': 'session_lost'})
    saved = Mock()
    monkeypatch.setattr(capture, 'save_capture_session', saved)
    monkeypatch.setattr(capture, 'set_capture_driver', Mock())
    monkeypatch.setattr(capture, '_do_start_appium_session', lambda _: {
        'ok': True, '_driver': driver, 'udid': session['udid'], 'device_name': 'Original'})
    class Request:
        async def json(self):
            return {'session_id': 'draft'}
    assert json.loads(run(capture.capture_launch(Request())).body)['ok']
    assert 'connection_issue_at' not in saved.call_args.args[0]
    assert 'connection_recovery' not in saved.call_args.args[0]


def test_transient_read_failure_exhausts_two_attempts(target):
    _, driver = target
    driver.get_screenshot_as_base64.side_effect = ConnectionResetError('connection reset')
    data = json.loads(run(capture.capture_screenshot()).body)
    assert not data['ok'] and data['reconnect_required']
    assert data['recovery']['attempts'] == 2
    assert data['recovery']['max_attempts'] == 2
    assert data['recovery']['action'] == 'reconnect_capture'
    assert driver.get_screenshot_as_base64.call_count == 2


def test_replaced_driver_during_backoff_is_not_called(target, monkeypatch):
    _, old = target
    replacement = SimpleNamespace(get_screenshot_as_base64=Mock())
    current = [old]
    monkeypatch.setattr(capture, 'get_capture_driver', lambda: current[0])
    def fail():
        current[0] = replacement
        raise ConnectionResetError('connection reset')
    old.get_screenshot_as_base64.side_effect = fail
    data = json.loads(run(capture.capture_screenshot()).body)
    assert data['code'] == 'capture_session_changed'
    old.get_screenshot_as_base64.assert_called_once()
    replacement.get_screenshot_as_base64.assert_not_called()
    assert not hasattr(replacement, '_capture_disconnected')


def test_launch_failure_adds_actionable_metadata_without_replaying_creation(target, monkeypatch):
    session, _ = target
    launch = Mock(return_value={'ok': False, 'error': 'ECONNREFUSED'})
    monkeypatch.setattr(capture, '_do_start_appium_session', launch)
    class Request:
        async def json(self):
            return {'session_id': session['session_id']}
    data = json.loads(run(capture.capture_launch(Request())).body)
    launch.assert_called_once()
    assert not data['ok']
    assert data['recovery']['category'] == 'appium_unavailable'
    assert data['recovery']['action'] == 'check_environment'
    assert not data['recovery']['retryable']


def test_snapshot_activity_update_preserves_newer_draft_and_incident(target, monkeypatch):
    session, driver = target
    driver.page_source = '<hierarchy/>'
    original = dict(session)
    current = {**session, 'actions': [{'action': 'input', 'value': 'new'}],
               'connection_issue_at': 'same-incident', 'connection_recovery': {'category': 'transport'}}
    reads = [0]
    def load():
        reads[0] += 1
        return dict(original if reads[0] == 1 else current)
    monkeypatch.setattr(capture, 'load_capture_session', load)
    save = Mock()
    monkeypatch.setattr(capture, 'save_capture_session', save)
    class Request:
        async def json(self):
            return {'session_id': 'draft'}
    assert json.loads(run(capture.capture_snapshot(Request())).body)['ok']
    assert save.call_args.args[0]['actions'] == current['actions']
    assert save.call_args.args[0]['connection_issue_at'] == 'same-incident'
