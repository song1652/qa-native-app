"""Only bounded read-only preflight probes may repeat; no device access."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.fixture
def execute(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('execute_safe_retries', Path(__file__).parents[2] / 'scripts/05_execute.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, value in {'ROOT': tmp_path, 'STATE_DIR': tmp_path / 'state', 'STATE_FILE': tmp_path / 'state/pipeline.json',
        'TESTS_DIR': tmp_path / 'tests/generated', 'REPORTS_DIR': tmp_path / 'tests/reports',
        'JSON_REPORT': tmp_path / 'state/pytest_report.json', 'JUNIT_XML': tmp_path / 'state/pytest_report.xml'}.items():
        monkeypatch.setattr(module, name, value)
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)
    def forbidden(*args, **kwargs):
        pytest.fail('unmocked process')
    monkeypatch.setattr(module.subprocess, 'run', forbidden)
    return module


def test_pytest_replay_plugin_is_disabled_even_when_installed(execute, monkeypatch):
    monkeypatch.setattr(execute, '_has_rerun_plugin', lambda: True)
    for disabled in (True, False):
        assert execute._pytest_rerun_options(disabled) == ['-p', 'no:rerunfailures']


def test_android_preflight_never_substitutes_other_connected_device(execute, monkeypatch):
    calls = []
    def adb(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stdout='List of devices attached\nother-phone\tdevice\nchosen\tunauthorized\n')
    monkeypatch.setattr(execute.subprocess, 'run', adb)
    with pytest.raises(RuntimeError, match='device unavailable'):
        execute.resolve_selected_device('android', 'real_device', 'chosen')
    assert len(calls) == 1 and calls[0][1]['timeout'] > 0


def test_ios_preflight_requires_exact_selected_booted_simulator(execute, monkeypatch):
    def simctl(cmd, **kwargs):
        assert kwargs['timeout'] > 0
        return SimpleNamespace(returncode=0, stdout=json.dumps({'devices': {'ios': [
            {'udid': 'other', 'state': 'Booted', 'isAvailable': True},
            {'udid': 'chosen', 'state': 'Shutdown', 'isAvailable': True}]}}))
    monkeypatch.setattr(execute.subprocess, 'run', simctl)
    with pytest.raises(RuntimeError, match='device unavailable'):
        execute.resolve_selected_device('ios', 'simulator', 'chosen')


def test_preflight_retries_temporary_absence_before_any_actions(execute, monkeypatch):
    devices, appium = [], []
    def selected(*args):
        devices.append(args)
        if len(devices) < 3:
            raise RuntimeError('Selected Android device unavailable')
        return 'chosen'
    monkeypatch.setattr(execute, 'resolve_selected_device', selected, raising=False)
    monkeypatch.setattr(execute, 'check_appium_server', lambda: appium.append(True) or True)
    outcome = {'platform': 'android', 'device_mode': 'real_device', 'device_udid': 'chosen'}
    execute._preflight(outcome)
    assert len(devices) == 3 and len(appium) == 1
    assert outcome['device_udid'] == 'chosen'
    assert outcome['preflight'] == {'device_attempts': 3, 'appium_attempts': 1}


def test_preflight_configuration_error_does_not_retry(execute, monkeypatch):
    calls = []
    def selected(*args):
        calls.append(args)
        raise ValueError('Invalid configuration: no selected target')
    monkeypatch.setattr(execute, 'resolve_selected_device', selected, raising=False)
    with pytest.raises(ValueError):
        execute._preflight({'platform': 'ios', 'device_mode': 'simulator', 'device_udid': ''})
    assert len(calls) == 1


def test_json_failure_uses_failed_teardown_not_successful_call(execute, tmp_path):
    report = tmp_path / 'report.json'
    report.write_text(json.dumps({'tests': [{'nodeid': 'tc.py::test_one', 'outcome': 'error',
        'setup': {'outcome': 'passed'}, 'call': {'outcome': 'passed'},
        'teardown': {'outcome': 'failed', 'crash': {'message': 'InvalidSessionIdException: session deleted'}}}],
        'summary': {'total': 1, 'error': 1}}))
    error = execute.parse_json_report(report)['errors'][0]
    assert error['phase'] == 'teardown'
    assert error['error_type'] == 'InvalidSessionIdException'
    assert 'session deleted' in error['error']


def test_parser_retains_all_failed_phases_to_block_unsafe_healing(execute, tmp_path):
    report = tmp_path / 'report.json'
    report.write_text(json.dumps({'tests': [{'nodeid': 'tc.py::test_one', 'outcome': 'failed',
        'call': {'outcome': 'failed', 'crash': {'message': 'NoSuchElementException: missing'}},
        'teardown': {'outcome': 'failed', 'crash': {'message': 'InvalidSessionIdException: session deleted'}}}],
        'summary': {'total': 1, 'failed': 1}}))
    result = execute.parse_json_report(report)
    assert [error['phase'] for error in result['errors']] == ['call', 'teardown']
    assert not execute.recovery_for_result({'status': 'failed', 'execute_results': result})['can_heal']


def test_collection_failure_is_configuration_error(execute, tmp_path):
    report = tmp_path / 'report.json'
    report.write_text(json.dumps({'tests': [], 'collectors': [{'nodeid': 'tc_bad.py', 'outcome': 'failed',
        'longrepr': 'SyntaxError: invalid syntax'}], 'summary': {'total': 0}}))
    result = execute.parse_json_report(report)
    assert result['errors'][0]['phase'] == 'collection'
    assert execute.recovery_for_result({'status': 'failed', 'execute_results': result})['category'] == 'configuration'


def test_appium_unavailable_probe_stops_after_three_attempts(execute, monkeypatch):
    monkeypatch.setattr(execute, 'resolve_selected_device', lambda *args: 'chosen')
    calls = []
    monkeypatch.setattr(execute, 'check_appium_server', lambda: calls.append(1) or False)
    outcome = {'platform': 'ios', 'device_mode': 'simulator', 'device_udid': 'chosen'}
    with pytest.raises(RuntimeError, match='Appium server not running'):
        execute._preflight(outcome)
    assert len(calls) == 3
    assert outcome['preflight'] == {'device_attempts': 1, 'appium_attempts': 3}


def test_failed_teardown_is_retained_even_when_top_level_outcome_says_passed(execute, tmp_path):
    report = tmp_path / 'report.json'
    report.write_text(json.dumps({'tests': [{'nodeid': 'tc.py::test_one', 'outcome': 'passed',
        'call': {'outcome': 'passed'}, 'teardown': {'outcome': 'failed',
        'crash': {'message': 'InvalidSessionIdException: deleted'}}}], 'summary': {'total': 1, 'error': 1}}))
    result = execute.parse_json_report(report)
    assert result['passed'] == []
    assert result['errors'][0]['phase'] == 'teardown'


@pytest.mark.parametrize('ready,expected', [(True, True), (False, False), (None, False)])
def test_appium_probe_requires_ready_status(execute, monkeypatch, ready, expected):
    import urllib.request
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return json.dumps({'value': {'ready': ready}}).encode()
    def urlopen(url, timeout):
        assert url == 'http://localhost:4723/status' and 0 < timeout <= 3
        return Response()
    monkeypatch.setattr(urllib.request, 'urlopen', urlopen)
    assert execute.check_appium_server() is expected


def test_unauthorized_device_stops_preflight_without_retries(execute, monkeypatch):
    calls = []
    def device(*args):
        calls.append(args)
        raise RuntimeError('Selected Android device unavailable (unauthorized)')
    monkeypatch.setattr(execute, 'resolve_selected_device', device)
    with pytest.raises(RuntimeError):
        execute._preflight({'platform': 'android', 'device_mode': 'real_device', 'device_udid': 'chosen'})
    assert len(calls) == 1


def test_ios_physical_device_does_not_fallback(execute, monkeypatch):
    def probe(cmd, **kwargs):
        assert cmd == ['idevice_id', '-l'] and kwargs['timeout'] == 8
        return SimpleNamespace(returncode=0, stdout='other-device\n')
    monkeypatch.setattr(execute.subprocess, 'run', probe)
    with pytest.raises(RuntimeError, match='device unavailable'):
        execute.resolve_selected_device('ios', 'real_device', 'chosen')
