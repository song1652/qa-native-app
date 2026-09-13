"""
utils/state.py — 파이프라인/캡처 세션 상태 읽기쓰기, 파일 목록 조회.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import (  # noqa: E402
    STATE_PATH,
    CAPTURE_SESSION_PATH,
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


def is_capture_active() -> bool:
    """Capture Studio 세션이 활성 상태인지 확인. 30분 비활동 시 자동 비활성화."""
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
    return True


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
        files = sorted([
            str(f.relative_to(platform_dir))
            for f in platform_dir.rglob("tc_*.py")
        ])
        if files:
            result.append({
                "platform": platform_dir.name,
                "files": files,
                "count": len(files),
            })
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
