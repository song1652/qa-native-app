"""Error policy is pure data; never contacts devices or services."""
import pytest


def policy():
    from scripts.error_policy import classify_error, recovery_for_result
    return classify_error, recovery_for_result


@pytest.mark.parametrize('error,category', [
    ('Appium server not running', 'appium_unavailable'),
    ('Selected Android device unavailable', 'device_unavailable'),
    ('InvalidSessionIdException: session deleted', 'session_lost'),
    ('ConnectionResetError: peer reset connection', 'transport'),
    ('NoSuchElementException: cannot locate element', 'locator'),
    ('AssertionError: expected NoSuchElementException', 'assertion'),
    ('SyntaxError: invalid syntax', 'configuration'),
    ('unrecognized error containing secret token', 'unknown'),
])
def test_error_category_has_safe_actionable_copy(error, category):
    classify, _ = policy()
    value = classify(error)
    assert value['category'] == category
    assert set(value) == {'category', 'title', 'message', 'action', 'can_heal', 'read_retryable'}
    assert 'secret token' not in value['message']
    assert value['can_heal'] is (category == 'locator')


@pytest.mark.parametrize('status,category', [('timed_out', 'timeout'), ('interrupted', 'interrupted'), ('cancelled', 'interrupted')])
def test_terminal_status_blocks_healing(status, category):
    classify, aggregate = policy()
    result = aggregate({'status': status, 'execute_results': {'errors': [{'error': 'NoSuchElementException'}]}})
    assert result['category'] == category and not result['can_heal']
    assert not result['read_retryable']


def test_mixed_failure_never_heals_assertion_or_unknown():
    _, aggregate = policy()
    for other in ('AssertionError: fail', 'unexpected unknown error'):
        result = aggregate({'status': 'failed', 'execute_results': {'errors': [
            {'error': 'NoSuchElementException'}, {'error': other}]}})
        assert not result['can_heal']
    assert aggregate({'status': 'failed', 'execute_results': {'errors': [
        {'error': 'NoSuchElementException'}, {'error': 'StaleElementReferenceException'}]}})['can_heal']


@pytest.mark.parametrize('message,expected', [('ConnectionResetError', True), ('ReadTimeoutError', True),
    ('ConnectionRefusedError', False), ('InvalidSessionIdException', False), ('TimeoutException', False)])
def test_read_retry_requires_known_completed_transport_error(message, expected):
    classify, _ = policy()
    assert classify(message)['read_retryable'] is expected


@pytest.mark.parametrize('message,category', [('invalid session id', 'session_lost'),
    ('ECONNREFUSED', 'appium_unavailable'), ('ConnectionRefusedError wrapped by ReadTimeoutError', 'appium_unavailable')])
def test_plain_transport_messages_prioritize_nonretryable_session_and_refusal(message, category):
    classify, _ = policy()
    result = classify(message)
    assert result['category'] == category and not result['read_retryable']


def test_nonfailed_result_cannot_trigger_healing():
    _, aggregate = policy()
    for status in ('passed', 'running'):
        assert not aggregate({'status': status, 'execute_results': {'errors': [{'error': 'NoSuchElementException'}]}})['can_heal']


@pytest.mark.parametrize('result', [None, [], {'execute_results': []},
    {'execute_results': {'errors': {}}}, {'execute_results': {'errors': [None, 123]}},
    {'status': 'failed', 'error': 'NoSuchElementException'}])
def test_malformed_or_unscoped_errors_never_heal(result):
    _, aggregate = policy()
    recovery = aggregate(result)
    assert not recovery['can_heal']
    assert recovery['category'] in ('unknown', 'locator')
