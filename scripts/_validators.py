"""대시보드 serve.py 입력 검증 헬퍼.

serve.py는 모듈 최상단에서 백그라운드 스레드를 시작하는 부작용이 있어
테스트에서 직접 import하기 부적합하다. 검증 로직만 이 모듈로 분리해
serve.py와 테스트 양쪽에서 부작용 없이 재사용한다.
"""
from __future__ import annotations

import re
from pathlib import Path


def is_valid_url(url: str) -> bool:
    """URL이 http(s) 스킴으로 시작하는지 검증."""
    return url.startswith(("http://", "https://"))


def is_valid_group_name(name: str) -> bool:
    """그룹명이 영숫자/언더스코어/하이픈만 포함하는지 검증 (경로 탈출 방지).

    Note: $가 아닌 \\Z를 사용해 'abc\\n' 같은 개행 포함 값이 통과하지 못하게 한다.
    """
    return bool(re.match(r'^[\w\-]+\Z', name))


def is_safe_filename(name: str) -> bool:
    """파일명(단일 컴포넌트) 검증 — 경로 탈출·절대경로·구분자를 모두 차단.

    강화 이유: 이전 구현은 '..' 만 검사해 다음 케이스를 허용했음:
      - '/' 포함 → Path(base) / 'sub/../../etc' 탈출 가능
      - 백슬래시 '\\' 포함 (Windows 경로)
      - 절대경로 '/etc/passwd' → Path(base) / '/etc/passwd' == Path('/etc/passwd')
    """
    if not name or ".." in name:
        return False
    if "/" in name or "\\" in name:
        return False
    if Path(name).is_absolute():
        return False
    return True
