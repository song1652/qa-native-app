"""TC 초안 생성 작업 — 헤드리스 claude -p 실행기 (PRD F4, D4).

보안 원칙 (PRD D4):
- --restricted: 사용자·프로젝트 설정 파일(훅 포함)을 읽지 않고, 코드 실행 도구를 뺀다.
- --tools "": 파일 도구도 주지 않는다. 소스는 프롬프트로만 넘긴다.
- --strict-mcp-config: MCP 서버를 붙이지 않는다.
- --json-schema: 출력은 DRAFTS_SCHEMA를 통과한 JSON만 받는다 (structured_output).
- 작업 디렉터리는 저장소 밖 임시 폴더다 (프로젝트 CLAUDE.md를 읽지 않게).
- --dangerously-skip-permissions는 절대 쓰지 않는다.

state/tc_library/_jobs/{job_id}/ status.json · run.log · invalid.json · cancel(플래그 파일)
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import _paths
from _state import read_state, update_state
from _tc_library import LibraryError, add_drafts, get_case, load_cases, patch_case, set_draft_meta
from _tc_model import PRIORITIES, now_iso, parse_steps
from _tc_profiles import get_profile
from _tc_prompt import DRAFTS_SCHEMA, build_prompt, chunk_sections
from _tc_review import find_duplicates
from _tc_sources import all_entries, load_bundle, read_text, split_sections

ACTIVE = ("queued", "fetching", "drafting", "validating")
CHUNK_TIMEOUT = int(os.environ.get("TCS_CHUNK_TIMEOUT", "300"))


class JobError(LibraryError):
    pass


def jobs_root() -> Path:
    return _paths.TC_LIBRARY_DIR / "_jobs"


def _job_dir(job_id: str) -> Path:
    if not re.fullmatch(r"job_[0-9a-f]{12}", job_id or ""):
        raise JobError("작업 id가 올바르지 않습니다", "INVALID_JOB")
    return jobs_root() / job_id


def get_job(job_id: str) -> dict:
    path = _job_dir(job_id) / "status.json"
    if not path.exists():
        raise JobError("작업이 없습니다", "JOB_NOT_FOUND", 404)
    return read_state(path)


def _update(job_id: str, **changes) -> dict:
    return update_state(_job_dir(job_id) / "status.json", lambda s: {**s, **changes})


def _log(job_id: str, line: str) -> None:
    with (_job_dir(job_id) / "run.log").open("a", encoding="utf-8") as fh:
        fh.write(f"[{time.strftime('%H:%M:%S')}] {line}\n")


def log_tail(job_id: str, lines: int = 40) -> str:
    path = _job_dir(job_id) / "run.log"
    return "\n".join(path.read_text(encoding="utf-8").splitlines()[-lines:]) if path.exists() else ""


def claude_command() -> list[str]:
    binary = os.environ.get("TCS_CLAUDE_BIN") or shutil.which("claude")
    if not binary:
        raise JobError("claude CLI를 찾을 수 없습니다. Claude Code를 설치하고 로그인하세요.",
                       "CLAUDE_NOT_FOUND", 503)
    cmd = [binary, "-p", "--restricted", "--strict-mcp-config", "--tools", "",
           "--permission-mode", "dontAsk", "--no-session-persistence",
           "--output-format", "json", "--json-schema", json.dumps(DRAFTS_SCHEMA, ensure_ascii=False)]
    if os.environ.get("TCS_CLAUDE_MODEL"):          # 예: sonnet, opus (비우면 CLI 기본 모델)
        cmd += ["--model", os.environ["TCS_CLAUDE_MODEL"]]
    return cmd


def active_job() -> dict | None:
    root = jobs_root()
    if not root.exists():
        return None
    for d in sorted(root.iterdir()):
        status = read_state(d / "status.json")
        if status.get("status") in ACTIVE:
            return status
    return None


def latest_job(suite: str) -> dict | None:
    """저장된 생성 작업에서 스위트의 소스·대상·검토 묶음을 복구한다."""
    jobs = []
    for path in jobs_root().glob('*/status.json'):
        job = read_state(path)
        if job.get('suite') == suite and job.get('mode') == 'new':
            jobs.append((job.get('created_at', ''), path.stat().st_mtime_ns, job))
    return max(jobs, key=lambda item: item[:2])[2] if jobs else None


def create_job(suite: str, *, bundle_id: str, target: dict, profile: str, mode: str = "new",
               case_id: str = "", note: str = "", only_refs: list[str] | None = None) -> dict:
    """mode: new(소스 전체, only_refs면 그 섹션만 — 실패 섹션 재시도) · regenerate(초안 1건, case_id+note 필수)."""
    claude_command()
    get_profile(profile)
    load_bundle(bundle_id)
    if mode not in ("new", "regenerate"):
        raise JobError(f"지원하지 않는 작업 종류입니다: {mode}", "INVALID_MODE")
    if mode == "regenerate" and not (case_id and note.strip()):
        raise JobError("재생성에는 케이스와 메모가 필요합니다", "NOTE_REQUIRED")
    running = active_job()
    if running:
        raise JobError(f"이미 실행 중인 작업이 있습니다 ({running['job_id']})", "JOB_RUNNING", 409)
    job_id = "job_" + secrets.token_hex(6)
    _job_dir(job_id).mkdir(parents=True)
    path = [*(target.get("path") or []), "", "", ""][:3]
    target_data = {"sheet": target["sheet"], "path": path}
    if "platforms" in target:
        target_data["platforms"] = target["platforms"]
    status = {"job_id": job_id, "suite": suite, "bundle_id": bundle_id,
              "target": target_data, "profile": profile,
              "mode": mode, "case_id": case_id, "note": note, "only_refs": list(only_refs or []),
              "status": "queued", "sections": [],
              "kept": 0, "invalid": 0, "reason": "", "cost_usd": 0.0, "created_at": now_iso()}
    update_state(_job_dir(job_id) / "status.json", lambda _: status)
    return status


def cancel_job(job_id: str) -> dict:
    status = get_job(job_id)
    if status["status"] in ACTIVE:
        (_job_dir(job_id) / "cancel").touch()
    return status


def _cancelled(job_id: str) -> bool:
    return (_job_dir(job_id) / "cancel").exists()


def run_claude(prompt: str, *, job_id: str, timeout: int = CHUNK_TIMEOUT) -> tuple[dict, float]:
    """claude -p 1회 실행 → (structured_output, 비용). 취소·시간 초과는 JobError."""
    env = {k: v for k, v in os.environ.items() if k != "NODE_OPTIONS"}
    with tempfile.TemporaryDirectory(prefix="tcs-job-") as workdir:
        proc = subprocess.Popen(claude_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd=workdir, env=env, text=True)
        out: dict = {}

        def communicate() -> None:
            out["stdout"], out["stderr"] = proc.communicate(prompt)

        worker = threading.Thread(target=communicate, daemon=True)
        worker.start()
        deadline = time.monotonic() + timeout
        while worker.is_alive():
            worker.join(0.5)
            if _cancelled(job_id):
                proc.kill()
                worker.join(5)
                raise JobError("취소했습니다", "CANCELLED")
            if time.monotonic() > deadline:
                proc.kill()
                worker.join(5)
                raise JobError(f"{timeout}초 안에 끝나지 않았습니다", "TIMEOUT")
    if proc.returncode != 0:
        raise JobError(f"claude 종료 코드 {proc.returncode}: {(out.get('stderr') or '')[-300:]}", "CLAUDE_ERROR")
    try:
        result = json.loads(out["stdout"])
    except (json.JSONDecodeError, KeyError) as exc:
        raise JobError("claude 출력이 JSON이 아닙니다", "CLAUDE_ERROR") from exc
    if result.get("is_error") or result.get("subtype") != "success" or "structured_output" not in result:
        raise JobError(f"claude 오류: {str(result.get('result', ''))[:300]}", "CLAUDE_ERROR")
    return result["structured_output"], float(result.get("total_cost_usd") or 0)


def build_draft(raw: dict, *, target: dict, allowed: dict[str, str], job_id: str,
                verified_kinds: tuple[str, ...] = ()) -> tuple[dict | None, list[str]]:
    """스키마를 통과한 초안 1건 → (케이스 필드, 구조 오류). 구조 오류가 있으면 케이스를 버린다.

    allowed: {source_ref: 섹션 본문}. 파일·붙여넣기 출처의 화면 문구는 '추정'(verified=False)이다.
    """
    errors = []
    ref = raw.get("source_ref", "")
    if ref not in allowed:
        errors.append(f"출처 {ref!r}가 소스 목록에 없습니다")
    steps = [s.strip() for s in raw.get("steps") or [] if s.strip()]
    steps = [parse_steps(s)[0] if parse_steps(s) else s for s in steps]   # "1. …" 번호가 붙어 와도 뗀다
    if not steps:
        errors.append("Step이 없습니다")
    if not raw.get("expected", "").strip():
        errors.append("Expected가 없습니다")
    if raw.get("priority") not in PRIORITIES:
        errors.append(f"우선순위 {raw.get('priority')!r}")
    base = [p for p in target["path"] if p]
    path = [p.strip() for p in (raw.get("path") or []) if p.strip()]
    if path[: len(base)] != base:      # 대상 가지 기준 상대 경로로 본다
        path = base + path
    path = (path + ["", "", ""])[:3]
    if errors:
        return None, errors
    kind = ref.split(":", 1)[0]
    quote = raw.get("source_quote", "")
    norm = lambda t: re.sub(r"\s+", " ", t).strip()
    return {
        "sheet": target["sheet"], "path": path, "feature": raw["feature"].strip(),
        "precondition": raw.get("precondition", "").strip(), "steps": steps,
        "expected": raw["expected"].strip(),
        "bullets": [{"text": b.strip(), "verified": kind in verified_kinds} for b in raw.get("bullets", []) if b.strip()],
        "priority": raw["priority"], "source_refs": [ref],
        "platforms": target.get("platforms", ["android", "ios"]),
        "draft_meta": {"job_id": job_id, "source_quote": quote,
                       "quote_found": bool(quote) and norm(quote) in norm(allowed[ref])},
    }, []


def run_job(job_id: str, *, runner=run_claude) -> dict:
    """작업을 끝까지 실행한다 (대시보드는 스레드에서 호출). 끝난 status를 돌려준다."""
    job = get_job(job_id)
    try:
        _update(job_id, status="fetching", started_at=now_iso())
        _log(job_id, f"fetching bundle={job['bundle_id']}")
        manifest = load_bundle(job["bundle_id"])
        # 재생성은 초안의 출처가 목록에서 빠졌어도 원문으로 다시 쓴다
        entries = all_entries(manifest) if job["mode"] == "regenerate" else manifest["sources"]
        sources = [{"entry": e, "sections": split_sections(read_text(job["bundle_id"], e["source_id"]))}
                   for e in entries]
        chunks = chunk_sections(sources)
        if job.get("only_refs"):
            chunks = [c for c in ([i for i in chunk if i["ref"] in job["only_refs"]] for chunk in chunks) if c]
        if not chunks:
            raise JobError("소스가 비어 있습니다", "EMPTY_SOURCE")
        profile = get_profile(job["profile"])
        target = job["target"]
        library = load_cases(job["suite"])
        base = [p for p in target["path"] if p]
        examples = [c for c in library if c["sheet"] == target["sheet"] and c["status"] == "approved"
                    and [p for p in c["path"] if p][: len(base)] == base][: profile["examples"]]
        # 같은 가지 예시가 모자라면 프로필의 기준 예시로 채운다 (새 스위트에서도 문체가 흔들리지 않게)
        examples += profile.get("style_examples", [])[: max(0, profile["examples"] - len(examples))]
        regenerate = None
        if job["mode"] == "regenerate":
            case = get_case(job["suite"], job["case_id"])
            regenerate = {"case": {k: case[k] for k in ("path", "feature", "precondition", "steps",
                                                        "expected", "bullets", "priority")},
                          "note": job["note"]}
            wanted = set(case["source_refs"])
            chunks = [[i for i in chunk if i["ref"] in wanted] or chunk for chunk in chunks][:1]
        sections = [{"index": n, "refs": [i["ref"] for i in c], "titles": [i["section"] for i in c],
                     "status": "pending", "kept": 0, "invalid": 0} for n, c in enumerate(chunks)]
        _update(job_id, status="drafting", sections=sections)

        invalid: list[dict] = []
        kept, cost, failed = 0, 0.0, []
        for n, chunk in enumerate(chunks):
            if _cancelled(job_id):
                raise JobError("취소했습니다", "CANCELLED")
            sections[n]["status"] = "running"
            _update(job_id, sections=sections)
            _log(job_id, f"drafting section {n + 1}/{len(chunks)} {sections[n]['titles']}")
            prompt = build_prompt(chunk=chunk, target=target, profile=profile, examples=examples,
                                  regenerate=regenerate)
            try:
                output, spent = runner(prompt, job_id=job_id)
            except JobError as exc:
                if exc.code == "CANCELLED":
                    raise
                sections[n]["status"] = "failed"
                failed.append(f"섹션 {n + 1}: {exc}")
                _log(job_id, f"ERROR section {n + 1}: {exc.code} {exc}")
                _update(job_id, sections=sections)
                continue
            cost += spent
            allowed = {i["ref"]: i["text"] for i in chunk}
            drafts = []
            for raw in output.get("cases", []):
                draft, errors = build_draft(raw, target=target, allowed=allowed, job_id=job_id,
                                            verified_kinds=("figma",))   # Figma 화면 문구 = 확인된 문구
                if errors:
                    invalid.append({"section": n + 1, "raw": raw, "errors": errors})
                    sections[n]["invalid"] += 1
                else:
                    draft["draft_meta"]["profile"] = profile["name"]   # 초안 검토 때 문체를 이 프로필로 검사
                    drafts.append(draft)
            _update(job_id, status="validating")
            for draft in drafts:
                draft["draft_meta"]["duplicates"] = find_duplicates(draft, library)
            if regenerate and drafts:
                current = get_case(job["suite"], job["case_id"])
                fields = {k: drafts[0][k] for k in ("path", "feature", "precondition", "steps",
                                                    "expected", "bullets", "priority")}
                patch_case(job["suite"], job["case_id"], current["rev"], fields, "generator")
                set_draft_meta(job["suite"], job["case_id"], {**drafts[0]["draft_meta"],
                    "job_id": current.get("draft_meta", {}).get("job_id", job_id),
                    "regenerated_job_id": job_id, "regenerated_note": job["note"]})
                sections[n]["kept"] = 1
                kept += 1
            elif drafts:
                add_drafts(job["suite"], drafts, "generator")
                sections[n]["kept"] = len(drafts)
                kept += len(drafts)
            sections[n]["status"] = "done"
            _log(job_id, f"section {n + 1} ok kept={sections[n]['kept']} invalid={sections[n]['invalid']}")
            _update(job_id, status="drafting", sections=sections, kept=kept,
                    invalid=len(invalid), cost_usd=round(cost, 4))
        (_job_dir(job_id) / "invalid.json").write_text(
            json.dumps(invalid, ensure_ascii=False, indent=2), encoding="utf-8")
        final = "failed" if failed else "done"
        _log(job_id, f"status={final} kept={kept} invalid={len(invalid)} cost=${cost:.4f}")
        return _update(job_id, status=final, reason="; ".join(failed), kept=kept,
                       invalid=len(invalid), finished_at=now_iso())
    except JobError as exc:
        _log(job_id, f"ERROR {exc.code}: {exc}")
        return _update(job_id, status="cancelled" if exc.code == "CANCELLED" else "failed",
                       reason=str(exc), finished_at=now_iso())
    except Exception as exc:  # 예기치 못한 오류도 작업을 '실패'로 끝낸다 (UI가 멈추지 않게)
        _log(job_id, f"ERROR unexpected: {exc!r}")
        return _update(job_id, status="failed", reason=f"내부 오류: {exc}", finished_at=now_iso())


def invalid_drafts(job_id: str) -> list[dict]:
    path = _job_dir(job_id) / "invalid.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def start_background(job_id: str) -> threading.Thread:
    thread = threading.Thread(target=run_job, args=(job_id,), name=f"tcs-{job_id}", daemon=True)
    thread.start()
    return thread
