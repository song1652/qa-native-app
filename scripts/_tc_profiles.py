"""작성 프로필 — 생성 규칙 묶음 (PRD F3). state/tc_library/_profiles.json"""
from __future__ import annotations

import _paths
from _state import read_state, update_state
from _tc_library import LibraryError
from _tc_model import now_iso

DEFAULT_PROFILE = {
    "name": "기본",
    "coverage": {"positive": 0, "negative": 0, "validation_if_input": 0},
    "rules": [
        "제공한 정보에 명시된 기능·조건·기대 결과를 기준으로 작성한다. 문서에 없는 동작은 추측하지 않는다",
        "TC 하나에는 하나의 검증 목적을 담고, 중복 케이스는 합친다",
        "조건에 따라 결과가 달라진다고 명시된 경우에만 케이스를 나눈다",
        "Step은 한 줄에 한 동작, Expected는 확인 가능한 결과와 원문 화면 문구로 작성한다",
    ],
    "banned_phrases": ["정상 동작", "정상적으로 노출"],
    "examples": 8,
    "expected_endings": [],   # Expected 마지막 줄이 이 중 하나로 끝나야 한다. 비면 검사하지 않는다
    "style_examples": [],     # 같은 가지에 승인된 케이스가 모자랄 때 채우는 기준 예시 (케이스 필드 모양)
}
_FIELDS = ("coverage", "rules", "banned_phrases", "examples", "expected_endings", "style_examples")
_EXAMPLE_FIELDS = ("path", "feature", "precondition", "steps", "expected", "bullets", "priority")
MAX_STYLE_EXAMPLES = 10


def _path():
    return _paths.TC_LIBRARY_DIR / "_profiles.json"


def list_profiles() -> list[dict]:
    # 새 필드가 생기기 전에 저장한 프로필도 같은 모양으로 돌려준다
    saved = [{**{k: DEFAULT_PROFILE[k] for k in _FIELDS}, **p} for p in read_state(_path()).get("profiles", [])]
    names = {p["name"] for p in saved}
    return ([dict(DEFAULT_PROFILE)] if DEFAULT_PROFILE["name"] not in names else []) + saved


def get_profile(name: str) -> dict:
    for profile in list_profiles():
        if profile["name"] == name:
            return profile
    raise LibraryError(f"작성 프로필이 없습니다: {name}", "PROFILE_NOT_FOUND", 404)


def save_profile(name: str, fields: dict) -> dict:
    name = (name or "").strip()
    if not name or len(name) > 40:
        raise LibraryError("프로필 이름은 1~40자여야 합니다", "INVALID_PROFILE")
    rules = fields.get("rules", DEFAULT_PROFILE["rules"])
    if not isinstance(rules, list) or not all(isinstance(r, str) and r.strip() for r in rules):
        raise LibraryError("규칙은 비어 있지 않은 문자열 목록이어야 합니다", "INVALID_PROFILE")
    endings = fields.get("expected_endings", [])
    if not isinstance(endings, list) or not all(isinstance(e, str) and e.strip() for e in endings):
        raise LibraryError("Expected 끝맺음은 비어 있지 않은 문자열 목록이어야 합니다", "INVALID_PROFILE")
    fields = {**fields, "expected_endings": [e.strip() for e in endings],
              "style_examples": _clean_examples(fields.get("style_examples", []))}
    profile = {"name": name, **{k: fields.get(k, DEFAULT_PROFILE[k]) for k in _FIELDS},
               "updated_at": now_iso()}

    def mutate(data: dict) -> dict:
        profiles = [p for p in data.get("profiles", []) if p["name"] != name]
        return {"profiles": profiles + [profile]}

    update_state(_path(), mutate)
    return profile


def _clean_examples(examples) -> list[dict]:
    if not isinstance(examples, list) or len(examples) > MAX_STYLE_EXAMPLES:
        raise LibraryError(f"기준 예시는 {MAX_STYLE_EXAMPLES}건 이하 목록이어야 합니다", "INVALID_PROFILE")
    cleaned = []
    for ex in examples:
        if not (isinstance(ex, dict) and str(ex.get("feature", "")).strip() and str(ex.get("expected", "")).strip()
                and isinstance(ex.get("steps"), list) and ex["steps"]):
            raise LibraryError("기준 예시에는 제목·Step·Expected가 있어야 합니다", "INVALID_PROFILE")
        cleaned.append({"path": list(ex.get("path") or []), "feature": ex["feature"],
                        "precondition": ex.get("precondition", ""), "steps": [str(x) for x in ex["steps"]],
                        "expected": ex["expected"], "bullets": list(ex.get("bullets") or []),
                        "priority": ex.get("priority", "")})
    return cleaned


def style_issues(case: dict, profile: dict) -> list[dict]:
    """프로필 문체 검사 — 금지 표현과 Expected 끝맺음. 경고(warning)라 내보내기를 막지는 않는다.
    화면 문구(bullets)는 원문을 옮긴 것이라 금지 표현 검사에서 뺀다."""
    issues = []
    text = "\n".join([case.get("feature", ""), case.get("precondition", ""), *case.get("steps", []),
                      case.get("expected", "")])
    for phrase in profile.get("banned_phrases", []):
        if phrase and phrase in text:
            issues.append({"level": "warning", "code": "STYLE_BANNED",
                           "message": f'금지 표현 "{phrase}"이(가) 있습니다'})
    endings = profile.get("expected_endings", [])
    lines = [line.strip() for line in case.get("expected", "").splitlines() if line.strip()]
    if endings and lines and not lines[-1].endswith(tuple(endings)):
        issues.append({"level": "warning", "code": "STYLE_ENDING",
                       "message": f"Expected 끝맺음이 작성 규칙과 다릅니다 ({' / '.join(endings)})"})
    return issues


def style_issues_for(case: dict) -> list[dict]:
    """초안이면 생성할 때 쓴 프로필로 검사한다. 프로필이 지워졌으면 검사하지 않는다."""
    name = (case.get("draft_meta") or {}).get("profile")
    if case.get("status") != "draft" or not name:
        return []
    try:
        return style_issues(case, get_profile(name))
    except LibraryError:
        return []


def _ending(line: str) -> str:
    line = line.strip()
    return line[-3:] if len(line) >= 3 else line


def style_from_cases(cases: list[dict], *, max_examples: int = 5) -> dict:
    """기존 TC(예: 엑셀에서 읽은 케이스)의 문체 → 프로필 초안 {rules, expected_endings, style_examples, stats}.
    ponytail: 끝 3글자 빈도·명사형 비율 같은 단순 휴리스틱. 결과는 사람이 규칙 편집에서 고쳐 저장한다."""
    from collections import Counter
    cases = [c for c in cases if c.get("feature") and c.get("steps") and c.get("expected")]
    if not cases:
        raise LibraryError("문체를 읽을 TC가 없습니다", "NO_CASES")
    lasts = [[l for l in c["expected"].splitlines() if l.strip()][-1] for c in cases]
    counts = Counter(_ending(l) for l in lasts)
    endings, covered = [], 0
    for ending, n in counts.most_common(6):          # 90%를 덮을 때까지 흔한 끝맺음만 고른다
        if covered >= 0.9 * len(lasts):
            break
        endings.append(ending)
        covered += n
    steps = [s.strip() for c in cases for s in c["steps"] if s.strip()]
    noun_steps = sum(1 for s in steps if not s.rstrip(".").endswith("다")) / len(steps)
    step_words = [w for w, _ in Counter(s.split()[-1] for s in steps).most_common(3)]
    pre = [c["precondition"].strip() for c in cases if c["precondition"].strip()]
    pre_lines = [l.strip() for p in pre for l in p.splitlines() if l.strip()]
    title_words = [w for w, _ in Counter(c["feature"].split()[-1] for c in cases).most_common(4)]
    rules = [f"제목은 짧은 명사구로 쓰고 주로 {', '.join(repr(w) for w in title_words)} 같은 화면 요소 이름으로 끝낸다"]
    if noun_steps >= 0.6:
        rules.append(f"Step은 한 동작씩 명사형으로 끝낸다 (예: {', '.join(repr('… ' + w) for w in step_words)}). "
                     "하위 동작은 ' > '로 잇는다")
    else:
        rules.append("Step은 한 동작씩 '~한다' 서술형으로 쓴다")
    if pre_lines and sum(l.startswith("-") for l in pre_lines) / len(pre_lines) >= 0.6:
        tail = Counter(l.split()[-1] for l in pre_lines).most_common(1)[0][0]
        rules.append(f"사전 조건은 줄마다 '- '로 시작하는 목록으로 쓰고 '~ {tail}'처럼 끝낸다")
    rules.append(f"Expected는 결과를 한 문장으로 쓰고 {', '.join(repr(e) for e in endings)}로 끝낸다. "
                 "결과가 여럿이면 '~하며, ~'로 한 문장에 잇는다")

    # 기준 예시: 사전 조건·여러 Step·화면 문구가 있는 케이스를 시트별로 골고루
    def score(c):
        return (bool(c["precondition"].strip()) + (len(c["steps"]) >= 2) + bool(c.get("bullets"))
                + bool(c.get("priority")))
    by_sheet: dict[str, list[dict]] = {}
    for c in sorted(cases, key=score, reverse=True):
        if _ending(lasts[cases.index(c)]) in endings:
            by_sheet.setdefault(c.get("sheet", ""), []).append(c)
    picked = []
    while len(picked) < max_examples and any(by_sheet.values()):
        for sheet in list(by_sheet):
            if by_sheet[sheet] and len(picked) < max_examples:
                picked.append(by_sheet[sheet].pop(0))
    # 분류 경로는 다른 스위트 것이라 빼고 말투만 넘긴다
    return {"rules": rules, "expected_endings": endings,
            "style_examples": _clean_examples([{**c, "path": []} for c in picked]),
            "stats": {"cases": len(cases), "ending_coverage": round(covered / len(lasts), 2),
                      "noun_steps": round(noun_steps, 2)}}
