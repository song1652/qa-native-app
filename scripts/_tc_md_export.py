"""승인 TC를 앱 파이프라인용 Markdown으로 미리보고 반영한다."""
from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
from pathlib import Path

import _paths
from _state import read_state, update_state
from _tc_library import LibraryError, load_cases, suite_dir, with_issues, _locked, _writes
from _tc_model import format_steps, join_expected
from import_excel import _render_markdown, _slug

_GROUP = re.compile(r"[A-Za-z0-9_-]+\Z")
_CODE = re.compile(r"[A-Z][A-Z0-9]{1,7}\Z")


def _config_path(suite: str) -> Path:
    return suite_dir(suite) / "md_export.json"


def _run_path(suite: str, run_id: str) -> Path:
    if not re.fullmatch(r"run_[0-9a-f]{12}", run_id):
        raise LibraryError("내보내기 ID가 올바르지 않습니다", "INVALID_RUN")
    return suite_dir(suite) / "md_runs" / f"{run_id}.json"


@_locked
def load_config(suite: str) -> dict:
    raw = read_state(_config_path(suite))
    return {"groups": raw.get("groups", []), "ids": raw.get("ids", {}), "exported": raw.get("exported", {})}


@_writes
def save_group(suite: str, path: list[str], group: str, code: str) -> dict:
    path = [str(p).strip() for p in path if str(p).strip()]
    if len(path) < 2 or not _GROUP.fullmatch(group or "") or not _CODE.fullmatch(code or ""):
        raise LibraryError("그룹·경로·접두어를 확인하세요", "INVALID_MD_GROUP")
    def mutate(cfg):
        groups = [g for g in cfg.get("groups", []) if g["path"] != path]
        return {**cfg, "groups": groups + [{"path": path, "group": group, "code": code}]}
    update_state(_config_path(suite), mutate)
    return load_config(suite)


def _keys(case: dict) -> list[str]:
    return [case["sheet"], *[p for p in case["path"] if p]]


def group_for(case: dict, groups: list[dict]) -> dict | None:
    hits = [g for g in groups if _keys(case)[:len(g["path"])] == g["path"]]
    return max(hits, key=lambda g: len(g["path"])) if hits else None


def _eligible(case: dict) -> bool:
    return case["status"] == "approved" and not case["has_error"] and all(
        bullet["verified"] for bullet in case.get("bullets", []))


@_locked
def eligibility(suite: str) -> dict:
    cases = [with_issues(c) for c in load_cases(suite)]
    cfg = load_config(suite)
    clean = [c for c in cases if _eligible(c)]
    mapped = [c for c in clean if group_for(c, cfg["groups"])]
    branches = {}
    for c in clean:
        key = tuple(_keys(c)[:2])
        mapping = group_for(c, cfg["groups"])
        entry = branches.setdefault(key, {"path": list(key), "group": mapping["group"] if mapping else "",
                                          "code": mapping["code"] if mapping else "", "count": 0})
        entry["count"] += 1
    excluded = [{"case_id": c["case_id"], "feature": c["feature"],
                 "reason": "미승인" if c["status"] != "approved" else
                           "검증 오류" if c["has_error"] else
                           "추정 문구" if not all(b["verified"] for b in c.get("bullets", [])) else "그룹 매핑 없음"}
                for c in cases if c not in mapped]
    return {"funnel": [{"label": "라이브러리 전체", "count": len(cases)},
                       {"label": "승인됨", "count": sum(c["status"] == "approved" for c in cases)},
                       {"label": "추정 문구·검증 오류 없음", "count": len(clean)},
                       {"label": "그룹 매핑됨", "count": len(mapped)}],
            "groups": cfg["groups"], "branches": list(branches.values()), "pages": [], "excluded": excluded, "drifted": []}


def _allocate_ids(suite: str, cases: list[dict], groups: list[dict]) -> dict[str, str]:
    def mutate(cfg):
        ids = dict(cfg.get("ids", {}))
        used = set(ids.values())
        for case in cases:
            if case["case_id"] in ids:
                continue
            original = str(case.get("source_tc_id") or "").strip()
            if original and re.fullmatch(r"[\w-]+", original) and original not in used:
                tc_id = original
            else:
                code = group_for(case, groups)["code"]
                number = 1
                while f"{code}_{number:02d}" in used:
                    number += 1
                tc_id = f"{code}_{number:02d}"
            ids[case["case_id"]] = tc_id
            used.add(tc_id)
        return {**cfg, "ids": ids}
    return update_state(_config_path(suite), mutate)["ids"]


def _target(row: dict) -> Path:
    root = _paths.TESTCASES_DIR.resolve()
    target = (root / row["platform"] / row["group"] / row["filename"]).resolve()
    if not target.is_relative_to(root):
        raise LibraryError("내보내기 경로가 올바르지 않습니다", "INVALID_TARGET")
    return target


def _digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _replace(target: Path, data: bytes | None) -> None:
    if data is None:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tc-" + secrets.token_hex(4))
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


@_writes
def preview(suite: str) -> dict:
    cfg = load_config(suite)
    cases = [c for c in map(with_issues, load_cases(suite)) if _eligible(c) and group_for(c, cfg["groups"])]
    if not cases:
        raise LibraryError("내보낼 케이스가 없습니다", "NOTHING_TO_EXPORT")
    ids = _allocate_ids(suite, cases, cfg["groups"])
    rows = []
    for case in cases:
        mapping = group_for(case, cfg["groups"])
        tc_id = ids[case["case_id"]]
        for platform in case.get("platforms") or ["android", "ios"]:
            row = {"tc_id": tc_id, "case_id": case["case_id"], "platform": platform,
                   "group": mapping["group"], "filename": f"tc_{tc_id}_{_slug(case['feature'])}.md"}
            row["content"] = _render_markdown(platform, tc_id, case["feature"],
                case.get("precondition", ""), format_steps(case["steps"]),
                join_expected(case["expected"], case.get("bullets", [])),
                "high" if case.get("priority") in ("P0", "P1") else "medium")
            target = _target(row)
            row["before_hash"] = _digest(target.read_bytes() if target.exists() else None)
            row["status"] = "added" if not target.exists() else (
                "same" if target.read_text(encoding="utf-8") == row["content"] else "conflict")
            row["file"] = f"{platform}/{mapping['group']}/{row['filename']}"
            row["excluded"] = False
            rows.append(row)
    run_id = "run_" + secrets.token_hex(6)
    run = {"run_id": run_id, "suite": suite, "tc_library_suite": suite,
           "status": "preview_ready", "rows": rows,
           "summary": {s: sum(r["status"] == s for r in rows) for s in ("added", "same", "conflict")}}
    update_state(_run_path(suite, run_id), lambda _: run)
    return run


@_writes
def commit(suite: str, run_id: str, skip_tc_ids: list[str], overwrite: bool = False) -> dict:
    path = _run_path(suite, run_id)
    run = read_state(path)
    if run.get("suite") != suite or run.get("status") != "preview_ready":
        raise LibraryError("반영할 수 없는 작업입니다", "INVALID_RUN", 409)
    choices = []
    for row in run["rows"]:
        target = _target(row)
        if row["file"] in skip_tc_ids or (target.exists() and not overwrite):
            continue
        current = target.read_bytes() if target.exists() else None
        if _digest(current) != row["before_hash"]:
            raise LibraryError("미리보기 이후 대상 파일이 변경되었습니다. 다시 미리보세요", "TARGET_CHANGED", 409)
        choices.append((row, target, current))
    snapshots, written, skipped = {}, [], []
    created = updated = 0
    try:
        for row, target, before in choices:
            snapshots[row["file"]] = None if before is None else base64.b64encode(before).decode()
            _replace(target, row["content"].encode("utf-8"))
            written.append(row["file"])
            created += before is None
            updated += before is not None
        skipped = [row["file"] for row in run["rows"] if row["file"] not in written]
        update_state(path, lambda old: {**old, "status": "committed", "snapshots": snapshots,
                                        "written": written, "skipped": skipped})
    except Exception:
        for row, target, before in reversed(choices):
            if row["file"] in written:
                _replace(target, before)
        raise
    return {"run_id": run_id, "status": "committed", "written": written, "skipped": skipped,
            "created": created, "updated": updated}


@_locked
def rollback(suite: str, run_id: str) -> dict:
    path = _run_path(suite, run_id)
    run = read_state(path)
    if run.get("suite") != suite or run.get("status") != "committed":
        raise LibraryError("되돌릴 수 없는 작업입니다", "INVALID_RUN", 409)
    for row in run["rows"]:
        if row["file"] in run["snapshots"]:
            target = _target(row)
            current = target.read_bytes() if target.exists() else None
            if current != row["content"].encode("utf-8"):
                raise LibraryError("반영 후 대상 파일이 변경되어 되돌릴 수 없습니다", "TARGET_CHANGED", 409)
    for row in run["rows"]:
        if row["file"] not in run["snapshots"]:
            continue
        target = _target(row)
        before = run["snapshots"][row["file"]]
        _replace(target, base64.b64decode(before) if before is not None else None)
    update_state(path, lambda old: {**old, "status": "rolled_back"})
    return {"run_id": run_id, "status": "rolled_back"}
