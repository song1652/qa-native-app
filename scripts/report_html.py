"""공통 HTML 리포트 생성 모듈 (앱 QA 전용).

CSS/JS 스타일은 qa-native와 동일하게 유지.
앱 전용 로직(parse_pipeline_to_groups, TC 마크다운 파싱)은 별도 보존.
"""
import html as _html
import json
import re
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).parent.parent
TESTCASES_DIR = ROOT / "testcases"
REPORTS_DIR = ROOT / "tests" / "reports"
RUNS_DIR = ROOT / "state" / "runs"

CASES_PER_PAGE = 20

_re_step = re.compile(r"^\s*\d+[\.\)]\s*")
_re_bullet = re.compile(r"^\s*[-*]\s*")


def _esc(text: str) -> str:
    return _html.escape(str(text), quote=True)


def _strip_prefix(text: str) -> str:
    t = _re_step.sub("", text)
    t = _re_bullet.sub("", t)
    return t.strip()


def _parse_tc_meta_from_md(filepath: str) -> dict:
    """TC 파일 경로에서 대응하는 .md를 찾아 steps와 expected를 반환."""
    p = Path(filepath)
    stem = p.stem

    parts = p.parts
    md_path = None
    try:
        gen_idx = next(i for i, x in enumerate(parts) if x == "generated")
        generated_platform = parts[gen_idx + 1] if len(parts) > gen_idx + 1 else ""
        relative_parts = parts[gen_idx + 2:]
        if generated_platform in ("android", "ios"):
            candidate = TESTCASES_DIR / generated_platform / Path(*relative_parts)
        else:
            candidate = TESTCASES_DIR / Path(*relative_parts)
        candidate = candidate.with_suffix(".md")
        if candidate.exists():
            md_path = candidate
    except (StopIteration, IndexError):
        pass

    if md_path is None:
        candidate = TESTCASES_DIR / f"{stem}.md"
        if candidate.exists():
            md_path = candidate

    # ios_test/ 폴더 직접 탐색
    if md_path is None:
        for candidate in TESTCASES_DIR.rglob(f"{stem}.md"):
            md_path = candidate
            break

    if md_path is None:
        return {"title": stem, "precondition": [], "steps": [], "expected": ""}

    text = md_path.read_text(encoding="utf-8")

    title_match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else stem

    precondition_match = re.search(
        r"##\s*(?:사전\s*조건|전제조건|전제\s*조건|Precondition)\s*\n(.*?)(?=\n##|\Z)",
        text, re.DOTALL | re.IGNORECASE,
    )
    precondition = []
    if precondition_match:
        for line in precondition_match.group(1).splitlines():
            clean = re.sub(r"^\s*[-*]\s*", "", line).strip()
            if clean:
                precondition.append(clean)

    steps_match = re.search(
        r"##\s*(?:테스트\s*단계|단계|Steps?)\s*\n(.*?)(?=\n##|\Z)",
        text, re.DOTALL | re.IGNORECASE,
    )
    steps = []
    if steps_match:
        for line in steps_match.group(1).splitlines():
            m = re.match(r"^\s*\d+[\.\)]\s+(.+)", line)
            if m:
                steps.append(m.group(1).strip())

    exp_match = re.search(
        r"##\s*(?:예상\s*결과|기대\s*결과|기대결과|Expected(?:\s*Result)?)\s*\n(.*?)(?=\n##|\Z)",
        text, re.DOTALL | re.IGNORECASE,
    )
    expected_lines = []
    if exp_match:
        for line in exp_match.group(1).splitlines():
            clean = re.sub(r"^\s*[-*]\s*", "", line).strip()
            if clean:
                expected_lines.append(clean)
    expected = "\n".join(expected_lines)

    return {
        "title": title,
        "precondition": precondition,
        "steps": steps,
        "expected": expected,
    }


def _load_run_manifest(run_id: str) -> dict:
    """observability run manifest(state/runs/{run_id}/artifacts/manifest.json)를 읽는다."""
    if not run_id:
        return {}
    manifest_path = RUNS_DIR / run_id / "artifacts" / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _obs_artifact_urls(manifest: dict, run_id: str, filepath: str, test_name: str) -> dict:
    """manifest에서 file+test에 해당하는 최신 attempt의 영상·스크린샷 URL을 찾는다.

    영상/스크린샷은 대시보드가 서빙하는 /api/run_artifacts/{run_id}/... 엔드포인트를
    통해 HTTP로 제공되므로, 리포트 HTML을 어디서 열든(파일 직접 열기 제외) 재생 가능하다.
    """
    for entry in manifest.get("entries", []):
        nodeid = entry.get("nodeid", "")
        if not nodeid.startswith(filepath + "::"):
            continue
        if test_name and not nodeid.endswith("::" + test_name):
            continue
        attempts = []
        encoded = urllib.parse.quote(nodeid, safe="")
        for attempt in entry.get("attempts") or [entry]:
            item = {"n": attempt.get("n", 1), "kept": bool(attempt.get("kept"))}
            for key, endpoint in (("video", "video"), ("screenshot", "screenshot"), ("syslog", "logcat")):
                if item["kept"] and attempt.get(key):
                    item[key + "_url"] = (
                        f"/api/run_artifacts/{run_id}/{endpoint}"
                        f"?nodeid={encoded}&attempt={item['n']}"
                    )
            attempts.append(item)
        return {**attempts[-1], "attempts": attempts} if attempts else {}
    return {}


_UNKNOWN_SCREEN = "other"
_KNOWN_SCREENS = ["login", "file_list", "file_detail"]


def _extract_screen(filepath: str) -> str:
    parts = Path(filepath).parts
    try:
        gen_idx = next(i for i, p in enumerate(parts) if p == "generated")
        group_idx = gen_idx + 2
        if len(parts) > group_idx:
            subfolder = parts[group_idx]
            if not subfolder.startswith("_") and not subfolder.startswith("."):
                return subfolder
    except StopIteration:
        pass
    stem = Path(filepath).stem.lower()
    for kw in ["login", "file_list", "file_detail"]:
        if kw in stem:
            return kw
    return _UNKNOWN_SCREEN


def parse_pipeline_to_groups(pipeline_state: dict) -> list:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    execute_results = pipeline_state.get("execute_results", {})
    errors: list = execute_results.get("errors", [])
    passed_files: list = execute_results.get("passed", [])

    run_id = pipeline_state.get("last_run_id") or pipeline_state.get("obs_last_run_id") or ""
    manifest = _load_run_manifest(run_id)

    groups: dict = {}

    def _get_group(screen: str) -> dict:
        if screen not in groups:
            groups[screen] = {"passed": 0, "failed": 0, "cases": []}
        return groups[screen]

    for entry in errors:
        filepath = entry.get("file", "")
        test_name = entry.get("test", "")
        screen = _extract_screen(filepath)
        g = _get_group(screen)
        g["failed"] += 1
        tc_meta = _parse_tc_meta_from_md(filepath)
        artifact_urls = _obs_artifact_urls(manifest, run_id, filepath, test_name)
        g["cases"].append({
            "file": filepath,
            "title": tc_meta["title"],
            "test": test_name,
            "outcome": "failed",
            "error": entry.get("error", ""),
            "screenshot_url": artifact_urls.get("screenshot_url", ""),
            "video_url": artifact_urls.get("video_url", ""),
            "attempts": artifact_urls.get("attempts", []),
            "precondition": tc_meta["precondition"],
            "steps": tc_meta["steps"],
            "expected": tc_meta["expected"],
        })

    for filepath in passed_files:
        screen = _extract_screen(filepath)
        g = _get_group(screen)
        g["passed"] += 1
        tc_meta = _parse_tc_meta_from_md(filepath)
        g["cases"].append({
            "file": filepath,
            "title": tc_meta["title"],
            "test": "",
            "outcome": "passed",
            "error": "",
            "precondition": tc_meta["precondition"],
            "steps": tc_meta["steps"],
            "expected": tc_meta["expected"],
        })

    ordered_screens = [s for s in _KNOWN_SCREENS if s in groups]
    extra_screens = [s for s in groups if s not in _KNOWN_SCREENS]
    all_screens = ordered_screens + extra_screens

    result = []
    for screen in all_screens:
        g = groups[screen]
        total = g["passed"] + g["failed"]
        all_pass = g["failed"] == 0 and total > 0
        rows_html = ""
        for idx, case in enumerate(g["cases"]):
            uid = f"{screen}_{idx}"
            rows_html += case_row(
                {
                    "title": case.get("title", case["file"]),
                    "precondition": case.get("precondition", []),
                    "steps": case.get("steps", []),
                    "expected": case.get("expected", ""),
                    "error": case.get("error", ""),
                    "screenshot_url": case.get("screenshot_url", ""),
                    "video": pipeline_state.get("video_path", ""),
                    "video_url": case.get("video_url", ""),
                    "attempts": case.get("attempts", []),
                },
                uid,
                case["outcome"],
            )
        result.append({
            "label": screen,
            "rows_html": rows_html,
            "pass_cnt": g["passed"],
            "total_cnt": total,
            "all_pass": all_pass,
            "has_tests": total > 0,
            "skip_cnt": 0,
            "screen": screen,
            "passed": g["passed"],
            "failed": g["failed"],
            "cases": g["cases"],
        })

    return result


def _resolve_media_uri(path_str: str) -> str:
    if not path_str:
        return ""
    p = Path(path_str)
    candidates = [p] if p.is_absolute() else [
        REPORTS_DIR / path_str,
        ROOT / path_str,
        Path(path_str),
    ]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved.exists():
                return resolved.as_uri()
        except Exception:
            continue
    return ""


def _build_artifact_panel(video: str, screenshot_url: str = "", video_url: str = "") -> str:
    parts = []

    # 스크린샷은 관측성 run manifest에서 얻은 HTTP URL(/api/run_artifacts/...)만
    # 사용한다. 대시보드가 서빙하는 리포트 페이지에서 바로 표시되며, file:// URI와
    # 달리 브라우저의 mixed-content 차단에 걸리지 않는다.
    ss_uri = screenshot_url
    if ss_uri:
        parts.append(
            f'<div class="artifact-sub">'
            f'<div class="artifact-sub-title">스크린샷</div>'
            f'<div class="screenshot-wrap">'
            f'<img src="{_esc(ss_uri)}" class="screenshot-thumb" alt="실행 시점의 기기 화면">'
            f'</div>'
            f'</div>'
        )

    vid_uri = video_url or _resolve_media_uri(video)
    if vid_uri:
        parts.append(
            f'<div class="artifact-sub">'
            f'<div class="artifact-sub-title">영상</div>'
            f'<video src="{_esc(vid_uri)}" controls class="artifact-video"></video>'
            f'<a href="{_esc(vid_uri)}" class="artifact-dl" download>영상 내려받기</a>'
            f'</div>'
        )

    if not parts:
        return ""
    return f'<div class="artifact-panel">{"".join(parts)}</div>'


def _error_summary(error: str) -> str:
    for name, message in (
        ("NoSuchElement", "화면에서 요소를 찾지 못했습니다"),
        ("Timeout", "응답을 기다리는 시간이 초과되었습니다"),
        ("AssertionError", "실제 결과가 기대 결과와 다릅니다"),
        ("SessionNotCreated", "앱 자동화 세션을 시작하지 못했습니다"),
        ("InvalidSession", "앱 자동화 세션 연결이 끊겼습니다"),
    ):
        if name in error:
            return message
    return "테스트 실행 중 오류가 발생했습니다"


def _attempt_panel(attempts: list) -> str:
    if not attempts:
        return ""
    buttons, panels = [], []
    for index, attempt in enumerate(attempts):
        number = _esc(attempt.get("n", index + 1))
        selected = index == len(attempts) - 1
        buttons.append(
            f'<button type="button" data-attempt="{number}" aria-pressed="{str(selected).lower()}">{number}차</button>'
        )
        content = _build_artifact_panel("", attempt.get("screenshot_url", ""), attempt.get("video_url", ""))
        if attempt.get("syslog_url"):
            content += f'<a class="artifact-dl" href="{_esc(attempt["syslog_url"])}" target="_blank" rel="noopener">시스템 로그</a>'
        if not content:
            content = '<p class="evidence-empty">보존된 증거가 없습니다.</p>'
        panels.append(f'<div data-attempt-panel="{number}"{ "" if selected else " hidden"}>{content}</div>')
    return ('<aside class="attempt-evidence"><h3>시도별 증거</h3>'
            '<div class="attempt-tabs" role="group" aria-label="시도 선택">'
            + ''.join(buttons) + '</div>' + ''.join(panels) + '</aside>')


def case_row(case: dict, uid: str, outcome) -> str:
    if isinstance(outcome, bool):
        outcome = "passed" if outcome else "failed"
    _cls_map = {"passed": "pass", "failed": "fail", "skipped": "skip"}
    _txt_map = {"passed": "통과", "failed": "실패", "skipped": "건너뜀"}
    status_cls = _cls_map.get(outcome, "fail")
    badge_txt = _txt_map.get(outcome, "실패")

    title = case.get("title", "untitled")
    precondition = case.get("precondition", [])
    steps = case.get("steps", [])
    expected = case.get("expected", "")
    error_msg = case.get("error", "")
    video = case.get("video", "")
    screenshot_url = case.get("screenshot_url", "")
    video_url = case.get("video_url", "")

    clean_steps = [_esc(_strip_prefix(s)) for s in steps if s.strip()]
    steps_html = "".join(f"<li>{s}</li>" for s in clean_steps) if clean_steps else "<li>-</li>"

    exp_lines = [_esc(_strip_prefix(ln)) for ln in expected.splitlines() if ln.strip()]
    exp_content = "<br>".join(exp_lines) if exp_lines else "-"
    pre_lines = [_esc(_strip_prefix(ln)) for ln in precondition if str(ln).strip()]
    pre_content = "<br>".join(pre_lines) if pre_lines else "-"

    error_section = ""
    if outcome == "failed" and error_msg:
        error_section = (
            f'<div class="error-summary" role="alert"><strong>{_error_summary(error_msg)}</strong>'
            f'<details><summary>전체 오류 보기</summary><pre>{_esc(error_msg)}</pre></details></div>'
        )

    artifact_html = ""
    if outcome == "failed":
        artifact_html = _attempt_panel(case.get("attempts", [])) or _build_artifact_panel(video, screenshot_url, video_url)

    return (
        f'<div class="case-item {status_cls}" data-status="{status_cls}" data-toggle="{uid}">'
        f'  <button type="button" class="case-header" aria-expanded="false" aria-controls="detail_{uid}">'
        f'    <span class="case-dot {status_cls}"></span>'
        f'    <span class="case-title">{_esc(title)}</span>'
        f'    <span class="case-right">'
        f'      <span class="case-status-txt {status_cls}">{badge_txt}</span>'
        f'      <span class="chevron" id="chv_{uid}">&#8250;</span>'
        f'    </span>'
        f'  </button>'
        f'  <div class="case-detail" id="detail_{uid}"><div class="case-columns"><div class="case-description">{error_section}'
        f'    <div class="detail-row">'
        f'      <span class="detail-label">사전 조건</span>'
        f'      <span class="detail-val">{pre_content}</span>'
        f'    </div>'
        f'    <div class="detail-row">'
        f'      <span class="detail-label">단계</span>'
        f'      <span class="detail-val"><ol class="steps-list">{steps_html}</ol></span>'
        f'    </div>'
        f'    <div class="detail-row">'
        f'      <span class="detail-label">기대 결과</span>'
        f'      <span class="detail-val">{exp_content}</span>'
        f'    </div>'
        f'    </div>{artifact_html}</div>'
        f'  </div>'
        f'</div>'
    )


def build_group_section(label: str, rows_html: str,
                        g_pass_cnt: int, g_total_cnt: int,
                        g_passed: bool, has_tests: bool,
                        g_skip_cnt: int = 0) -> str:
    status_cls = "pass" if g_passed else ("fail" if has_tests else "warn")
    g_fail_cnt = g_total_cnt - g_pass_cnt - g_skip_cnt
    status_txt = "통과" if g_passed else ("실패" if has_tests else "N/A")
    if g_passed and g_skip_cnt > 0:
        status_txt = f"통과 · {g_skip_cnt}건 건너뜀"
    display_label = _esc(label)
    skip_btn = (
        f'<button class="fbtn skip" data-filter="{label}" data-filter-val="skip">'
        f'건너뜀 ({g_skip_cnt})</button>'
        if g_skip_cnt > 0 else ""
    )

    return f"""
<section class="group-card" id="group_{label}">
  <div class="group-header {status_cls}">
    <button type="button" class="group-title-wrap" data-toggle-group="{label}" aria-expanded="false" aria-controls="gbody_{label}">
      <span class="group-chevron" id="gchv_{label}">&#9654;</span>
      <span class="group-dot {status_cls}"></span>
      <span class="group-title">{display_label}</span>
      <span class="group-sub">{g_pass_cnt} / {g_total_cnt - g_skip_cnt} 통과{f" · {g_skip_cnt}건 건너뜀" if g_skip_cnt else ""}</span>
    </button>
    <div class="group-right">
      <span class="badge {status_cls}">{status_txt}</span>
    </div>
  </div>
  <div class="filter-bar" id="fbar_{label}">
      <button class="fbtn active" data-filter="{label}" data-filter-val="all">전체 ({g_total_cnt})</button>
      <button class="fbtn pass" data-filter="{label}" data-filter-val="pass">통과 ({g_pass_cnt})</button>
      <button class="fbtn fail" data-filter="{label}" data-filter-val="fail">실패 ({g_fail_cnt})</button>
      {skip_btn}
      <span class="pager" id="pager_{label}"></span>
  </div>
  <div class="group-body" id="gbody_{label}" style="display:none">
    <div class="case-list" id="clist_{label}">{rows_html}</div>
  </div>
</section>"""


def report_css() -> str:
    tokens = (ROOT / "agents/dashboard/static/tokens.css").read_text(encoding="utf-8")
    return """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
""" + tokens + """
:root{--text2:var(--text-2);--text3:var(--text-3);--surface2:var(--surface-sub);--skip:var(--warn);--skip-bg:var(--warn-bg)}
*{box-sizing:border-box;margin:0;padding:0}[hidden]{display:none!important}
body{background:var(--bg);color:var(--text);font:14px/1.6 var(--font-sans)}
button,a{font:inherit}button{cursor:pointer;white-space:nowrap}button:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}a{color:var(--accent)}
.report-header{background:var(--bg)}
.topbar{max-width:1304px;margin:auto;padding:20px 32px;display:flex;gap:20px;align-items:center;justify-content:space-between}
.report-actions{display:none}
.topbar>div:first-child{min-width:0}.topbar>div:first-child>div:first-child{flex-wrap:wrap}.meta{overflow-wrap:anywhere}.topbar h1{font-size:22px;font-weight:600}.meta{font:13px var(--font-mono);color:var(--text-2);margin-top:6px}
.overall-badge,.platform-badge,.badge,.case-status-txt{font-size:12px;font-weight:600;white-space:nowrap;border-radius:4px;padding:2px 8px}
.platform-badge{background:var(--surface-sub);color:var(--text-2)}
.overall-badge.pass,.badge.pass,.case-status-txt.pass{background:var(--pass-bg);color:var(--pass)}
.overall-badge.fail,.badge.fail,.case-status-txt.fail{background:var(--fail-bg);color:var(--fail)}
.badge.warn,.case-status-txt.skip{background:var(--warn-bg);color:var(--warn)}
.layout{max-width:1304px;margin:auto;padding:24px 32px;display:grid;grid-template-columns:minmax(0,1fr);gap:24px;align-items:start}
.sidebar{max-width:1304px;margin:auto;padding:20px 32px 0;min-width:0}.sidebar-logo{display:none}.logo-text{font-size:15px;font-weight:600}.logo-sub{font-size:12px;color:var(--text-3);overflow-wrap:anywhere}
.nav-label{font:500 12px var(--font-mono);letter-spacing:.08em;color:var(--text-3);padding:0 0 10px}.nav-section ul{list-style:none;display:flex;flex-wrap:wrap;gap:8px}.nav-section li{min-width:0;max-width:100%}
.nav-item{width:auto;max-width:100%;min-width:0;border:1px solid var(--border);background:var(--surface);color:inherit;text-align:left;white-space:normal;display:flex;gap:8px;padding:8px 12px;align-items:center;border-radius:6px;font-size:13px;cursor:pointer;overflow-wrap:anywhere}
.nav-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.nav-item.active{background:var(--accent-bg);color:var(--accent);border-color:var(--accent);font-weight:600}.nav-count{margin-left:4px;font:12px var(--font-mono);white-space:nowrap}
.nav-dot,.group-dot,.case-dot{height:7px;width:7px;flex-shrink:0;border-radius:50%}.pass.nav-dot,.pass.group-dot,.pass.case-dot{background:var(--pass)}.fail.nav-dot,.fail.group-dot,.fail.case-dot{background:var(--fail)}.warn.nav-dot,.warn.group-dot,.skip.case-dot{background:var(--warn)}
.main{min-width:0;display:grid;gap:20px}.stats{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));background:var(--surface);border:1px solid var(--border);border-radius:8px}
.stat-card{padding:14px 16px;display:flex;flex-direction:column-reverse;border-left:1px solid var(--border)}.stat-card:first-child{border:0}.stat-num{font:600 24px var(--font-mono);margin-top:4px}.stat-lbl{font-size:13px;color:var(--text-2);white-space:nowrap}
.group-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden;min-width:0}
.group-header,.group-title-wrap,.group-right{display:flex;align-items:center;gap:10px}.group-header{padding:14px 16px;justify-content:space-between;flex-wrap:wrap;border-bottom:1px solid var(--border)}.group-title-wrap{border:0;background:transparent;color:inherit;text-align:left;white-space:normal;min-width:0;flex:1;flex-wrap:wrap}.group-title{font:600 14px var(--font-mono);overflow-wrap:anywhere}.group-sub{font-size:13px;color:var(--text-2);white-space:nowrap}.group-chevron,.chevron{display:inline-block;color:var(--text-3)}.group-chevron.open,.chevron.open{transform:rotate(90deg)}
.filter-bar{display:flex;gap:0;padding:12px 16px;align-items:center;flex-wrap:wrap;border-bottom:1px solid var(--border)}.fbtn{min-height:32px;padding:0 12px;background:var(--surface);color:var(--text-2);border:1px solid var(--border);border-radius:0}.fbtn:first-child{border-radius:6px 0 0 6px}.fbtn.active{background:var(--text);color:var(--on-accent);border-color:var(--text)}.pager{margin-left:auto;font:12px var(--font-mono)}.pager button{padding:4px 10px;border:1px solid var(--border);border-radius:6px;background:var(--surface)}
.case-item{border-top:1px solid var(--border)}.case-header{width:100%;border:0;background:transparent;color:inherit;text-align:left;white-space:normal;display:flex;align-items:center;gap:12px;padding:14px 16px;cursor:pointer}.case-header:focus-visible{outline-offset:-3px}.case-item:hover>.case-header{background:var(--surface-sub)}.case-title{min-width:0;flex:1;font-weight:500;overflow-wrap:anywhere}.case-right{display:flex;gap:10px;align-items:center}.chevron{font-size:20px}
.case-detail{display:none;padding:20px 16px 20px 40px;border-top:1px solid var(--border)}.case-columns{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:24px}.case-columns:not(:has(.attempt-evidence,.artifact-panel)){grid-template-columns:1fr}.case-description{min-width:0;display:grid;align-content:start;gap:18px}
.detail-row{display:flex;flex-direction:column;gap:6px}.detail-label{font-size:12px;color:var(--text-2)}.detail-val{font-size:14px;overflow-wrap:anywhere}.steps-list{padding-left:20px}.steps-list li{padding:2px 0}
.error-summary{background:var(--fail-bg);border-radius:6px;padding:14px 16px;color:var(--fail)}.error-summary strong{overflow-wrap:anywhere;font-size:14px;font-weight:600}.error-summary details{margin-top:10px;color:var(--text-2);font-size:13px}.error-summary summary{cursor:pointer}.error-summary pre{margin-top:8px;padding:10px 12px;border-radius:6px;background:var(--surface);font:12px/1.7 var(--font-mono);white-space:pre-wrap;overflow-wrap:anywhere}
.attempt-evidence{min-width:0}.attempt-evidence h3{font-size:12px;font-weight:500;color:var(--text-2);margin-bottom:12px}.attempt-tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}.attempt-tabs button{height:32px;padding:0 12px;border:1px solid var(--border);background:var(--surface);border-radius:6px;color:var(--text-2);font-size:13px}.attempt-tabs [aria-pressed=true]{background:var(--accent-bg);color:var(--accent);border-color:var(--accent)}
.artifact-panel{border:1px solid var(--border);border-radius:8px;overflow:hidden;background:var(--log-bg)}.artifact-sub{padding:12px}.artifact-sub+.artifact-sub{border-top:1px solid var(--border)}.artifact-sub-title{font-size:12px;color:var(--text-2);margin-bottom:8px}.screenshot-thumb{display:block;width:100%;height:420px;object-fit:contain;cursor:zoom-in}.artifact-video{width:100%;max-height:260px;background:var(--surface-sub)}.artifact-dl{display:inline-block;margin-top:8px;font-size:13px}.evidence-empty{font-size:13px;color:var(--text-3);background:var(--surface-sub);padding:16px;border-radius:6px}
.lb-overlay{display:none;position:fixed;inset:0;background:var(--backdrop);z-index:9999;align-items:center;justify-content:center;cursor:zoom-out}.lb-overlay.open{display:flex}.lb-overlay img{max-width:92vw;max-height:92vh;object-fit:contain;border-radius:8px;box-shadow:var(--shadow-modal)}
@media(max-width:1000px){.layout{grid-template-columns:minmax(0,1fr);padding:20px}.case-columns{grid-template-columns:1fr}.stat-card{padding:12px}.stat-num{font-size:20px}}
@media(max-width:640px){.layout{grid-template-columns:1fr}.sidebar{position:static}.sidebar{padding:16px 16px 0}.stats{grid-template-columns:repeat(5,minmax(0,1fr))}.stat-card{padding:12px 6px}.stat-num{font-size:14px}.stat-lbl{font-size:12px}.nav-item,.group-title-wrap,.fbtn,.attempt-tabs button,.pager button{min-height:44px}.pager{display:flex;align-items:center;gap:8px;margin-top:8px}.filter-bar{row-gap:8px}.topbar{padding:16px;flex-wrap:wrap}.case-detail{padding:16px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
@media print{.sidebar,.filter-bar,.attempt-tabs,.report-actions{display:none}.layout{display:block;max-width:none}.case-detail,.group-body{display:block!important}.group-card{break-inside:avoid}}
"""


def report_display_script() -> str:
    """Adapt saved QA report layout while retaining its content and handlers."""
    return """
document.addEventListener('DOMContentLoaded', function(){
  var sidebar=document.querySelector('.sidebar');
  if(sidebar && sidebar.parentElement!==document.body) document.body.prepend(sidebar);
  document.querySelectorAll('.topbar > .report-actions').forEach(function(actions){actions.remove();});
  var label=document.querySelector('.nav-label');
  if(label) label.textContent='그룹';
  document.querySelectorAll('.group-header > .filter-bar').forEach(function(bar){
    bar.parentElement.after(bar);
  });
  var first=document.querySelector('.group-card');
  if(first && typeof toggleGroup==='function' && typeof _gs==='function'){
    var key=first.id.replace('group_','');
    if(!_gs(key).open) toggleGroup(key);
  }
});
"""


def report_js() -> str:
    return """
var _gState = {};
var PP = """ + str(CASES_PER_PAGE) + """;

function _gs(label) {
  if (!_gState[label]) _gState[label] = {filter:'all', page:1, open:false};
  return _gState[label];
}

function toggle(uid) {
  var d=document.getElementById('detail_'+uid);
  var c=document.getElementById('chv_'+uid);
  if(d.style.display==='none'||!d.style.display){d.style.display='block';c.classList.add('open');}
  else{d.style.display='none';c.classList.remove('open');}
  d.closest('.case-item').querySelector('.case-header').setAttribute('aria-expanded',String(d.style.display==='block'));
}

function scrollToGroup(label) {
  var el=document.getElementById('group_'+label);
  if(el)el.scrollIntoView({behavior:'smooth',block:'start'});
}

var _selectedNav = 'all';

function selectNav(label) {
  document.querySelectorAll('.nav-item').forEach(function(el){el.classList.remove('active');});
  var navEl = document.getElementById('nav_'+label);
  if(navEl) navEl.classList.add('active');
  _selectedNav = label;
  var cards = document.querySelectorAll('.group-card');
  if(label === 'all') {
    cards.forEach(function(card){
      card.style.display = '';
      var gl = card.id.replace('group_','');
      var st = _gs(gl);
      if(st.open) toggleGroup(gl);
    });
  } else {
    cards.forEach(function(card){
      var gl = card.id.replace('group_','');
      if(gl === label) {
        card.style.display = '';
        var st = _gs(gl);
        if(!st.open) toggleGroup(gl);
        scrollToGroup(label);
      } else {
        card.style.display = 'none';
      }
    });
  }
}

function toggleGroup(label) {
  var st=_gs(label); st.open=!st.open;
  var body=document.getElementById('gbody_'+label);
  var chv=document.getElementById('gchv_'+label);
  if(st.open){body.style.display='block';chv.classList.add('open');applyFilter(label);}
  else{body.style.display='none';chv.classList.remove('open');}
  document.getElementById('group_'+label).querySelector('[data-toggle-group]').setAttribute('aria-expanded',String(st.open));
}

function setFilter(label, f) {
  var st=_gs(label); st.filter=f; st.page=1;
  applyFilter(label);
}

function setPage(label, p) {
  var st=_gs(label); st.page=p;
  applyFilter(label);
}

function applyFilter(label) {
  var st=_gs(label);
  var list=document.getElementById('clist_'+label);
  var items=list.querySelectorAll('.case-item');
  var visible=[];
  items.forEach(function(el){
    if(st.filter==='all'||el.dataset.status===st.filter){visible.push(el);el.style.display='';}
    else{el.style.display='none';}
  });
  var total=visible.length;
  var pages=Math.max(1,Math.ceil(total/PP));
  st.page=Math.min(st.page,pages);
  var start=(st.page-1)*PP;
  visible.forEach(function(el,i){
    el.style.display=(i>=start&&i<start+PP)?'':'none';
  });
  var bar=document.getElementById('fbar_'+label);
  bar.querySelectorAll('.fbtn').forEach(function(btn){btn.classList.remove('active');});
  bar.querySelectorAll('.fbtn').forEach(function(btn){
    if(st.filter==='all'&&btn.textContent.startsWith('전체'))btn.classList.add('active');
    if(st.filter==='pass'&&btn.textContent.startsWith('통과'))btn.classList.add('active');
    if(st.filter==='fail'&&btn.textContent.startsWith('실패'))btn.classList.add('active');
    if(st.filter==='skip'&&btn.textContent.startsWith('건너뜀'))btn.classList.add('active');
  });
  var pg=document.getElementById('pager_'+label);
  if(pages>1){
    pg.innerHTML='<button data-page-group="'+label+'" data-page-dir="prev"'+(st.page<=1?' disabled':'')+'>\\u00ab</button>'
      +'<span>'+st.page+' / '+pages+'</span>'
      +'<button data-page-group="'+label+'" data-page-dir="next"'+(st.page>=pages?' disabled':'')+'>\\u00bb</button>';
  }else{pg.innerHTML='';}
}

function _openLb(src) {
  var ov = document.getElementById('lb-overlay');
  if (!ov) return;
  document.getElementById('lb-img').src = src;
  ov.classList.add('open');
}

document.addEventListener('click', function(e) {
  var t;
  t = e.target.closest('#lb-overlay');
  if(t){t.classList.remove('open');return;}
  t = e.target.closest('.screenshot-thumb');
  if(t){_openLb(t.src);return;}
  t = e.target.closest('[data-attempt]');
  if(t){
    var panel=t.closest('.attempt-evidence');
    panel.querySelectorAll('[data-attempt]').forEach(function(button){button.setAttribute('aria-pressed',String(button===t));});
    panel.querySelectorAll('[data-attempt-panel]').forEach(function(item){item.hidden=item.dataset.attemptPanel!==t.dataset.attempt;});
    return;
  }
  if(e.target.closest('.case-detail')) return;
  t = e.target.closest('[data-toggle]');
  if(t){toggle(t.getAttribute('data-toggle'));return;}
  t = e.target.closest('[data-toggle-group]');
  if(t){toggleGroup(t.getAttribute('data-toggle-group'));return;}
  t = e.target.closest('[data-filter]');
  if(t){setFilter(t.getAttribute('data-filter'),t.getAttribute('data-filter-val'));return;}
  t = e.target.closest('[data-nav]');
  if(t){selectNav(t.getAttribute('data-nav'));return;}
  t = e.target.closest('[data-page-group]');
  if(t&&!t.disabled){
    var gl=t.getAttribute('data-page-group');
    var st=_gs(gl);
    var dir=t.getAttribute('data-page-dir');
    setPage(gl, dir==='prev'?st.page-1:st.page+1);
  }
});

(function(){
  var ov=document.createElement('div');
  ov.id='lb-overlay';ov.className='lb-overlay';
  var img=document.createElement('img');img.id='lb-img';
  ov.appendChild(img);
  if(document.body) document.body.appendChild(ov);
  else document.addEventListener('DOMContentLoaded',function(){document.body.appendChild(ov);});
})();
"""


def build_report(groups_data: list, summary: dict,
                 created_at: str, subtitle: str = "App Test Report",
                 video_path: "str | None" = None,
                 platform: str = "", run_id: str = "",
                 run_type: str = "execution") -> str:
    run_type = run_type if run_type in ("quick", "pipeline") else "execution"
    pass_total = summary.get("passed", 0)
    fail_total = summary.get("failed", 0) + summary.get("error", 0)
    skip_total = summary.get("skipped", 0)
    total = pass_total + fail_total + skip_total
    pass_rate = round(pass_total / total * 100, 1) if total else 0
    all_pass = fail_total == 0
    overall_cls = "pass" if all_pass else "fail"
    overall_txt = "전체 통과" if all_pass else f"실패 {fail_total}건"

    platform_badge = ""
    if platform:
        platform_badge = f'<span class="platform-badge {platform}">{_esc("Android" if platform == "android" else "iOS" if platform == "ios" else platform)}</span>'

    nav_items = f'<li><button type="button" class="nav-item active" id="nav_all" data-nav="all">전체 ({total})</button></li>\n'
    for g in groups_data:
        lbl = g["label"]
        g_skip_cnt = g.get("skip_cnt", 0)
        g_non_skip = g["total_cnt"] - g_skip_cnt
        dot_cls = "pass" if g["all_pass"] else ("fail" if g["has_tests"] else "warn")
        skip_label = (
            f'<span style="font-size:12px;color:var(--warn);margin-left:3px;">· {g_skip_cnt}건 건너뜀</span>'
            if g_skip_cnt > 0 else ""
        )
        nav_items += (
            f'<li><button type="button" class="nav-item" id="nav_{lbl}" data-nav="{lbl}">'
            f'<span class="nav-dot {dot_cls}"></span>'
            f'<span class="nav-name" title="{_esc(lbl)}">{_esc(lbl)}</span>'
            f'<span class="nav-count">{g["pass_cnt"]}/{g_non_skip}{skip_label}</span>'
            f'</button></li>\n'
        )

    group_sections = ""
    for g in groups_data:
        group_sections += build_group_section(
            g["label"], g["rows_html"],
            g["pass_cnt"], g["total_cnt"],
            g["all_pass"], g["has_tests"],
            g_skip_cnt=g.get("skip_cnt", 0),
        )

    n_groups = len(groups_data)
    open_first = f"toggleGroup({json.dumps(groups_data[0]["label"])});" if groups_data else ""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="qa-run-id" content="{_esc(run_id)}">
<meta name="qa-run-type" content="{run_type}">
<title>App QA Report</title>
<style>{report_css()}</style>
</head>
<body>
  <aside class="sidebar">
    <div class="sidebar-logo">
      <div class="logo-text">QA App</div>
      <div class="logo-sub">{_esc({"ANDROID Test Report": "Android 테스트 리포트", "IOS Test Report": "iOS 테스트 리포트", "App Test Report": "앱 테스트 리포트"}.get(subtitle, subtitle))}</div>
    </div>
    <nav class="nav-section">
      <div class="nav-label">그룹</div>
      <ul style="list-style:none;">{nav_items}</ul>
    </nav>
  </aside>

<header class="report-header">    <div class="topbar">
      <div>
        <div style="display:flex;align-items:center;gap:8px">
          <h1>테스트 리포트</h1>
          {platform_badge}
          <span class="overall-badge {overall_cls}">{overall_txt}</span>
        </div>
        <div class="meta">{created_at} &middot; {n_groups}개 그룹 &middot; {total}건</div>
      </div>
    </div>
</header>
<div class="layout">
  <div class="main">
    <div class="stats">
      <div class="stat-card"><div class="stat-num" style="color:var(--text);">{total}</div><div class="stat-lbl">전체</div></div>
      <div class="stat-card"><div class="stat-num" style="color:var(--pass);">{pass_total}</div><div class="stat-lbl">통과</div></div>
      <div class="stat-card"><div class="stat-num" style="color:var(--fail);">{fail_total}</div><div class="stat-lbl">실패</div></div>
      <div class="stat-card"><div class="stat-num" style="color:var(--skip);">{skip_total}</div><div class="stat-lbl">건너뜀</div></div>
      <div class="stat-card"><div class="stat-num" style="color:{'var(--pass)' if all_pass else 'var(--fail)'};">{pass_rate}%</div><div class="stat-lbl">통과율</div></div>
    </div>
    {group_sections}
  </div>
</div>
<script>{report_js()}
{open_first}</script>
</body>
</html>"""
