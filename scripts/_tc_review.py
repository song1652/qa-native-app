"""초안 검토 도우미 — 중복 후보·중복 처리·커버리지 갭 (PRD F5.6, F5.10)."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from _tc_library import (
    LibraryError, RevConflict, add_source_refs, delete_cases, get_case, load_cases, patch_case,
    set_draft_meta, set_review_source,
)

DUPLICATE_THRESHOLD = 0.7
_NEGATIVE = ("실패", "오류", "에러", "불가", "없는", "없을", "잘못", "만료", "초과", "미노출", "제한", "안 돼", "않")
_VALIDATION = ("유효", "형식", "필수", "입력해", "자리", "글자")


def _norm(text: str) -> str:
    return re.sub(r"[\s\W_]+", " ", text).strip().lower()


def case_text(case: dict) -> str:
    return _norm(" ".join([case["feature"], *case["steps"], case["expected"],
                           *[b["text"] for b in case.get("bullets", [])]]))


def similarity(a: dict, b: dict) -> float:
    return round(SequenceMatcher(None, case_text(a), case_text(b)).ratio(), 2)


def find_duplicates(draft: dict, existing: list[dict], threshold: float = DUPLICATE_THRESHOLD) -> list[dict]:
    """같은 시트·같은 대분류 안의 승인 케이스 중 비슷한 것 (유사도 높은 순, 최대 3개)."""
    hits = []
    for case in existing:
        if case["case_id"] == draft.get("case_id") or case["status"] != "approved":
            continue
        if case["sheet"] != draft["sheet"] or case["path"][0] != draft["path"][0]:
            continue
        score = similarity(draft, case)
        if score >= threshold:
            hits.append({"case_id": case["case_id"], "similarity": score})
    return sorted(hits, key=lambda h: -h["similarity"])[:3]


def resolve_duplicate(suite: str, draft_id: str, draft_rev: int, action: str, actor: str,
                      target_id: str = "", target_rev: int = 0) -> dict:
    """action: update(기존 케이스를 초안 내용으로 갱신, 초안은 삭제) · skip(초안 반려) · add(중복 아님 표시).

    update 규칙 (명세 피드백 #9): 기존 케이스의 case_id·이력은 유지하고 내용만 바꾼다.
    초안의 출처는 기존 출처에 덧붙이고, 기존 케이스 상태는 approved로 둔다.
    """
    draft = get_case(suite, draft_id)
    if draft["rev"] != draft_rev:
        raise RevConflict(draft)
    if action == "skip":
        return {"draft": patch_case(suite, draft_id, draft_rev, {"status": "rejected"}, actor)}
    if action == "add":
        return {"draft": set_draft_meta(suite, draft_id, {"duplicates": [], "duplicate_checked": True})}
    if action != "update":
        raise LibraryError(f"지원하지 않는 처리입니다: {action}", "INVALID_ACTION")
    target = get_case(suite, target_id)
    fields = ("feature", "precondition", "steps", "expected", "bullets", "priority")
    changes = {f: draft[f] for f in fields if draft[f] != target[f] and (draft[f] or f == "precondition")}
    patch_case(suite, target_id, target_rev, {**changes, "status": "approved"}, actor)
    set_review_source(suite, target_id, "human")     # 초안 검토에서 사람이 합쳐 승인했다
    updated = add_source_refs(suite, target_id, draft["source_refs"])
    delete_cases(suite, [{"case_id": draft_id, "rev": draft_rev}], actor)
    return {"target": updated, "deleted_draft": draft_id}


def classify(case: dict) -> str:
    """커버리지 분류(휴리스틱): negative · validation · positive."""
    text = " ".join([case["precondition"], case["expected"], *[b["text"] for b in case["bullets"]]])
    if any(k in text for k in _VALIDATION) and any("입력" in s for s in case["steps"]):
        return "validation"
    if any(k in text for k in _NEGATIVE):
        return "negative"
    return "positive"


def coverage_gaps(suite: str, sheet: str, path: list[str], profile: dict) -> list[dict]:
    """대상 가지의 기능별 정상·예외·유효성 개수와 부족분 (반려·삭제 제외)."""
    prefix = [p for p in path if p]
    groups: dict[str, dict] = {}
    for case in load_cases(suite):
        if case["sheet"] != sheet or case["status"] == "rejected":
            continue
        if [p for p in case["path"] if p][: len(prefix)] != prefix:
            continue
        g = groups.setdefault(case["feature"], {"feature": case["feature"], "positive": 0,
                                                "negative": 0, "validation": 0, "has_input": False})
        g[classify(case)] += 1
        g["has_input"] |= any("입력" in s for s in case["steps"])
    need = profile["coverage"]
    out = []
    for g in groups.values():
        missing = []
        if g["positive"] < need["positive"]:
            missing.append("정상")
        if g["negative"] < need["negative"]:
            missing.append("예외")
        if g["has_input"] and g["validation"] < need["validation_if_input"]:
            missing.append("유효성")
        out.append({**g, "missing": missing})
    return sorted(out, key=lambda g: (-len(g["missing"]), g["feature"]))
