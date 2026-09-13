"""
shared.py — 대시보드 전역 공유 상태.

경로 상수, Python/ADB 바이너리, 프로세스 락, Capture Studio 드라이버,
WebSocket 연결 목록을 한 곳에서 관리합니다.
다른 모듈은 이 파일을 임포트해 사용합니다. 직접 수정하지 말고
공개 헬퍼(get_capture_driver 등)를 통해 접근하세요.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
from pathlib import Path

# ── 경로 상수 ──────────────────────────────────────────────────
HERE         = Path(__file__).parent
PROJECT_ROOT = HERE.parent.parent
PORT         = 8767

STATE_PATH           = PROJECT_ROOT / "state" / "pipeline.json"
CAPTURE_SESSION_PATH = PROJECT_ROOT / "state" / "capture_session.json"
REPORTS_DIR          = PROJECT_ROOT / "tests" / "reports"
GENERATED_DIR        = PROJECT_ROOT / "tests" / "generated"
SCREENSHOTS_DIR      = PROJECT_ROOT / "reports" / "screenshots"
IMPORT_DIR           = PROJECT_ROOT / "import"
LOGS_DIR             = PROJECT_ROOT / "logs"
CAPTURES_DIR         = PROJECT_ROOT / "state" / "captures"
TESTCASES_DIR        = PROJECT_ROOT / "testcases"

for _d in (LOGS_DIR, REPORTS_DIR, SCREENSHOTS_DIR, IMPORT_DIR, CAPTURES_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ── Python / ADB 바이너리 ──────────────────────────────────────

def _find_python_bin() -> str:
    import os
    import shutil

    candidates = [
        os.path.expanduser("~/.pyenv/versions/3.12.9/bin/python"),
        os.path.expanduser("~/.pyenv/shims/python3"),
        shutil.which("python3") or "",
        sys.executable,
    ]
    for c in candidates:
        if not c:
            continue
        try:
            r = subprocess.run(
                [c, "-c", "import appium"],
                capture_output=True, timeout=3,
            )
            if r.returncode == 0:
                return c
        except Exception:
            continue
    return sys.executable


def _find_adb_bin() -> str:
    import os
    import shutil

    candidates = [
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
        "/usr/local/bin/adb",
        shutil.which("adb") or "",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return "adb"


PYTHON_BIN = _find_python_bin()
ADB_BIN    = _find_adb_bin()


# ── 스크립트 맵 ───────────────────────────────────────────────

SCRIPT_MAP: dict[str, tuple[str, list[str], str]] = {
    "analyze":  ("scripts/01_analyze.py",  ["--platform", "{platform}"],                     "run_analyze.txt"),
    "generate": ("scripts/02_generate.py", ["--platform", "{platform}", "--strict-locators"], "run_generate.txt"),
    "lint":     ("scripts/03_lint.py",     [],                                               "run_lint.txt"),
    "execute":  ("scripts/05_execute.py",  ["--platform", "{platform}"],                     "run_execute.txt"),
    "heal":     ("scripts/06_heal.py",     ["--platform", "{platform}"],                     "run_heal.txt"),
}


# ── 동시성 제어 ───────────────────────────────────────────────

_state_lock   = threading.Lock()
_process_lock = threading.Lock()
_running:    dict[str, subprocess.Popen] = {}
_test_runs:  dict[str, dict]             = {}


# ── Capture Studio — Appium 드라이버 관리 ──────────────────────

_capture_driver      = None
_capture_driver_lock = threading.Lock()


def get_capture_driver():
    """현재 _capture_driver 인스턴스를 안전하게 반환."""
    with _capture_driver_lock:
        return _capture_driver


def set_capture_driver(driver) -> None:
    """_capture_driver를 새 드라이버로 설정."""
    global _capture_driver
    with _capture_driver_lock:
        _capture_driver = driver


def clear_capture_driver():
    """_capture_driver를 None으로 초기화하고 이전 값을 반환."""
    global _capture_driver
    with _capture_driver_lock:
        old = _capture_driver
        _capture_driver = None
    return old


# ── WebSocket 연결 관리 (Action Timeline) ─────────────────────

_ws_connections: list = []
_ws_lock = asyncio.Lock()
