"""출처 버전 변경 추적 (PRD F5.9, 로드맵 C6).

scan(suite): 라이브러리 케이스의 conf·figma 출처마다 현재 원격 버전을 한 번씩 확인하고,
            바뀌었으면 해당 케이스에 flags.source_change = {ref, from, to, at}을 단다.
ack(suite, case_id): 새 버전을 확인했다고 표시 — 출처 버전을 새 값으로 바꾸고 표시를 지운다.
diff(ref): 번들에 남은 옛 본문과 현재 원격 본문의 차이 (줄 단위).
원격 호출은 사용자가 "출처 변경 확인"을 누를 때만 한다 (라이브러리를 열 때마다 부르지 않는다).
"""
from __future__ import annotations

import difflib

from _tc_connectors import current_version, ref_base, refetch_markdown
from _tc_fetch import FetchError
from _tc_library import get_case, load_cases, replace_source_version, set_flag
from _tc_model import now_iso
from _tc_sources import find_source, read_text

WATCHED = ("conf", "figma")


def _versioned(ref: str) -> str:
    return ref.split("#", 1)[0]                     # "conf:1@v14#§2" → "conf:1@v14"


def scan(suite: str) -> dict:
    groups: dict[str, set[str]] = {}
    for case in load_cases(suite):
        for ref in case["source_refs"]:
            if ref.split(":", 1)[0] in WATCHED and "@" in ref:
                groups.setdefault(_versioned(ref), set()).add(case["case_id"])
    changes, errors = [], []
    for versioned, case_ids in sorted(groups.items()):
        old = versioned.split("@", 1)[1]
        try:
            new = current_version(versioned)
        except FetchError as exc:
            errors.append({"ref": versioned, "error": str(exc), "code": exc.code})
            continue
        if new and new != old:
            to_ref = f"{ref_base(versioned)}@{new}"
            for case_id in sorted(case_ids):
                set_flag(suite, case_id, "source_change",
                         {"ref": versioned, "from": old, "to": new, "to_ref": to_ref, "at": now_iso()})
            changes.append({"ref": versioned, "from": old, "to": new, "case_ids": sorted(case_ids)})
    return {"checked": len(groups), "changes": changes, "errors": errors}


def flagged(suite: str) -> list[dict]:
    """원격 호출 없이 지금 표시된 변경 목록 (배너용)."""
    out: dict[str, dict] = {}
    for case in load_cases(suite):
        change = case.get("flags", {}).get("source_change")
        if change:
            item = out.setdefault(change["ref"], {**{k: change[k] for k in ("ref", "from", "to")}, "case_ids": []})
            item["case_ids"].append(case["case_id"])
    return list(out.values())


def ack(suite: str, case_id: str) -> dict:
    case = get_case(suite, case_id)
    change = case.get("flags", {}).get("source_change")
    if not change:
        return case
    replace_source_version(suite, case_id, change["ref"], change["to_ref"])
    return set_flag(suite, case_id, "source_change", None)


def diff(ref: str, *, context: int = 1) -> dict:
    """옛 번들 본문(ref 버전) ↔ 현재 원격 본문. {old_available, lines:[{op:' '|'-'|'+', text}]}"""
    versioned = _versioned(ref)
    found = find_source(versioned)
    new_lines = refetch_markdown(versioned).splitlines()
    if not found:
        return {"old_available": False, "lines": [{"op": "+", "text": t} for t in new_lines[:200]]}
    bundle_id, entry = found
    old_lines = read_text(bundle_id, entry["source_id"]).splitlines()
    lines = []
    for line in difflib.unified_diff(old_lines, new_lines, lineterm="", n=context):
        if line.startswith(("---", "+++")):
            continue
        if line.startswith("@@"):
            lines.append({"op": "@", "text": "…"})
        else:
            lines.append({"op": line[0], "text": line[1:]})
    return {"old_available": True, "lines": lines[:400]}
