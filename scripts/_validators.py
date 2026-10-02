"""대시보드 serve.py 입력 검증 헬퍼.

serve.py는 모듈 최상단에서 백그라운드 스레드를 시작하는 부작용이 있어
테스트에서 직접 import하기 부적합하다. 검증 로직만 이 모듈로 분리해
serve.py와 테스트 양쪽에서 부작용 없이 재사용한다.
"""
from __future__ import annotations

import re


def is_valid_group_name(name: str) -> bool:
    """그룹명이 영숫자/언더스코어/하이픈만 포함하는지 검증 (경로 탈출 방지).

    Note: $가 아닌 \\Z를 사용해 'abc\\n' 같은 개행 포함 값이 통과하지 못하게 한다.
    """
    return bool(re.match(r'^[\w\-]+\Z', name))

