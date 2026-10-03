"""Logical execution ownership using only fake subprocesses and temporary files."""
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from agents.dashboard.routes import pipeline

@pytest.fixture
def harness(monkeypatch, tmp_path):
    jobs, commands = [], []
    class Thread:
        def __init__(self, target, args=(), **kwargs): jobs.append(lambda: target(*args))
        def start(self): pass
    class Process:
        pid = 123456
        returncode = None
        def __init__(self, command, **kwargs):
            commands.append((command, kwargs.get('env')))
        def poll(self): return self.returncode
        def wait(self, timeout=None):
            self.returncode = 0
            return 0
        def terminate(self): self.returncode = -15
    monkeypatch.setattr(pipeline, '_running', {})
    monkeypatch.setattr(pipeline, '_test_runs', {})
    monkeypatch.setattr(pipeline, '_pipeline_batches', {})
    if hasattr(pipeline, '_execution_reservation'):
        pipeline._execution_reservation.clear()
    monkeypatch.setattr(pipeline, 'threading', SimpleNamespace(Thread=Thread))
    monkeypatch.setattr(pipeline.subprocess, 'Popen', Process)
    monkeypatch.setattr(pipeline, 'PROJECT_ROOT', tmp_path)
    (tmp_path / 'scripts').mkdir()
    for name in ('01_analyze.py', '02_generate.py', '03_lint.py', '05_execute.py', '06_heal.py', 'jira_reporter.py'):
        (tmp_path / 'scripts' / name).touch()
    monkeypatch.setattr(pipeline, 'LOGS_DIR', tmp_path)
    monkeypatch.setattr(pipeline, 'GENERATED_DIR', tmp_path)
    (tmp_path / 'android' / 'one').mkdir(parents=True)
    (tmp_path / 'android' / 'two').mkdir()
    monkeypatch.setattr(pipeline, 'list_tc_folders', lambda _: ['one', 'two'])
    monkeypatch.setattr(pipeline, 'is_capture_active', lambda _: False)
    monkeypatch.setattr(pipeline, 'read_state', lambda: {})
    for name in ('save_state', 'broadcast_timeline_sync'):
        monkeypatch.setattr(pipeline, name, lambda *_: None)
    for name in ('save_running_pids', '_purge_old_runs', '_broadcast_run_summary'):
        monkeypatch.setattr(pipeline, name, lambda *_: None)
    monkeypatch.setattr(pipeline, '_SERIAL_FOLDER_GAP_SECONDS', 0)
    app = FastAPI(); app.include_router(pipeline.router)
    yield TestClient(app), jobs, commands
    if hasattr(pipeline, '_execution_reservation'):
        pipeline._execution_reservation.clear()


def test_pending_full_run_reserves_execution(harness):
    client, jobs, commands = harness
    body = {'platform': 'android', 'tc_folders': ['one'], 'from_tc_studio': True}
    assert client.post('/api/run_all', json=body).status_code == 200
    assert client.post('/api/run_all', json=body).status_code == 409
    assert client.post('/api/run_test', json={'test_folder': 'two'}).status_code == 409
    assert commands == []


def test_quick_run_blocks_capture(harness, monkeypatch):
    client, _, commands = harness
    monkeypatch.setattr(pipeline, 'is_capture_active', lambda _: True)
    assert client.post('/api/run_test', json={'test_folder': 'one'}).status_code == 409
    assert commands == []


def test_cancel_queued_quick_run_never_spawns(harness):
    client, jobs, commands = harness
    assert client.post('/api/run_test', json={'test_folder': 'one'}).status_code == 200
    assert client.post('/api/cancel', json={'step': 'folder:android:one'}).status_code == 200
    jobs[0]()
    assert commands == []

@pytest.mark.parametrize('failures,expected_heals', [(1, 1), (4, 3)])
def test_full_run_heals_failed_execute_with_same_environment(harness, monkeypatch, failures, expected_heals):
    client, jobs, commands = harness
    attempts = []
    base = pipeline.subprocess.Popen
    class Process(base):
        def __init__(self, command, **kwargs):
            super().__init__(command, **kwargs)
            self.command = command
        def wait(self, timeout=None):
            if '05_execute.py' in self.command[2]:
                attempts.append(True)
                self.returncode = 1 if len(attempts) <= failures else 0
            else:
                self.returncode = 0
            return self.returncode
    monkeypatch.setattr(pipeline.subprocess, 'Popen', Process)
    monkeypatch.setattr(pipeline, 'read_execution_result', lambda *_: {'status': 'failed', 'execute_results': {'errors': [{'error': 'NoSuchElementException'}]}})
    # Exhausted retries must not actually publish a Jira issue.
    monkeypatch.setattr(pipeline.subprocess, 'run', lambda *_a, **_k: SimpleNamespace(stdout='', stderr=''))
    response = client.post('/api/run_all', json={'tc_folders': ['one'], 'from_tc_studio': True})
    jobs[0]()
    executions = [env for command, env in commands if '05_execute.py' in command[2]]
    heals = [env for command, env in commands if '06_heal.py' in command[2]]
    assert len(heals) == expected_heals
    assert len(executions) == expected_heals + 1
    assert all(env == executions[0] for env in heals)
    status = client.get('/api/run_all/status/' + response.json()['batch_id']).json()
    assert status['done'] and status['ok'] is (failures == 1)


def test_cancel_running_quick_run_never_heals(harness, monkeypatch):
    client, jobs, commands = harness
    base = pipeline.subprocess.Popen
    class Process(base):
        def wait(self, timeout=None):
            assert client.post('/api/cancel', json={'step': 'folder:android:one'}).status_code == 200
            self.returncode = -15
            return -15
    monkeypatch.setattr(pipeline.subprocess, 'Popen', Process)
    monkeypatch.setattr(pipeline, '_terminate_group', lambda proc: setattr(proc, 'returncode', -15))
    client.post('/api/run_test', json={'test_folder': 'one', 'heal': True})
    jobs[0]()
    assert len(commands) == 1
    assert not pipeline._execution_reservation


def test_termination_failure_keeps_admission_closed(harness, monkeypatch):
    client, jobs, commands = harness
    client.post('/api/run_test', json={'test_folder': 'one'})
    proc = pipeline.subprocess.Popen(['fake'])
    pipeline._running['folder:android:one'] = proc
    def fail(_proc): raise RuntimeError('still alive')
    monkeypatch.setattr(pipeline, '_terminate_group', fail)
    assert client.post('/api/cancel', json={'step': 'folder:android:one'}).status_code == 409
    jobs[0]()
    assert client.post('/api/run_test', json={'test_folder': 'two'}).status_code == 409
    assert pipeline._running['folder:android:one'] is proc


def test_group_termination_escalates_even_after_parent_exits(monkeypatch):
    import time
    signals = []
    clock = iter([0, 1, 4, 5, 6])
    monkeypatch.setattr(time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(time, 'sleep', lambda _: None)
    def killpg(pid, signal):
        signals.append(signal)
        if signal == 0 and 9 in signals:
            raise ProcessLookupError
    monkeypatch.setattr(pipeline.os, 'killpg', killpg)
    pipeline._terminate_group(SimpleNamespace(pid=123456, poll=lambda: 0))
    assert signals == [15, 0, 9, 0]


def test_rejected_single_step_does_not_overwrite_active_state(harness, monkeypatch):
    client, _, _ = harness
    writes = []
    monkeypatch.setattr(pipeline, 'save_state', writes.append)
    client.post('/api/run_test', json={'test_folder': 'one'})
    assert client.post('/api/run', json={'step': 'execute', 'platform': 'ios'}).status_code == 409
    assert writes == []


def test_failed_worker_start_releases_admission(harness, monkeypatch):
    client, _, _ = harness
    class Thread:
        def __init__(self, **kwargs): pass
        def start(self): raise RuntimeError('no threads')
    monkeypatch.setattr(pipeline, 'threading', SimpleNamespace(Thread=Thread))
    with pytest.raises(RuntimeError, match='no threads'):
        client.post('/api/run_test', json={'test_folder': 'one'})
    assert not pipeline._execution_reservation


def test_log_result_uses_its_run_not_latest_global_state(harness, monkeypatch, tmp_path):
    from scripts.run_results import write_execution_result
    client, _, _ = harness
    monkeypatch.setattr(pipeline, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(pipeline, 'read_state', lambda: {'execute_results': {'summary': {'passed': 99}}})
    pipeline._test_runs['old.txt'] = {'key': 'old', 'run_id': 'run_android_old', 'done': True, 'returncode': 0}
    own = {'passed': ['one'], 'errors': [], 'summary': {'passed': 1, 'failed': 0, 'total': 1}}
    write_execution_result(tmp_path, 'run_android_old', {'execute_results': own, 'status': 'passed', 'exit_code': 0})
    result = client.post('/api/run_log', json={'log': 'old.txt'}).json()['result']
    assert all(result[key] == value for key, value in own.items())
    pipeline._test_runs['missing.txt'] = {'key': 'new', 'run_id': 'run_android_new', 'done': True, 'returncode': 1}
    assert client.post('/api/run_log', json={'log': 'missing.txt'}).json()['result']['summary'] == {}

@pytest.mark.parametrize('quick', [False, True])
@pytest.mark.parametrize('heal_code,executions', [(0, 2), (1, 1), (-15, 1), (143, 1)])
def test_only_successful_heal_is_reexecuted(harness, monkeypatch, quick, heal_code, executions):
    client, jobs, commands = harness
    base = pipeline.subprocess.Popen
    attempts = []
    class Process(base):
        def __init__(self, command, **kwargs):
            super().__init__(command, **kwargs); self.command = command
        def wait(self, timeout=None):
            self.returncode = 0
            if '05_execute.py' in self.command[2]:
                attempts.append(True)
                self.returncode = 1 if len(attempts) == 1 else 0
            elif '06_heal.py' in self.command[2]:
                self.returncode = heal_code
            return self.returncode
    monkeypatch.setattr(pipeline.subprocess, 'Popen', Process)
    monkeypatch.setattr(pipeline, 'read_execution_result', lambda *_: {'status': 'failed', 'execute_results': {'errors': [{'error': 'NoSuchElementException'}]}})
    if quick:
        client.post('/api/run_test', json={'test_folder': 'one'})
    else:
        client.post('/api/run_all', json={'tc_folders': ['one'], 'from_tc_studio': True})
    jobs[0]()
    assert len(attempts) == executions


def test_next_folder_preflight_log_never_inherits_previous_result(harness, monkeypatch):
    client, jobs, commands = harness
    base = pipeline.subprocess.Popen
    class Process(base):
        def __init__(self, command, **kwargs):
            super().__init__(command, **kwargs); self.command = command
        def wait(self, timeout=None):
            self.returncode = int('02_generate.py' in self.command[2] and 'android/two' in self.command)
            return self.returncode
    monkeypatch.setattr(pipeline.subprocess, 'Popen', Process)
    client.post('/api/run_all', json={'tc_folders': ['one', 'two'], 'from_tc_studio': True})
    jobs[0]()
    current_id = pipeline._test_runs['run_generate.txt']['run_id']
    assert current_id
    assert current_id != pipeline._test_runs['run_execute.txt']['run_id']
    assert client.post('/api/run_log', json={'log': 'run_generate.txt'}).json()['result']['summary'] == {}


def test_cancel_finalizes_run_owned_result_and_keeps_measurements(harness, monkeypatch, tmp_path):
    from scripts.run_results import read_execution_result, write_execution_result
    client, jobs, _ = harness
    client.post('/api/run_test', json={'test_folder': 'one'})
    run_id = pipeline._test_runs['run_test_android_one.txt']['run_id']
    measured = {'passed': ['measured'], 'errors': [], 'summary': {'total': 1, 'passed': 1, 'failed': 0}}
    write_execution_result(tmp_path, run_id, {'status': 'running', 'execute_results': measured})
    assert client.post('/api/cancel', json={'step': 'folder:android:one'}).status_code == 200
    jobs[0]()
    result = read_execution_result(tmp_path, run_id)
    assert result['status'] == 'cancelled' and result['exit_code'] == -15
    assert result['execute_results'] == {**measured, 'exit_code': -15}
    response = client.post('/api/run_log', json={'log': 'run_test_android_one.txt'}).json()
    assert response['result']['status'] == 'cancelled'


def test_spawn_exception_finalizes_failed_result_with_reason(harness, monkeypatch, tmp_path):
    from scripts.run_results import read_execution_result
    client, jobs, _ = harness
    def fail(*args, **kwargs): raise OSError('spawn unavailable')
    monkeypatch.setattr(pipeline.subprocess, 'Popen', fail)
    response = client.post('/api/run_test', json={'test_folder': 'one'})
    jobs[0]()
    meta = pipeline._test_runs[response.json()['log']]
    result = read_execution_result(tmp_path, meta['run_id'])
    assert result['status'] == 'failed' and result['exit_code'] == -1
    assert result['error'] == 'spawn unavailable'
    polled = client.post('/api/run_log', json={'log': response.json()['log']}).json()
    assert polled['result']['error'] == 'spawn unavailable'
    assert polled['result']['summary'] == {}


def test_analyze_spawn_exception_records_failed_stage_without_test_counts(harness, monkeypatch, tmp_path):
    client, _, _ = harness
    def fail(*args, **kwargs): raise OSError('spawn unavailable')
    monkeypatch.setattr(pipeline.subprocess, 'Popen', fail)
    with pytest.raises(OSError):
        client.post('/api/run', json={'step': 'analyze'})
    import json
    records = list((tmp_path / 'state' / 'runs').glob('*/execution_result.json'))
    assert len(records) == 1
    result = json.loads(records[0].read_text())
    assert result['status'] == 'failed'
    assert result['error'] == 'spawn unavailable'
    assert result['execute_results']['summary'] == {}


def test_standalone_heal_reuses_owned_run_and_target(harness, monkeypatch, tmp_path):
    from scripts.run_results import write_execution_result
    client, jobs, commands = harness
    run_id = 'run_android_previous'
    write_execution_result(tmp_path, run_id, {'status': 'failed', 'platform': 'android', 'device_mode': 'real_device', 'device_udid': 'phone-1'})
    monkeypatch.setattr(pipeline, 'read_state', lambda: {'last_run_id': run_id})
    response = client.post('/api/run', json={'step': 'heal', 'platform': 'android'})
    assert response.status_code == 200
    env = commands[0][1]
    assert env['QA_RUN_ID'] == run_id
    assert env['DEVICE_MODE'] == 'real_device'
    assert env['DEVICE_UDID'] == 'phone-1'
    jobs[0]()


@pytest.mark.parametrize('change', ['missing', 'platform', 'mode', 'device', 'unknown_device'])
def test_standalone_heal_rejects_missing_or_different_execution(harness, monkeypatch, tmp_path, change):
    from scripts.run_results import write_execution_result
    client, jobs, commands = harness
    run_id = 'run_android_previous'
    if change != 'missing':
        write_execution_result(tmp_path, run_id, {'status': 'failed', 'platform': 'android', 'device_mode': 'real_device', 'device_udid': '' if change == 'unknown_device' else 'phone-1'})
    monkeypatch.setattr(pipeline, 'read_state', lambda: {'last_run_id': run_id})
    body = {'step': 'heal', 'platform': 'android'}
    if change == 'platform': body['platform'] = 'ios'
    if change == 'mode': body['mode'] = 'emulator'
    if change == 'device': body['device_udid'] = 'other-phone'
    assert client.post('/api/run', json=body).status_code == 409
    assert commands == []
    assert not pipeline._execution_reservation


def test_failed_generation_is_recorded_before_next_folder_without_leaking_error(harness, monkeypatch, tmp_path):
    from scripts.run_results import write_execution_result, read_execution_result
    client, jobs, commands = harness
    ids = {}
    base = pipeline.subprocess.Popen
    class Process(base):
        def __init__(self, command, **kwargs):
            super().__init__(command, **kwargs)
            self.command, self.env = command, kwargs['env']
        def wait(self, timeout=None):
            rid = self.env['QA_RUN_ID']
            if '02_generate.py' in self.command[2]:
                folder = self.command[self.command.index('--tc-dir') + 1]
                ids[folder] = rid
                if folder == 'android/two':
                    assert read_execution_result(tmp_path, ids['android/one'])['status'] == 'failed'
                self.returncode = 1 if folder == 'android/one' else 0
            else:
                self.returncode = 0
                if '05_execute.py' in self.command[2]:
                    write_execution_result(tmp_path, rid, {'status': 'passed', 'exit_code': 0,
                        'execute_results': {'summary': {'passed': 1, 'failed': 0}}})
            return self.returncode
    monkeypatch.setattr(pipeline.subprocess, 'Popen', Process)
    response = client.post('/api/run_all', json={'tc_folders': ['one', 'two'], 'from_tc_studio': True})
    jobs[0]()
    failed = read_execution_result(tmp_path, ids['android/one'])
    passed = read_execution_result(tmp_path, ids['android/two'])
    assert ids['android/one'] != ids['android/two']
    assert failed['status'] == 'failed' and failed['execute_results']['summary'] == {}
    assert passed['status'] == 'passed' and not passed.get('error')
    assert pipeline._test_runs['run_generate.txt']['run_id'] == ids['android/two']
    assert pipeline._pipeline_batches[response.json()['batch_id']]['ok'] is False


def test_postspawn_persistence_failure_terminates_child_and_releases_slot(harness, monkeypatch):
    client, jobs, commands = harness
    saves = [0]
    stopped = []
    def save():
        saves[0] += 1
        if saves[0] > 1:
            raise OSError('disk full')
    def stop(proc):
        stopped.append(proc)
        proc.returncode = -15
    monkeypatch.setattr(pipeline, 'save_running_pids', save)
    monkeypatch.setattr(pipeline, '_terminate_group', stop)
    with pytest.raises(OSError, match='disk full'):
        client.post('/api/run', json={'step': 'generate'})
    assert len(stopped) == 1
    assert pipeline._running == {}
    assert not pipeline._execution_reservation
    assert jobs == []


def test_single_preflight_nonzero_exit_has_owned_failure(harness, monkeypatch, tmp_path):
    from scripts.run_results import read_execution_result
    client, jobs, commands = harness
    base = pipeline.subprocess.Popen
    class Process(base):
        def wait(self, timeout=None):
            self.returncode = 2
            return 2
    monkeypatch.setattr(pipeline.subprocess, 'Popen', Process)
    response = client.post('/api/run', json={'step': 'lint'})
    jobs[0]()
    meta = pipeline._test_runs[response.json()['log']]
    result = read_execution_result(tmp_path, meta['run_id'])
    assert result['status'] == 'failed'
    assert result['exit_code'] == 2
    assert meta['done'] and meta['returncode'] == 2
    assert result['execute_results']['summary'] == {}


def test_postspawn_persistence_failure_keeps_guard_if_termination_unconfirmed(harness, monkeypatch):
    client, jobs, commands = harness
    saves = [0]
    def save():
        saves[0] += 1
        if saves[0] > 1:
            raise OSError('disk full')
    def stop(proc):
        raise RuntimeError('termination unconfirmed')
    monkeypatch.setattr(pipeline, 'save_running_pids', save)
    monkeypatch.setattr(pipeline, '_terminate_group', stop)
    with pytest.raises(OSError, match='disk full'):
        client.post('/api/run', json={'step': 'generate'})
    assert pipeline._execution_reservation['run']['stopping'] is True
    assert pipeline._running['generate'].poll() is None
    assert jobs == []


@pytest.mark.parametrize('route,body', [
    ('/api/run_all', {'platform': 'android', 'tc_folders': ['one']}),
    ('/api/run_test', {'platform': 'android', 'test_folder': 'one'}),
])
def test_preworker_metadata_failure_releases_unstarted_execution(harness, monkeypatch, route, body):
    client, jobs, commands = harness
    saves = [0]
    def fail_metadata_save():
        saves[0] += 1
        if saves[0] == 2:
            raise OSError('metadata disk full')
    monkeypatch.setattr(pipeline, 'save_running_pids', fail_metadata_save)
    with pytest.raises(OSError, match='metadata disk full'):
        client.post(route, json=body)
    assert not pipeline._execution_reservation
    assert not pipeline._running
    assert jobs == [] and commands == []
    assert not any(not item.get('done') for item in pipeline._pipeline_batches.values())
    assert not any(not item.get('done') for item in pipeline._test_runs.values())


@pytest.mark.parametrize('route,body,kind', [
    ('/api/run_test', {'test_folder': 'one'}, 'quick'),
    ('/api/run_all', {'tc_folders': ['one'], 'from_tc_studio': True}, 'pipeline'),
    ('/api/run', {'step': 'execute', 'tc_folder': 'one'}, 'pipeline'),
])
def test_execution_kind_is_reserved_and_sent_to_children(harness, route, body, kind):
    client, jobs, commands = harness
    assert client.post(route, json=body).status_code == 200
    assert pipeline._execution_reservation['run']['run_type'] == kind
    jobs[0]()
    assert commands and all(env.get('QA_RUN_TYPE') == kind for _, env in commands)


def test_cancel_before_pytest_preserves_execution_kind(harness):
    client, jobs, _ = harness
    client.post('/api/run_test', json={'test_folder': 'one'})
    run = pipeline._execution_reservation['run']
    run['cancelled'] = True
    jobs[0]()
    assert pipeline.read_execution_result(pipeline.PROJECT_ROOT, run['run_id'])['run_type'] == 'quick'
