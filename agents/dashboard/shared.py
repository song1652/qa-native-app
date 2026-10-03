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
LOGS_DIR             = PROJECT_ROOT / "logs"
CAPTURES_DIR         = PROJECT_ROOT / "state" / "captures"
TESTCASES_DIR        = PROJECT_ROOT / "testcases"

for _d in (LOGS_DIR, REPORTS_DIR, SCREENSHOTS_DIR, CAPTURES_DIR):
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
    "lint":     ("scripts/03_lint.py",     ["--platform", "{platform}"],                     "run_lint.txt"),
    "execute":  ("scripts/05_execute.py",  ["--platform", "{platform}"],                     "run_execute.txt"),
    "heal":     ("scripts/06_heal.py",     ["--platform", "{platform}"],                     "run_heal.txt"),
}


# ── 동시성 제어 ───────────────────────────────────────────────

_state_lock   = threading.Lock()
_process_lock = threading.Lock()
_running:    dict[str, subprocess.Popen] = {}
_test_runs:  dict[str, dict]             = {}
# ponytail: serialize execution while pipeline state and generated files are shared.
_execution_reservation: dict = {}
_pipeline_batches: dict[str, dict] = {}
_capture_launch_active = False


def execution_active_locked() -> bool:
    """Caller holds _process_lock; includes queued work and gaps between stages."""
    return _capture_launch_active or bool(_execution_reservation) or any(p.poll() is None for p in _running.values())

# ── 서버 재시작 후 고아 프로세스 복구 ────────────────────────────

_RUNNING_PIDS_PATH = PROJECT_ROOT / "state" / "running_procs.json"


def process_identity(pid: int) -> dict | None:
    """PID creation time and command protect against a recycled PID (macOS/Linux)."""
    try:
        output = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart=", "-o", "pgid=", "-o", "command="],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip().split(None, 6)
        if len(output) != 7:
            return None
        return {"started": " ".join(output[:5]), "pgid": int(output[5]), "command": output[6]}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def process_group_members(pgid):
    try:
        output = subprocess.run(["ps", "-axo", "pid=,pgid=,lstart=,command="],
                                capture_output=True, text=True, timeout=3).stdout
        members = {}
        for line in output.splitlines():
            parts = line.split(None, 7)
            if len(parts) == 8 and int(parts[1]) == pgid:
                members[str(int(parts[0]))] = {"pgid": pgid, "started": " ".join(parts[2:7]), "command": parts[7]}
        return members
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}


class _PidOnlyProc:
    """Recovered process: disappearance is not an observed child exit code."""

    def __init__(self, pid, identity=None, deadline_at=None, members=None):
        self.pid = pid
        self.identity = identity
        self.deadline_at = deadline_at
        self.returncode = None
        self.members = members or {}

    def owned(self):
        current = process_identity(self.pid)
        if current is not None:
            return bool(self.identity and current == self.identity and current.get("pgid") == self.pid)
        return any(process_identity(int(pid)) == identity and identity.get("pgid") == self.pid
                   for pid, identity in self.members.items())

    def poll(self):
        current = process_identity(self.pid)
        if current is not None and (not self.identity or current == self.identity):
            return None
        # A surviving descendant can still own the Appium session. Keep the
        # reservation until the group disappears, but never signal an unverified PID.
        try:
            os.killpg(self.pid, 0)
            return None
        except ProcessLookupError:
            return -1
        except PermissionError:
            return None


def save_running_pids() -> None:
    """Atomic logical execution snapshot. Caller holds _process_lock."""
    import json
    import tempfile
    processes = {}
    for key, proc in _running.items():
        if not hasattr(proc, "identity"):
            proc.identity = process_identity(proc.pid)
        if not isinstance(proc, _PidOnlyProc):
            proc.members = process_group_members(proc.pid)
        processes[key] = {"pid": proc.pid, "identity": proc.identity, "members": proc.members,
                          "deadline_at": getattr(proc, "deadline_at", None)}
    data = {"version": 2, "processes": processes,
            "reservation": {"run": _execution_reservation["run"]} if _execution_reservation.get("run") else {},
            "test_runs": _test_runs, "batches": _pipeline_batches}
    _RUNNING_PIDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=_RUNNING_PIDS_PATH.parent,
                                         prefix=".running-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(_RUNNING_PIDS_PATH)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def restore_running_procs() -> dict[str, list[str]]:
    """Restore durable metadata; legacy identities block but cannot be signalled."""
    import json
    result = {"restored": [], "discarded": []}
    try:
        data = json.loads(_RUNNING_PIDS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result
    if not isinstance(data, dict):
        return result
    with _process_lock:
        if data.get("version") == 2:
            for field, target in (("test_runs", _test_runs), ("batches", _pipeline_batches)):
                records = data.get(field)
                if isinstance(records, dict):
                    target.update({key: value for key, value in records.items()
                                   if isinstance(key, str) and isinstance(value, dict)})
            for meta in _test_runs.values():
                meta.setdefault("key", "")
                meta.setdefault("done", False)
                meta.setdefault("returncode", None)
            reservation = data.get("reservation")
            if isinstance(reservation, dict) and isinstance(reservation.get("run"), dict):
                _execution_reservation["run"] = reservation["run"]
            run = _execution_reservation.get("run")
            if run:
                run["recovered_after_restart"] = True
                for key, batch in _pipeline_batches.items():
                    if batch.get("id") == run.get("id"):
                        _pipeline_batches[key] = run
            processes = data.get("processes", {})
            if not isinstance(processes, dict):
                processes = {}
        else:
            processes = {key: {"pid": pid} for key, pid in data.items()}
        for key, record in processes.items():
            pid = record.get("pid") if isinstance(record, dict) else None
            if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
                result["discarded"].append(str(key))
                continue
            identity = record.get("identity")
            identity = identity if isinstance(identity, dict) else None
            members = record.get("members")
            members = {key: value for key, value in members.items() if str(key).isdigit() and isinstance(value, dict)} if isinstance(members, dict) else {}
            deadline = record.get("deadline_at")
            import math
            deadline = deadline if isinstance(deadline, (float, int)) and math.isfinite(deadline) and deadline > 0 else None
            proc = _PidOnlyProc(pid, identity, deadline, members)
            if proc.poll() is None:
                _running[key] = proc
                result["restored"].append(key)
            else:
                result["discarded"].append(key)
    return result


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


def clear_capture_driver(expected=None):
    """_capture_driver를 None으로 초기화하고 이전 값을 반환."""
    global _capture_driver
    with _capture_driver_lock:
        old = _capture_driver
        if expected is not None and old is not expected:
            return None
        _capture_driver = None
    return old


# ── WebSocket 연결 관리 (Action Timeline) ─────────────────────

_ws_connections: list = []
_ws_lock = asyncio.Lock()
