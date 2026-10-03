"""Execution outcomes belong to a run even when pytest never starts."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def execute(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('execute_isolation', Path(__file__).parents[2] / 'scripts/05_execute.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, value in {'ROOT': tmp_path, 'STATE_DIR': tmp_path / 'state', 'STATE_FILE': tmp_path / 'state/pipeline.json', 'TESTS_DIR': tmp_path / 'tests/generated', 'REPORTS_DIR': tmp_path / 'tests/reports', 'JSON_REPORT': tmp_path / 'state/pytest_report.json', 'JUNIT_XML': tmp_path / 'state/pytest_report.xml'}.items():
        monkeypatch.setattr(module, name, value)
    module.STATE_DIR.mkdir()
    module.STATE_FILE.write_text(json.dumps({'execute_results': {'passed': ['OLD'], 'summary': {'passed': 1}}, 'report_path': 'old.html'}))
    (module.TESTS_DIR / 'android').mkdir(parents=True)
    monkeypatch.setattr(module, 'check_android_device', lambda: True)
    monkeypatch.setattr(module, 'check_appium_server', lambda: True)
    monkeypatch.setattr(module, '_has_json_report_plugin', lambda: True)
    monkeypatch.setattr(module, '_has_rerun_plugin', lambda: False)
    monkeypatch.setattr(sys, 'argv', ['05_execute.py', '--no-report'])
    monkeypatch.setenv('QA_RUN_ID', 'run_one')
    return module


def outcome(module, run='run_one'):
    path = module.ROOT / 'state/runs' / run / 'execution_result.json'
    assert path.exists(), 'every execution must publish its own result'
    return json.loads(path.read_text())


@pytest.mark.parametrize('failure', ['device', 'appium', 'no_tests', 'spawn'])
def test_early_failure_never_reuses_previous_passes(execute, monkeypatch, failure):
    if failure == 'device':
        monkeypatch.setattr(execute, 'check_android_device', lambda: False)
    elif failure == 'appium':
        monkeypatch.setattr(execute, 'check_appium_server', lambda: False)
    elif failure == 'no_tests':
        (execute.TESTS_DIR / 'android').rmdir()
    def fail_spawn(*args, **kwargs):
        raise OSError('cannot spawn')
    monkeypatch.setattr(execute.subprocess, 'run', fail_spawn)
    with pytest.raises(SystemExit) as error:
        execute.main()
    assert error.value.code != 0
    saved = outcome(execute)
    assert saved['status'] == 'failed'
    assert saved['execute_results']['passed'] == []
    assert saved['execute_results']['summary']['passed'] == 0
    assert 'report_path' not in saved
    assert saved['error']


def test_runs_and_healing_invocations_use_fresh_reports(execute, monkeypatch):
    paths = []
    def pytest_process(cmd, **kwargs):
        report = Path(next(arg.split('=', 1)[1] for arg in cmd if arg.startswith('--json-report-file=')))
        paths.append(report)
        if len(paths) == 1:
            report.write_text(json.dumps({'tests': [{'nodeid': 'tc_first.py::test_ok', 'outcome': 'passed'}], 'summary': {'total': 1, 'passed': 1}}))
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=2)
    monkeypatch.setattr(execute.subprocess, 'run', pytest_process)
    with pytest.raises(SystemExit):
        execute.main()
    first = outcome(execute)
    monkeypatch.setenv('QA_RUN_ID', 'run_two')
    for _ in range(2):
        with pytest.raises(SystemExit):
            execute.main()
        assert outcome(execute, 'run_two')['execute_results']['passed'] == []
    assert outcome(execute) == first
    assert len(set(paths)) == 3
    assert all(path.is_relative_to(execute.ROOT / 'state/runs') for path in paths)


def test_summary_rejects_other_run_and_failed_write_preserves_previous(tmp_path, monkeypatch):
    from scripts.run_results import read_execution_result, write_execution_result
    write_execution_result(tmp_path, 'run_one', {'status': 'passed'})
    with pytest.raises(ValueError):
        write_execution_result(tmp_path, '../outside', {})
    with pytest.raises(ValueError):
        write_execution_result(tmp_path, 'run_one', {'run_id': 'run_two'})
    original_replace = Path.replace
    def fail_replace(path, target):
        raise OSError('disk unavailable')
    monkeypatch.setattr(Path, 'replace', fail_replace)
    with pytest.raises(OSError):
        write_execution_result(tmp_path, 'run_one', {'status': 'failed'})
    assert read_execution_result(tmp_path, 'run_one')['status'] == 'passed'
    monkeypatch.setattr(Path, 'replace', original_replace)
    path = tmp_path / 'state/runs/run_one/execution_result.json'
    path.write_text(json.dumps({'run_id': 'run_two', 'status': 'passed'}))
    assert read_execution_result(tmp_path, 'run_one') is None
    assert read_execution_result(tmp_path, '../outside') is None


@pytest.mark.parametrize('cli_args,environment,expected', [
    (['--mode', 'real_device', '--udid', 'PHONE'], {'DEVICE_MODE': 'emulator', 'DEVICE_UDID': 'emulator-5554'}, ('real_device', 'PHONE')),
    ([], {'DEVICE_MODE': 'real_device', 'DEVICE_UDID': 'WIFI-PHONE'}, ('real_device', 'WIFI-PHONE')),
    ([], {}, ('emulator', '')),
])
def test_execution_result_preserves_target_context_on_preflight_failure(execute, monkeypatch, cli_args, environment, expected):
    monkeypatch.setattr(sys, 'argv', ['05_execute.py', '--no-report', *cli_args])
    for key in ('DEVICE_MODE', 'DEVICE_UDID'):
        monkeypatch.delenv(key, raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(execute, 'check_android_device', lambda: False)
    with pytest.raises(SystemExit):
        execute.main()
    saved = outcome(execute)
    assert saved['platform'] == 'android'
    assert (saved['device_mode'], saved['device_udid']) == expected


def test_execution_records_start_and_finish_timestamps(execute, monkeypatch):
    from datetime import datetime
    monkeypatch.setattr(execute, 'check_android_device', lambda: False)
    with pytest.raises(SystemExit):
        execute.main()
    result = outcome(execute)
    assert datetime.fromisoformat(result['started_at']) <= datetime.fromisoformat(result['finished_at'])
    assert datetime.fromisoformat(result['started_at']).tzinfo is not None


def test_repeated_attempt_keeps_logical_run_start(execute, monkeypatch):
    monkeypatch.setattr(execute, 'check_android_device', lambda: False)
    with pytest.raises(SystemExit):
        execute.main()
    started = outcome(execute)['started_at']
    with pytest.raises(SystemExit):
        execute.main()
    assert outcome(execute)['started_at'] == started
