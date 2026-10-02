"""pytest-json-report leaves rerun status after the final attempt passes."""
import importlib.util
import json
from pathlib import Path

import pytest


def _parse(tmp_path, tests, summary):
    path = Path(__file__).parents[2] / 'scripts/05_execute.py'
    spec = importlib.util.spec_from_file_location('execute_json_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = tmp_path / 'report.json'
    report.write_text(json.dumps({'tests': tests, 'summary': summary}))
    return module.parse_json_report(report)


def test_final_pass_after_rerun_restores_case_and_summary(tmp_path):
    tests = [
        {'nodeid': 'tests/generated/android/tc_first.py::test_first', 'outcome': 'passed'},
        {'nodeid': 'tests/generated/android/tc_second.py::test_second', 'outcome': 'passed'},
        {'nodeid': 'tests/generated/android/tc_retry.py::test_retry', 'outcome': 'rerun',
         'setup': {'outcome': 'passed'}, 'call': {'outcome': 'passed'},
         'teardown': {'outcome': 'passed'}},
    ]
    result = _parse(tmp_path, tests, {'passed': 2, 'rerun': 1, 'total': 3})
    assert result['summary'] == {'total': 3, 'passed': 3, 'failed': 0}
    assert result['passed'] == [test['nodeid'] for test in tests]
    assert result['errors'] == []


@pytest.mark.parametrize('failed_phase', ['setup', 'call', 'teardown'])
def test_rerun_without_successful_final_attempt_is_not_added_to_passes(tmp_path, failed_phase):
    test = {'nodeid': 'tc_retry.py::test_retry', 'outcome': 'rerun',
            'setup': {'outcome': 'passed'}, 'call': {'outcome': 'passed'},
            'teardown': {'outcome': 'passed'}}
    test[failed_phase]['outcome'] = 'failed'
    result = _parse(tmp_path, [test], {'rerun': 1, 'passed': 0, 'total': 1})
    assert result['passed'] == []
    assert result['summary']['passed'] == 0
