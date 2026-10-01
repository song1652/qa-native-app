"""TC 스튜디오가 사용하는 앱 저장소 경로와 파일 잠금."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TC_LIBRARY_DIR = PROJECT_ROOT / "state" / "tc_library"
IMPORT_PROFILES_PATH = TC_LIBRARY_DIR / "_mapping_profiles.json"
IMPORT_DIR = PROJECT_ROOT / "import"
IMPORT_SESSIONS_DIR = PROJECT_ROOT / "state" / "import_sessions"
IMPORT_SNAPSHOTS_DIR = PROJECT_ROOT / "state" / "import_snapshots"
TESTCASES_DIR = PROJECT_ROOT / "testcases"
PAGES_JSON = PROJECT_ROOT / "config" / "pages.json"
LOCK_TIMEOUT_SECS = 10.0


@contextmanager
def _file_lock(lock_path: Path, target: Path, timeout_secs: float = LOCK_TIMEOUT_SECS):
    """상태 파일을 읽거나 쓸 때 프로세스 간 배타적으로 잠근다."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            if lock.seek(0, os.SEEK_END) == 0:
                lock.write(b"0")
                lock.flush()
            deadline = time.monotonic() + timeout_secs
            while True:
                lock.seek(0)
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"파일 잠금 시간 초과: {target}") from exc
                    time.sleep(0.05)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
