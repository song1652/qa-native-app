"""
utils/state.py — 파이프라인/캡처 세션 상태 읽기쓰기, 파일 목록 조회.
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import copy

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import (  # noqa: E402
    STATE_PATH,
    CAPTURE_SESSION_PATH,
    ENV_SESSION_PATH,
    REPORTS_DIR,
    GENERATED_DIR,
    SCREENSHOTS_DIR,
    IMPORT_DIR,
    TESTCASES_DIR,
    PROJECT_ROOT,
    _state_lock,
    _process_lock,
    _running,
)


# ── JSON 읽기/쓰기 ────────────────────────────────────────────

def load_json(path: Path) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_state(state: dict) -> None:
    with _state_lock:
        STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def read_state() -> dict:
    with _state_lock:
        return load_json(STATE_PATH) or {}


# ── Capture Studio 세션 ───────────────────────────────────────

def load_capture_session() -> dict:
    return load_json(CAPTURE_SESSION_PATH) or {}


def save_capture_session(data: dict) -> None:
    CAPTURE_SESSION_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def is_capture_active(platform: str | None = None) -> bool:
    """Capture Studio 세션이 활성 상태인지 확인. 30분 비활동 시 자동 비활성화.

    platform=None      → 전체 확인 (Appium 종료 등)
    platform="android" → Android Capture 세션만 확인
    platform="ios"     → iOS Capture 세션만 확인
    """
    session = load_capture_session()
    if not session.get("active"):
        return False
    last_activity = session.get("last_activity_at", "")
    if last_activity:
        try:
            last_dt = datetime.fromisoformat(last_activity)
            elapsed = (datetime.now() - last_dt).total_seconds()
            if elapsed > 1800:  # 30분
                save_capture_session({**session, "active": False, "end_reason": "timeout"})
                return False
        except Exception:
            pass
    if platform is None:
        return True
    # platform 필드가 없으면 (구버전 세션) 전체 확인으로 fallback
    session_platform = session.get("platform", "").lower()
    if not session_platform:
        return True
    return session_platform == platform.lower()


def is_pipeline_active() -> bool:
    """파이프라인 실행 중인지 확인."""
    with _process_lock:
        return any(p.poll() is None for p in _running.values())


# ── 파일 목록 ─────────────────────────────────────────────────

def list_reports() -> list[dict]:
    if not REPORTS_DIR.exists():
        return []
    files = list(REPORTS_DIR.glob("report_*.html"))
    seen: set = set()
    result: list[dict] = []
    for f in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True):
        if f in seen:
            continue
        seen.add(f)
        try:
            rel = str(f.relative_to(REPORTS_DIR))
        except ValueError:
            rel = f.name
        result.append({
            "name": rel,
            "modified_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            "size": f.stat().st_size,
        })
    return result[:50]


def list_generated(platform: str | None = None) -> list[dict]:
    if not GENERATED_DIR.exists():
        return []
    result: list[dict] = []
    for platform_dir in sorted(GENERATED_DIR.iterdir()):
        if not platform_dir.is_dir() or platform_dir.name.startswith("."):
            continue
        if platform and platform_dir.name != platform:
            continue
        generated_paths = sorted(platform_dir.rglob("tc_*.py"))
        files = [str(f.relative_to(platform_dir)) for f in generated_paths]
        if files:
            stale_files = []
            for generated_path in generated_paths:
                try:
                    source = generated_path.read_text(encoding="utf-8")
                except OSError:
                    continue
                if "caps = devs['android'][PLATFORM_MODE].copy()" in source or \
                        "caps = devs['ios'][PLATFORM_MODE].copy()" in source:
                    stale_files.append(str(generated_path.relative_to(platform_dir)))
            item = {
                "platform": platform_dir.name,
                "files": files,
                "count": len(files),
            }
            # Keep the established response shape for current artifacts while
            # attaching actionable metadata only when an upgrade is needed.
            if stale_files:
                item["stale_files"] = stale_files
                item["stale_count"] = len(stale_files)
            result.append(item)
    return result


def list_screenshots() -> list[dict]:
    if not SCREENSHOTS_DIR.exists():
        return []
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    return sorted(
        [
            {
                "name": f.name,
                "path": str(f.relative_to(PROJECT_ROOT)),
                "size": f.stat().st_size,
                "modified_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            }
            for f in SCREENSHOTS_DIR.iterdir()
            if f.suffix.lower() in exts
        ],
        key=lambda x: x["modified_at"],
        reverse=True,
    )[:30]


def list_import_files() -> list[dict]:
    if not IMPORT_DIR.exists():
        return []
    return sorted(
        [
            {
                "name": file.name,
                "size": file.stat().st_size,
                "modified_at": datetime.fromtimestamp(file.stat().st_mtime).isoformat(),
            }
            for file in IMPORT_DIR.glob("*.xlsx")
            if file.is_file()
        ],
        key=lambda item: item["name"].lower(),
    )


def parse_failed_tcs(log_text: str) -> list[dict]:
    failures: list[dict] = []
    lines = log_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("FAILED "):
            tc = line.replace("FAILED ", "").split(" - ")[0].strip()
            error = line.split(" - ", 1)[1].strip() if " - " in line else ""
            failures.append({"tc": tc, "error": error})
        if "short test summary info" in line:
            for j in range(i + 1, min(i + 100, len(lines))):
                if lines[j].startswith("FAILED"):
                    tc = lines[j].replace("FAILED ", "").split(" - ")[0].strip()
                    error = lines[j].split(" - ", 1)[1].strip() if " - " in lines[j] else ""
                    entry = {"tc": tc, "error": error}
                    if entry not in failures:
                        failures.append(entry)
        i += 1
    seen: set = set()
    unique: list[dict] = []
    for f in failures:
        key = f["tc"]
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def list_tc_folders(platform: str | None = None) -> list[str]:
    if not TESTCASES_DIR.exists():
        return []
    if platform in ("android", "ios"):
        platform_dir = TESTCASES_DIR / platform
        return [platform] if platform_dir.is_dir() and any(platform_dir.rglob("tc_*.md")) else []
    return sorted([
        d.name for d in TESTCASES_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".") and list(d.glob("tc_*.md"))
    ])


# ── devices.json 읽기/쓰기 ────────────────────────────────────────

_DEVICES_PATH = PROJECT_ROOT / "config" / "devices.json"


def load_devices_json() -> dict:
    """config/devices.json 로드. 파일 없거나 손상 시 빈 dict 반환."""
    return load_json(_DEVICES_PATH) or {}


def save_devices_json(data: dict) -> None:
    """devices.json을 임시 파일 → 원자적 교체로 저장.

    스키마 검증: 각 플랫폼/모드 섹션에서 default:true가 2개 이상이면 ValueError.
    F5: flock(배타적 잠금) + fsync(디스크 동기화) → 동시 쓰기 충돌 방지.
    """
    for platform in ("android", "ios"):
        modes = (
            ["emulator", "real_device"]
            if platform == "android"
            else ["simulator", "real_device"]
        )
        for mode in modes:
            section = data.get(platform, {}).get(mode, [])
            if isinstance(section, list):
                defaults = [x for x in section if x.get("default")]
                if len(defaults) > 1:
                    raise ValueError(
                        f"{platform}.{mode}: default:true가 2개 이상 존재합니다"
                    )
    content = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = _DEVICES_PATH.with_suffix(".json.tmp")
    # flock으로 배타적 잠금 후 기록 → fsync → replace (원자적 교체)
    lock_path = _DEVICES_PATH.with_suffix(".json.lock")
    lock_path.touch(exist_ok=True)
    with open(lock_path, "r", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(_DEVICES_PATH)
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


# ── ENV Setup 세션 ─────────────────────────────────────────────────

ENV_SESSION_DEFAULT: dict = {
    "appium": {
        "status": "stopped",
        "pid": None,
        "port": 4723,
        "error_msg": None,
        "started_at": None,
    },
    "android": {"status": "stopped", "avd": None, "started_at": None},
    "ios": {"status": "stopped", "simulator": None, "started_at": None},
}

_ENV_SESSION_LOCK = threading.RLock()


def _write_env_session_unlocked(data: dict) -> None:
    ENV_SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = ENV_SESSION_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp_path.replace(ENV_SESSION_PATH)


def load_env_session() -> dict:
    """env_session.json 로드. 파일 없거나 손상 시 기본값 반환."""
    with _ENV_SESSION_LOCK:
        return load_json(ENV_SESSION_PATH) or copy.deepcopy(ENV_SESSION_DEFAULT)


def save_env_session(data: dict) -> None:
    """env_session.json을 프로세스 내 잠금과 원자적 교체로 저장한다."""
    with _ENV_SESSION_LOCK:
        _write_env_session_unlocked(data)


def update_env_session_sections(
    sections: dict[str, dict],
    expected: dict[str, dict] | None = None,
) -> dict:
    """지정 섹션만 원자적으로 갱신하며 선택적으로 오래된 쓰기를 거부한다."""
    with _ENV_SESSION_LOCK:
        current = load_json(ENV_SESSION_PATH) or copy.deepcopy(ENV_SESSION_DEFAULT)
        for key, value in sections.items():
            if expected is None or current.get(key) == expected.get(key):
                current[key] = value
        _write_env_session_unlocked(current)
        return current
