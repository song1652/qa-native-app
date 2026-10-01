"""스위트 삭제·휴지통 — 지운 스위트를 30일 동안 보관하고 되돌린다.

state/tc_library/_trash/{trash_id}/
  meta.json        {"trash_id", "suite", "deleted_at", "cases", "sheets", "jobs": [...], "runs": [...]}
  suite/           스위트 폴더 그대로 (cases·양식·이력·md 내보내기 설정)
  jobs/{job_id}/   이 스위트의 생성 작업 (같은 이름으로 새로 만든 스위트에 옛 작업이 붙지 않게 함께 옮긴다)
  import_runs/     이 스위트의 가져오기 기록 (삭제된 스위트를 되살리는 커밋·롤백을 막는다)

소스 묶음(_sources)은 작업끼리 공유하므로 옮기지 않는다. testcases/의 md 파일도 건드리지 않는다.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import _paths
from _state import read_state, update_state
from _tc_generate import ACTIVE, jobs_root
from _tc_import_ops import _root as import_runs_root
from _tc_library import DEFAULT_SUITE, LibraryError, load_cases, suite_dir, suite_lock
from _tc_model import now_iso

RETENTION_DAYS = 30


def trash_root() -> Path:
    return _paths.TC_LIBRARY_DIR / "_trash"


def _trash_dir(trash_id: str) -> Path:
    if not re.fullmatch(r"trash_[0-9a-f]{12}", trash_id or ""):
        raise LibraryError("휴지통 항목 id가 올바르지 않습니다", "INVALID_TRASH")
    return trash_root() / trash_id


def _suite_jobs(suite: str) -> list[Path]:
    root = jobs_root()
    if not root.exists():
        return []
    return [d for d in sorted(root.iterdir()) if (d / "status.json").exists()
            and read_state(d / "status.json").get("suite") == suite]


def _suite_runs(suite: str) -> list[Path]:
    root = import_runs_root()
    if not root.exists():
        return []
    runs = []
    for path in sorted(root.glob("libimp_*.json")):
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("suite") == suite:
                runs.append(path)
        except (ValueError, OSError):
            continue
    return runs


def delete_suite(suite: str, confirm: str) -> dict:
    """스위트를 휴지통으로 옮긴다. confirm은 화면이 보낸 스위트 이름 (엉뚱한 스위트 삭제 방지)."""
    if suite == DEFAULT_SUITE:
        raise LibraryError(f"'{DEFAULT_SUITE}'는 기본 양식이라 삭제할 수 없습니다", "DEFAULT_SUITE", 409)
    if confirm != suite:
        raise LibraryError("삭제할 스위트 이름이 일치하지 않습니다", "CONFIRM_MISMATCH")
    source = suite_dir(suite)
    with suite_lock(suite):          # 락을 얻을 때 중단된 가져오기를 먼저 마무리한다
        if not source.is_dir():
            raise LibraryError(f"스위트가 없습니다: {suite}", "SUITE_NOT_FOUND", 404)
        jobs = _suite_jobs(suite)
        running = [d.name for d in jobs if read_state(d / "status.json").get("status") in ACTIVE]
        if running:
            raise LibraryError("초안 생성이 진행 중인 스위트는 삭제할 수 없습니다. 작업을 취소한 뒤 다시 시도하세요",
                               "JOB_RUNNING", 409)
        cases = load_cases(suite)
        runs = _suite_runs(suite)
        trash_id = "trash_" + secrets.token_hex(6)
        target = _trash_dir(trash_id)
        target.mkdir(parents=True)
        meta = {"trash_id": trash_id, "suite": suite, "deleted_at": now_iso(), "cases": len(cases),
                "sheets": len({c["sheet"] for c in cases}), "jobs": [d.name for d in jobs],
                "runs": [p.name for p in runs]}
        update_state(target / "meta.json", lambda _: meta)
        os.replace(source, target / "suite")          # 한 번에 옮겨 목록에서 바로 사라지게 한다
        if jobs:
            (target / "jobs").mkdir()
            for d in jobs:
                os.replace(d, target / "jobs" / d.name)
        if runs:
            (target / "import_runs").mkdir()
            for p in runs:
                os.replace(p, target / "import_runs" / p.name)
    return meta


def list_trash() -> list[dict]:
    """보관 기간이 지난 항목은 이때 영구 삭제한다."""
    root = trash_root()
    if not root.exists():
        return []
    items = []
    expire = datetime.now() - timedelta(days=RETENTION_DAYS)
    for d in sorted(root.iterdir()):
        meta = read_state(d / "meta.json")
        if not meta.get("trash_id"):
            continue
        deleted = datetime.fromisoformat(meta["deleted_at"])
        if deleted < expire:
            shutil.rmtree(d, ignore_errors=True)
            continue
        items.append({**meta, "expires_at": (deleted + timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")})
    return sorted(items, key=lambda m: m["deleted_at"], reverse=True)


def restore_suite(trash_id: str) -> dict:
    source = _trash_dir(trash_id)
    meta = read_state(source / "meta.json")
    if not meta.get("trash_id"):
        raise LibraryError("휴지통에 없는 항목입니다", "TRASH_NOT_FOUND", 404)
    suite = meta["suite"]
    with suite_lock(suite):
        if not (source / "meta.json").exists():   # 락을 기다리는 사이 영구 삭제됐는지 다시 확인
            raise LibraryError("휴지통에 없는 항목입니다", "TRASH_NOT_FOUND", 404)
        if suite_dir(suite).exists():
            raise LibraryError(f"같은 이름의 스위트 '{suite}'가 이미 있습니다. 그 스위트를 삭제한 뒤 복원하세요",
                               "SUITE_EXISTS", 409)
        os.replace(source / "suite", suite_dir(suite))
        for d in sorted((source / "jobs").iterdir()) if (source / "jobs").exists() else []:
            jobs_root().mkdir(parents=True, exist_ok=True)
            os.replace(d, jobs_root() / d.name)
        for p in sorted((source / "import_runs").iterdir()) if (source / "import_runs").exists() else []:
            import_runs_root().mkdir(parents=True, exist_ok=True)
            os.replace(p, import_runs_root() / p.name)
        shutil.rmtree(source)
    return meta


def purge(trash_id: str, confirm: str) -> dict:
    """휴지통 항목 하나를 영구 삭제한다. confirm은 화면이 보낸 스위트 이름 (엉뚱한 항목 삭제 방지)."""
    target = _trash_dir(trash_id)
    meta = read_state(target / "meta.json")
    if not meta.get("trash_id"):
        raise LibraryError("휴지통에 없는 항목입니다", "TRASH_NOT_FOUND", 404)
    if confirm != meta["suite"]:
        raise LibraryError("삭제할 스위트 이름이 일치하지 않습니다", "CONFIRM_MISMATCH")
    with suite_lock(meta["suite"]):          # restore_suite와 같은 락 — 복원과 동시에 돌지 않게 한다
        if not (target / "meta.json").exists():   # 락을 기다리는 사이 복원·삭제됐는지 다시 확인
            raise LibraryError("휴지통에 없는 항목입니다", "TRASH_NOT_FOUND", 404)
        shutil.rmtree(target)
    return meta
