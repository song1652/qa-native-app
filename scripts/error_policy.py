"""Conservative failure classification. Classification never replays an action."""
import re


_COPY = {
    'appium_unavailable': ('Appium 연결 확인', 'Appium 서버 연결을 확인한 뒤 실행을 다시 시작하세요.', 'check_environment'),
    'device_unavailable': ('선택한 기기 연결 확인', '선택한 기기의 연결과 잠금 상태를 확인하세요. 다른 기기로 자동 전환하지 않습니다.', 'check_environment'),
    'session_lost': ('세션 연결 끊김', '기기와 Appium 상태를 확인하고 Capture를 사용 중이면 세션을 다시 연결하세요.', 'reconnect_capture'),
    'transport': ('통신 연결 오류', '기기와 Appium 연결을 확인하세요. 완료 여부가 불분명한 앱 동작은 자동 반복하지 않습니다.', 'check_environment'),
    'locator': ('요소 확인 필요', '선택한 화면의 요소와 Locator를 검토하세요.', 'review_locator'),
    'assertion': ('검증 결과 불일치', '실제 앱 결과와 테스트의 기대값을 비교하세요.', 'review_assertion'),
    'configuration': ('실행 설정 확인', '테스트 파일, 실행 옵션과 선택한 기기 설정을 확인하세요.', 'review_configuration'),
    'timeout': ('실행 제한 시간 초과', '실행 로그와 기기 상태를 확인한 뒤 필요한 작업을 다시 시작하세요.', 'inspect_log'),
    'interrupted': ('실행 중단', '완료된 결과와 실행 로그를 확인하세요. 남은 앱 동작은 자동으로 실행하지 않습니다.', 'inspect_log'),
    'unknown': ('실행 오류 확인', '실행 로그에서 원인을 확인하세요. 원인이 확인되기 전에는 자동 복구하지 않습니다.', 'inspect_log'),
}


def classify_error(error, status=None):
    """Return category/title/message/action/can_heal/read_retryable only."""
    if isinstance(error, dict):
        text = f"{error.get('error_type', '')} {error.get('error', '')}".lower()
    else:
        text = f"{type(error).__name__ if isinstance(error, BaseException) else ''} {error}".lower()
    category = 'unknown'
    if status == 'timed_out':
        category = 'timeout'
    elif status in ('interrupted', 'cancelled'):
        category = 'interrupted'
    elif 'assertionerror' in text or re.match(r'^\s*assert\s', text):
        category = 'assertion'
    elif any(token in text for token in ('collectionerror', 'syntaxerror', 'importerror', 'modulenotfounderror', 'filenotfounderror',
            'invalidargumentexception', 'invalidselectorexception', 'invalid device mode', 'invalid test file',
            'no tests found', 'no root tests found', 'pytest usage error', 'no tests collected', 'device selection ambiguous',
            'invalid configuration', 'invalid capabilities')):
        category = 'configuration'
    elif any(token in text for token in ('appium server not running', 'appium unavailable', 'econnrefused', 'connectionrefused', 'connection refused')):
        category = 'appium_unavailable'
    elif any(token in text for token in ('device unavailable', 'device/emulator not connected', 'device offline', 'device unauthorized')):
        category = 'device_unavailable'
    elif any(token in text for token in ('invalidsessionid', 'invalid session id', 'nosuchsession', 'session deleted', 'session does not exist',
            'sessionnotcreatedexception', 'instrumentation process is not running', 'uiautomator2 server cannot be proxied')):
        category = 'session_lost'
    elif any(token in text for token in ('connectionreset', 'connection reset', 'readtimeout', 'read timed out',
            'connectionrefused', 'connection refused', 'maxretryerror', 'remotedisconnected', 'brokenpipe', 'socket hang up')):
        category = 'transport'
    elif any(token in text for token in ('nosuchelementexception', 'staleelementreferenceexception')):
        category = 'locator'
    elif 'timeoutexception' in text or 'timeouterror' in text or 'timeoutexpired' in text:
        category = 'timeout'
    title, message, action = _COPY[category]
    read_retryable = category == 'transport' and any(token in text for token in (
        'connectionreset', 'connection reset', 'readtimeout', 'read timed out', 'remotedisconnected'))
    return dict(category=category, title=title, message=message, action=action,
                can_heal=category == 'locator', read_retryable=read_retryable)


def recovery_for_result(result):
    """Mixed or unclassified failures must never enter automatic locator healing."""
    if not isinstance(result, dict):
        return classify_error('')
    status = result.get('status')
    if status in ('timed_out', 'interrupted', 'cancelled'):
        return classify_error('', status=status)
    if status in ('passed', 'running'):
        return classify_error('')
    execution = result.get('execute_results') or {}
    if not isinstance(execution, dict):
        return classify_error('')
    errors = execution.get('errors', [])
    if not isinstance(errors, list):
        return classify_error('')
    classified = [classify_error(error) for error in errors]
    if not classified:
        recovery = classify_error(result.get('error', ''), status=status)
        recovery['can_heal'] = False  # No failed test/locator is available to repair.
        return recovery
    if all(item['can_heal'] for item in classified):
        return classified[0]
    # Prefer the first actionable blocker over the locator symptom it may cause.
    return next(item for item in classified if not item['can_heal'])
