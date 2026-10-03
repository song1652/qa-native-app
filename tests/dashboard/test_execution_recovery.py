"""Recovery/watchdog tests use temporary state and mocked process identities only."""
import json
import pytest
from agents.dashboard.routes import pipeline
import shared


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    for module in (shared, pipeline):
        for name in ('_running', '_test_runs', '_execution_reservation', '_pipeline_batches'):
            monkeypatch.setattr(module, name, {}, raising=False)
        monkeypatch.setattr(module, 'PROJECT_ROOT', tmp_path)
    # Both modules must reference the same containers.
    for name in ('_running', '_test_runs', '_execution_reservation', '_pipeline_batches'):
        monkeypatch.setattr(pipeline, name, getattr(shared, name))
    monkeypatch.setattr(shared, '_RUNNING_PIDS_PATH', tmp_path / 'running_procs.json')
    monkeypatch.setattr(pipeline, 'save_state', lambda _: None)
    monkeypatch.setattr(pipeline, 'read_state', lambda: {})
    monkeypatch.setattr(shared, 'process_identity', lambda pid: None, raising=False)
    monkeypatch.setattr(shared, 'process_group_members', lambda pid: {})
    return tmp_path


def test_snapshot_restores_log_mapping_and_interrupts_queued_batch(isolated):
    run = {'id': 'logical', 'run_id': 'run_one', 'step': 'execute', 'done': False, 'cancelled': False}
    shared._execution_reservation['run'] = run
    shared._pipeline_batches['batch'] = run
    shared._test_runs['log.txt'] = {'key': 'execute', 'run_id': 'run_one', 'done': False, 'returncode': None}
    shared.save_running_pids()
    shared._execution_reservation.clear()
    shared._test_runs.clear()
    shared._pipeline_batches.clear()
    shared.restore_running_procs()
    pipeline.reconcile_recovered_execution()
    assert shared._test_runs['log.txt']['done'] is True
    assert shared._test_runs['log.txt']['returncode'] is None
    assert shared._pipeline_batches['batch']['status'] == 'interrupted'
    assert not shared._execution_reservation


def test_timeout_blocks_retry_and_persists_terminal_result(monkeypatch, isolated):
    class Proc:
        pid = 99999
        returncode = -15
        def wait(self, timeout=None):
            raise pipeline.subprocess.TimeoutExpired('fake', timeout)
    run = {'run_id': 'run_timeout', 'cancelled': False}
    monkeypatch.setattr(pipeline, '_terminate_group', lambda proc: None)
    proc = Proc()
    proc.deadline_at = 0
    pipeline._wait_stage(proc, run)
    pipeline._finalize_run(run)
    result = pipeline.read_execution_result(isolated, 'run_timeout')
    assert run['cancelled'] is True
    assert result['status'] == 'timed_out'


def test_invalid_timeout_uses_finite_default(monkeypatch):
    monkeypatch.setenv('QA_STAGE_TIMEOUT_SECONDS', 'nan')
    assert pipeline._stage_timeout() == 1800


def test_recovery_preserves_completed_run_result(isolated):
    pipeline.write_execution_result(isolated, 'run_done', {'status': 'passed', 'exit_code': 0,
                                    'execute_results': {'summary': {'passed': 2}}})
    shared._execution_reservation['run'] = {'run_id': 'run_done', 'recovered_after_restart': True}
    shared._test_runs['log.txt'] = {'key': 'execute', 'run_id': 'run_done', 'done': False}
    pipeline.reconcile_recovered_execution()
    assert pipeline.read_execution_result(isolated, 'run_done')['status'] == 'passed'
    assert shared._test_runs['log.txt']['returncode'] == 0


def test_recovered_live_process_keeps_guard_and_mapping(monkeypatch, isolated):
    identity = {'started': 'today', 'pgid': 99, 'command': 'our stage'}
    monkeypatch.setattr(shared, 'process_identity', lambda pid: identity)
    shared._RUNNING_PIDS_PATH.write_text(json.dumps({'version': 2,
        'processes': {'execute': {'pid': 99, 'identity': identity, 'deadline_at': 9999999999}},
        'reservation': {'run': {'id': 'one', 'run_id': 'run_live', 'done': False}},
        'test_runs': {'log.txt': {'key': 'execute', 'run_id': 'run_live', 'done': False}}, 'batches': {}}))
    shared.restore_running_procs()
    assert pipeline.reconcile_recovered_execution() is False
    assert shared.execution_active_locked()
    assert shared._test_runs['log.txt']['done'] is False


@pytest.mark.parametrize('legacy', [False, True])
def test_unverified_pid_never_gets_signalled(monkeypatch, isolated, legacy):
    old = {'started': 'old', 'pgid': 99, 'command': 'stage'}
    new = {'started': 'new', 'pgid': 99, 'command': 'unrelated'}
    monkeypatch.setattr(shared, 'process_identity', lambda pid: new)
    proc = shared._PidOnlyProc(99, None if legacy else old)
    monkeypatch.setattr(pipeline.os, 'killpg', lambda *args: pytest.fail('must not signal unknown owner'))
    with pytest.raises(RuntimeError, match='소유권'):
        pipeline._terminate_group(proc)


def test_timeout_termination_failure_retains_busy_guard(monkeypatch, isolated):
    class Proc:
        pid = 99
        deadline_at = 0
        def wait(self, timeout=None):
            raise pipeline.subprocess.TimeoutExpired('fake', timeout)
    run = {'run_id': 'run_timeout', 'cancelled': False}
    shared._execution_reservation['run'] = run
    def fail(_):
        raise RuntimeError('still alive')
    monkeypatch.setattr(pipeline, '_terminate_group', fail)
    with pytest.raises(RuntimeError, match='still alive'):
        pipeline._wait_stage(Proc(), run)
    pipeline._release(run)
    assert shared.execution_active_locked()
    assert run['stopping'] is True


def test_recovered_descendant_identity_allows_group_termination(monkeypatch, isolated):
    identity = {'started': 'old', 'pgid': 99, 'command': 'pytest child'}
    monkeypatch.setattr(shared, 'process_identity', lambda pid: identity if pid == 100 else None)
    proc = shared._PidOnlyProc(99, members={'100': identity})
    assert proc.owned()


def test_malformed_snapshot_fields_keep_valid_live_owner(monkeypatch, isolated):
    identity = {'started': 'today', 'pgid': 99, 'command': 'stage'}
    monkeypatch.setattr(shared, 'process_identity', lambda pid: identity)
    shared._RUNNING_PIDS_PATH.write_text(json.dumps({'version': 2,
        'test_runs': ['invalid'], 'batches': 4, 'reservation': {'run': 'invalid'},
        'processes': {'execute': {'pid': 99, 'identity': identity, 'deadline_at': 'bad', 'members': None}}}))
    assert shared.restore_running_procs()['restored'] == ['execute']
    assert shared.execution_active_locked()


def test_initial_persistence_failure_releases_unstarted_reservation(monkeypatch, isolated):
    monkeypatch.setattr(pipeline, 'is_capture_active', lambda _: False)
    def fail():
        raise OSError('disk full')
    monkeypatch.setattr(pipeline, 'save_running_pids', fail)
    with pytest.raises(OSError):
        pipeline._reserve('android', 'execute')
    assert not shared._execution_reservation


def test_worker_failure_does_not_release_alive_process(monkeypatch, isolated):
    class Proc:
        def poll(self):
            return None
    shared._running['execute'] = Proc()
    run = {'run_id': 'run_alive'}
    shared._execution_reservation['run'] = run
    monkeypatch.setattr(pipeline, 'save_running_pids', lambda: None)
    pipeline._release(run)
    assert shared._execution_reservation['run'] is run


def test_recovered_run_log_returns_run_owned_interruption(monkeypatch, isolated):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(pipeline, 'LOGS_DIR', isolated)
    shared._execution_reservation['run'] = {'run_id': 'run_lost', 'recovered_after_restart': True}
    shared._test_runs['log.txt'] = {'key': 'execute', 'run_id': 'run_lost', 'done': False, 'returncode': None}
    pipeline.reconcile_recovered_execution()
    app = FastAPI()
    app.include_router(pipeline.router)
    payload = TestClient(app).post('/api/run_log', json={'log': 'log.txt'}).json()
    assert payload['done'] is True
    assert payload['exit_code'] is None
    assert payload['run_id'] == 'run_lost'
    assert payload['result']['status'] == 'interrupted'


@pytest.mark.parametrize('persistent', [False, True])
def test_group_probe_permission_error_is_bounded_and_never_confirms_exit(monkeypatch, isolated, persistent):
    from types import SimpleNamespace
    clock = [0.0]
    signals = []
    monkeypatch.setattr(pipeline.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(pipeline.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    probes = [0]
    def killpg(pid, signal):
        signals.append(signal)
        if signal == 0:
            probes[0] += 1
            if persistent or probes[0] == 1:
                raise PermissionError('transient macOS process teardown')
            raise ProcessLookupError
    monkeypatch.setattr(pipeline.os, 'killpg', killpg)
    proc = SimpleNamespace(pid=99, poll=lambda: -15)
    if persistent:
        with pytest.raises(RuntimeError, match='종료를 확인'):
            pipeline._terminate_group(proc)
        assert 6 <= clock[0] < 6.2
    else:
        pipeline._terminate_group(proc)
        assert signals == [15, 0, 0]
        assert clock[0] == 0.05


def test_signalled_stage_stops_workflow_and_drains_descendants(monkeypatch, isolated):
    from types import SimpleNamespace
    run = {'run_id': 'run_signalled', 'cancelled': False}
    proc = SimpleNamespace(pid=99, returncode=-9, wait=lambda timeout=None: -9)
    stopped = []
    monkeypatch.setattr(pipeline, '_terminate_group', lambda child: stopped.append(child))
    pipeline._wait_stage(proc, run)
    pipeline._finalize_run(run)
    assert stopped == [proc]
    assert run['cancelled'] is True
    assert run['stopping'] is False
    assert pipeline.read_execution_result(isolated, 'run_signalled')['status'] == 'interrupted'


def test_signalled_stage_keeps_guard_when_descendants_cannot_stop(monkeypatch, isolated):
    from types import SimpleNamespace
    run = {'run_id': 'run_signalled', 'cancelled': False}
    proc = SimpleNamespace(pid=99, returncode=-9, wait=lambda timeout=None: -9)
    shared._execution_reservation['run'] = run
    def fail(child):
        raise RuntimeError('descendants still alive')
    monkeypatch.setattr(pipeline, '_terminate_group', fail)
    with pytest.raises(RuntimeError, match='descendants still alive'):
        pipeline._wait_stage(proc, run)
    pipeline._release(run)
    assert run['stopping'] is True
    assert shared.execution_active_locked()


def test_recovery_monitor_never_removes_replacement_run(monkeypatch, isolated):
    from types import SimpleNamespace
    old_run = {'id': 'old', 'run_id': 'run_old', 'recovered_after_restart': True}
    new_run = {'id': 'new', 'run_id': 'run_new', 'done': False}
    replacement = SimpleNamespace(poll=lambda: None)
    shared._execution_reservation['run'] = old_run
    old = shared._PidOnlyProc(99)
    def replace_during_probe():
        shared._execution_reservation['run'] = new_run
        shared._running['execute'] = replacement
        shared._test_runs['log.txt'] = {'run_id': 'run_new', 'done': False}
        return -1
    monkeypatch.setattr(old, 'poll', replace_during_probe)
    shared._running['execute'] = old
    pipeline.reconcile_recovered_execution()
    assert shared._running['execute'] is replacement
    assert shared._execution_reservation['run'] is new_run
    assert shared._test_runs['log.txt']['done'] is False


def test_run_ids_are_unique_when_wall_clock_does_not_advance(monkeypatch):
    monkeypatch.setattr(pipeline.time, 'time', lambda: 1234567890.123)
    monkeypatch.setattr(pipeline, '_last_run_ms', 0)
    values = [pipeline._gen_run_id('android') for _ in range(10)]
    assert len(set(values)) == 10
    import re
    assert all(re.fullmatch(r'run_android_\d{8}_\d{6}_\d{3}', value) for value in values)


def test_recovered_folder_gap_preserves_pass_and_records_unfinished_workflow(isolated):
    run = {'id': 'batch-run', 'run_id': 'run_done', 'recovered_after_restart': True, 'done': False}
    shared._execution_reservation['run'] = run
    shared._pipeline_batches['batch'] = run
    pipeline.write_execution_result(isolated, 'run_done', {'status': 'passed', 'exit_code': 0,
        'execute_results': {'summary': {'passed': 2}}})
    pipeline.reconcile_recovered_execution()
    result = pipeline.read_execution_result(isolated, 'run_done')
    assert result['status'] == 'passed' and result['exit_code'] == 0
    assert result['execute_results']['summary'] == {'passed': 2}
    assert result['workflow_status'] == 'interrupted'
    assert result['workflow_error']
