"""TC 라이브러리 케이스 모델 — 엑셀·md 어느 쪽에도 묶이지 않는 형식 (PRD §5)."""
from __future__ import annotations

import re
from datetime import datetime

PRIORITIES = ("P0", "P1", "P2", "P3")
# "" = 미실행. 엑셀의 빈 결과 칸과 1:1로 대응해야 왕복 시 NT로 바뀌지 않는다 (로드맵 Z1).
EXECUTION_RESULTS = ("", "pass", "fail", "not_test", "na")
STATUSES = ("draft", "approved", "rejected", "needs_review")
EXCEL_TO_RESULT = {"pass": "pass", "fail": "fail", "nt": "not_test", "na": "na"}
RESULT_TO_EXCEL = {"pass": "Pass", "fail": "Fail", "not_test": "NT", "na": "NA"}
# 여러 플랫폼 결과를 하나로 합칠 때 앞쪽이 이긴다.
RESULT_PRECEDENCE = ("fail", "na", "pass", "not_test")
EDITABLE_FIELDS = (
    "sheet", "path", "feature", "precondition", "steps", "expected", "bullets",
    "priority", "execution_result", "platforms", "results", "status", "note", "source_tc_id", "tags",
)
_VAGUE = (re.compile(r"정상\s*동작"), re.compile(r"정상적으로\s*노출"))
_STEP_NO = re.compile(r"^\s*\d+\s*[.)]\s*")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_case(**fields) -> dict:
    case = {
        "case_id": "", "sheet": "", "path": ["", "", ""], "feature": "",
        "precondition": "", "steps": [], "expected": "", "bullets": [],
        "priority": "", "execution_result": "", "platforms": ["android", "ios"],
        "results": {}, "status": "draft",
        "note": "", "source_tc_id": "", "tags": [], "source_refs": [], "rev": 1, "deleted": False,
        "updated_at": now_iso(),
        # 생성 초안 정보 (Phase 2): job_id, source_quote, duplicates[{case_id, similarity}]
        "draft_meta": {},
        # 검토 표시 (Phase 3): source_change {ref, from, to, at} — 상태(status)와 따로 둔다 (명세 피드백 #7)
        "flags": {},
    }
    fields.pop("auto", None)
    case.update(fields)
    case["path"] = (list(case["path"]) + ["", "", ""])[:3]
    if case["results"]:
        case["execution_result"] = merge_results(list(case["results"].values()))
    return case


def platform_key(label: str) -> str | None:
    key = str(label or "").strip().casefold()
    if key in {"and", "android", "aos", "안드로이드"}:
        return "android"
    if key in {"ios", "아이폰"}:
        return "ios"
    return None


def parse_steps(text: str) -> list[str]:
    """'1. a\\n2. b' → ['a', 'b']. 번호 없는 줄은 앞 Step에 이어 붙인다."""
    steps: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if _STEP_NO.match(line) or not steps:
            steps.append(_STEP_NO.sub("", line))
        else:
            steps[-1] = f"{steps[-1]}\n{line}"
    return steps


def format_steps(steps: list[str]) -> str:
    return "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))


def split_expected(text: str) -> tuple[str, list[dict]]:
    """Expected 셀 → (결과 문장, UI 문구 불릿). 엑셀에서 온 문구는 확인된 문구로 본다."""
    head: list[str] = []
    bullets: list[dict] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("-"):
            bullets.append({"text": line[1:].strip(), "verified": True})
        elif bullets:
            bullets[-1]["text"] += f"\n{line}"
        else:
            head.append(line)
    return "\n".join(head), bullets


def join_expected(expected: str, bullets: list[dict]) -> str:
    lines = [expected] if expected else []
    lines += [f"- {b['text']}" for b in bullets]
    return "\n".join(lines)


def merge_results(values: list[str]) -> str:
    present = {v for v in values if v}
    for candidate in RESULT_PRECEDENCE:
        if candidate in present:
            return candidate
    return ""


def next_case_id(prefix: str, existing: set[str]) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    top = max((int(m.group(1)) for i in existing if (m := pattern.match(i))), default=0)
    return f"{prefix}_{top + 1:04d}"


def validate_case(case: dict) -> list[dict]:
    """PRD F5.8 검증. level은 error(내보내기 차단) 또는 warning."""
    issues: list[dict] = []

    def add(level: str, code: str, message: str) -> None:
        issues.append({"level": level, "code": code, "message": message})

    for field, label in (("feature", "기능"), ("expected", "Expected")):
        if not str(case.get(field, "")).strip():
            add("error", "MISSING_FIELD", f"{label}이(가) 비어 있습니다")
    steps = case.get("steps") or []
    if not steps:
        add("error", "MISSING_FIELD", "Test Step이 비어 있습니다")
    elif any(not str(s).strip() for s in steps):
        add("error", "STEP_EMPTY", "빈 Step이 있습니다")
    if not case.get("path", [""])[0]:
        add("error", "PATH_EMPTY", "대분류가 비어 있습니다")
    priority = case.get("priority", "")
    if not priority:
        add("warning", "PRIORITY_EMPTY", "우선순위가 지정되지 않았습니다")
    elif priority not in PRIORITIES:
        add("error", "PRIORITY_INVALID", f"우선순위 {priority!r}는 허용 값이 아닙니다 (P0~P3)")
    if case.get("execution_result", "") not in EXECUTION_RESULTS:
        add("error", "RESULT_INVALID", "실행 결과 값이 올바르지 않습니다")
    text = join_expected(case.get("expected", ""), case.get("bullets", []))
    if any(p.search(text) for p in _VAGUE):
        add("error", "VAGUE_EXPECTED", "모호한 표현이 있습니다 (정상 동작 / 정상적으로 노출)")
    return issues
