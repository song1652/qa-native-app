"""Automatic locator repair never replays environmental or assertion failures."""
from types import SimpleNamespace

import pytest

from tests.dashboard.test_execution_admission import harness  # noqa: F401
from agents.dashboard.routes import pipeline
from scripts.run_results import write_execution_result


@pytest.mark.parametrize('quick', [True, False])
@pytest.mark.parametrize('errors', [
    ['AssertionError: expected title'],
    ['Appium server not running'],
    ['InvalidSessionIdException: session ended'],
    ['ConnectionResetError: connection reset by peer'],
    ['unknown failure'],
    ['NoSuchElementException: element not found', 'AssertionError: expected title'],
])
def test_non_locator_failure_is_not_automatically_healed(harness, monkeypatch, quick, errors):
    client, jobs, commands = harness
    base = pipeline.subprocess.Popen
    class Process(base):
        def __init__(self, command, **kwargs):
            super().__init__(command, **kwargs)
            self.command, self.env = command, kwargs['env']
        def wait(self, timeout=None):
            self.returncode = 0
            if '05_execute.py' in self.command[2]:
                self.returncode = 1
                write_execution_result(pipeline.PROJECT_ROOT, self.env['QA_RUN_ID'], {
                    'status': 'failed', 'platform': 'android', 'exit_code': 1,
                    'execute_results': {'summary': {}, 'errors': [{'error': text} for text in errors]},
                })
            return self.returncode
    monkeypatch.setattr(pipeline.subprocess, 'Popen', Process)
    monkeypatch.setattr(pipeline.subprocess, 'run', lambda *_a, **_k: SimpleNamespace(stdout='', stderr=''))
    path = '/api/run_test' if quick else '/api/run_all'
    body = {'test_folder': 'one', 'heal': True} if quick else {'tc_folders': ['one'], 'from_tc_studio': True}
    assert client.post(path, json=body).status_code == 200
    jobs[0]()
    assert len([cmd for cmd, _ in commands if '05_execute.py' in cmd[2]]) == 1
    assert not [cmd for cmd, _ in commands if '06_heal.py' in cmd[2]]


def test_locator_repair_stops_when_new_failure_changes_category(harness, monkeypatch):
    client, jobs, commands = harness
    attempts = []
    base = pipeline.subprocess.Popen
    class Process(base):
        def __init__(self, command, **kwargs):
            super().__init__(command, **kwargs)
            self.command, self.env = command, kwargs['env']
        def wait(self, timeout=None):
            self.returncode = 0
            if '05_execute.py' in self.command[2]:
                attempts.append(1)
                self.returncode = 1
                message = 'NoSuchElementException: element not found' if len(attempts) == 1 else 'AssertionError: expected title'
                write_execution_result(pipeline.PROJECT_ROOT, self.env['QA_RUN_ID'], {
                    'status': 'failed', 'platform': 'android', 'exit_code': 1,
                    'execute_results': {'errors': [{'error': message}], 'summary': {}},
                })
            return self.returncode
    monkeypatch.setattr(pipeline.subprocess, 'Popen', Process)
    monkeypatch.setattr(pipeline.subprocess, 'run', lambda *_a, **_k: SimpleNamespace(stdout='', stderr=''))
    client.post('/api/run_all', json={'tc_folders': ['one'], 'from_tc_studio': True})
    jobs[0]()
    assert len(attempts) == 2
    assert len([cmd for cmd, _ in commands if '06_heal.py' in cmd[2]]) == 1


@pytest.mark.parametrize('quick', [True, False])
def test_failed_heal_verification_does_not_replay_stale_locator_failure(harness, monkeypatch, quick):
    client, jobs, commands = harness
    base = pipeline.subprocess.Popen
    class Process(base):
        def __init__(self, command, **kwargs):
            super().__init__(command, **kwargs)
            self.command, self.env = command, kwargs['env']
        def wait(self, timeout=None):
            self.returncode = 0
            if '05_execute.py' in self.command[2]:
                self.returncode = 1
                write_execution_result(pipeline.PROJECT_ROOT, self.env['QA_RUN_ID'], {
                    'status': 'failed', 'platform': 'android', 'exit_code': 1,
                    'execute_results': {'errors': [{'error': 'NoSuchElementException: element not found'}], 'summary': {}},
                })
            elif '06_heal.py' in self.command[2]:
                self.returncode = 1
            return self.returncode
    monkeypatch.setattr(pipeline.subprocess, 'Popen', Process)
    monkeypatch.setattr(pipeline.subprocess, 'run', lambda *_a, **_k: SimpleNamespace(stdout='', stderr=''))
    path = '/api/run_test' if quick else '/api/run_all'
    body = {'test_folder': 'one', 'heal': True} if quick else {'tc_folders': ['one'], 'from_tc_studio': True}
    assert client.post(path, json=body).status_code == 200
    jobs[0]()
    assert len([cmd for cmd, _ in commands if '06_heal.py' in cmd[2]]) == 1
    assert len([cmd for cmd, _ in commands if '05_execute.py' in cmd[2]]) == 1
