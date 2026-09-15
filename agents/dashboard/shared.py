"""
shared.py — 대시보드 전역 공유 상태.

경로 상수, Python/ADB 바이너리, 프로세스 락, Capture Studio 드라이버,
WebSocket 연결 목록을 한 곳에서 관리합니다.
다른 모듈은 이 파일을 임포트해 사용합니다. 직접 수정하지 말고
공개 헬퍼(get_capture_driver 등)를 통해 접근하세요.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
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
ENV_SESSION_PATH     = PROJECT_ROOT / "state" / "env_session.json"
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

def _is_executable(path: str | Path) -> bool:
    candidate = Path(path).expanduser()
    return candidate.is_file() and os.access(candidate, os.X_OK)


def _node_version_key(path: Path) -> tuple[int, ...]:
    match = re.search(r"/v(\d+(?:\.\d+)*)/bin/", str(path))
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def _find_appium_bin(
    home: Path | None = None,
    environ: dict | None = None,
    path_lookup=None,
) -> str:
    """NVM을 포함해 비대화형 서버에서도 Appium 실행 파일을 찾는다."""
    home = Path.home() if home is None else Path(home)
    environ = os.environ if environ is None else environ
    path_lookup = shutil.which if path_lookup is None else path_lookup

    candidates: list[str | Path] = []
    if environ.get("APPIUM_BIN"):
        candidates.append(environ["APPIUM_BIN"])
    path_appium = path_lookup("appium")
    if path_appium:
        candidates.append(path_appium)
    candidates.extend([
        home / ".local" / "bin" / "appium",
        Path("/opt/homebrew/bin/appium"),
        Path("/usr/local/bin/appium"),
    ])
    nvm_candidates = sorted(
        (home / ".nvm" / "versions" / "node").glob("v*/bin/appium"),
        key=_node_version_key,
        reverse=True,
    )
    candidates.extend(nvm_candidates)
    for candidate in candidates:
        if _is_executable(candidate):
            return str(Path(candidate).expanduser())
    return "appium"


def _find_emulator_bin(
    home: Path | None = None,
    environ: dict | None = None,
    path_lookup=None,
) -> str:
    """ANDROID_HOME이 없는 GUI 실행에서도 Android Emulator를 찾는다."""
    home = Path.home() if home is None else Path(home)
    environ = os.environ if environ is None else environ
    path_lookup = shutil.which if path_lookup is None else path_lookup

    candidates: list[str | Path] = []
    if environ.get("EMULATOR_BIN"):
        candidates.append(environ["EMULATOR_BIN"])
    for key in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        if environ.get(key):
            candidates.append(Path(environ[key]) / "emulator" / "emulator")
    candidates.extend([
        home / "Library" / "Android" / "sdk" / "emulator" / "emulator",
        home / "Android" / "Sdk" / "emulator" / "emulator",
    ])
    path_emulator = path_lookup("emulator")
    if path_emulator:
        candidates.append(path_emulator)
    for candidate in candidates:
        if _is_executable(candidate):
            return str(Path(candidate).expanduser())
    return "emulator"


def subprocess_env_for(
    binary: str,
    home: Path | None = None,
    environ: dict | None = None,
) -> dict[str, str]:
    """Build a GUI-safe environment for Appium and Android tooling."""
    home = Path.home() if home is None else Path(home)
    env = dict(os.environ if environ is None else environ)
    binary_dir = str(Path(binary).expanduser().parent)
    current_path = env.get("PATH", "")
    path_parts = [part for part in current_path.split(os.pathsep) if part]

    sdk_root = env.get("ANDROID_SDK_ROOT") or env.get("ANDROID_HOME")
    if not sdk_root:
        for candidate in (home / "Library" / "Android" / "sdk", home / "Android" / "Sdk"):
            if candidate.is_dir():
                sdk_root = str(candidate)
                break
    if sdk_root:
        env.setdefault("ANDROID_HOME", sdk_root)
        env.setdefault("ANDROID_SDK_ROOT", sdk_root)
        path_parts = [str(Path(sdk_root) / "platform-tools"), str(Path(sdk_root) / "emulator")] + path_parts

    env["PATH"] = os.pathsep.join(
        [binary_dir] + [part for part in path_parts if part != binary_dir]
    )
    return env

def _find_python_bin() -> str:
    import os
    import shutil

    candidates = [
        str(PROJECT_ROOT / ".venv" / "bin" / "python"),
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
                [c, "-c", "import appium, pytest"],
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
APPIUM_BIN = _find_appium_bin()
EMULATOR_BIN = _find_emulator_bin()


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
