"""
App QA Dashboard 서버.

Usage:
    python agents/dashboard/serve.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT = 8767
HERE = Path(__file__).parent
PROJECT_ROOT = HERE.parent.parent

# appium이 설치된 Python을 찾는다.
# serve.py가 Xcode Python 등 시스템 Python으로 실행될 경우에도
# 서브프로세스는 pyenv Python을 사용해야 한다.
def _find_python_bin() -> str:
    import shutil
    candidates = [
        os.path.expanduser("~/.pyenv/versions/3.12.9/bin/python"),
        os.path.expanduser("~/.pyenv/shims/python3"),
        shutil.which("python3") or "",
        sys.executable,
    ]
    for c in candidates:
        if not c:
            continue
        try:
            r = subprocess.run(
                [c, "-c", "import appium"],
                capture_output=True, timeout=3,
            )
            if r.returncode == 0:
                return c
        except Exception:
            continue
    return sys.executable

PYTHON_BIN = _find_python_bin()


def _find_adb_bin() -> str:
    import shutil
    candidates = [
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
        "/usr/local/bin/adb",
        shutil.which("adb") or "",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return "adb"

ADB_BIN = _find_adb_bin()

STATE_PATH    = PROJECT_ROOT / "state" / "pipeline.json"
REPORTS_DIR   = PROJECT_ROOT / "tests" / "reports"
GENERATED_DIR = PROJECT_ROOT / "tests" / "generated"
SCREENSHOTS_DIR = PROJECT_ROOT / "reports" / "screenshots"
LOGS_DIR      = PROJECT_ROOT / "logs"

for d in (LOGS_DIR, REPORTS_DIR, SCREENSHOTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

ALLOWED_ORIGIN = f"http://localhost:{PORT}"

# ── 동시성 제어 ───────────────────────────────────────────────
_state_lock   = threading.Lock()   # pipeline.json 읽기/쓰기 보호
_process_lock = threading.Lock()   # _running dict 보호
_running: dict[str, subprocess.Popen] = {}  # step → 실행 중인 프로세스


# ── 유틸 ─────────────────────────────────────────────────────

def load_json(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_state(state: dict):
    with _state_lock:
        STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def read_state() -> dict:
    with _state_lock:
        return load_json(STATE_PATH) or {}


def check_appium_status() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:4723/status", timeout=2)
        return True
    except Exception:
        return False


def check_android_devices() -> list:
    try:
        result = subprocess.run(
            [ADB_BIN, "devices"], capture_output=True, text=True, timeout=3
        )
        lines = result.stdout.strip().splitlines()
        return [
            l.split("\t")[0]
            for l in lines[1:]
            if l.strip() and "offline" not in l
        ]
    except Exception:
        return []


def check_ios_simulators() -> list:
    """부팅된 iOS 시뮬레이터 목록 반환."""
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "booted"],
            capture_output=True, text=True, timeout=5
        )
        devices = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("==") and not line.startswith("--"):
                import re
                m = re.match(r"(.+?)\s+\(([0-9A-F-]+)\)\s+\(Booted\)", line)
                if m:
                    devices.append(m.group(1).strip())
        return devices
    except Exception:
        return []


def list_reports() -> list:
    if not REPORTS_DIR.exists():
        return []
    files = list(REPORTS_DIR.glob("report_*.html"))
    seen = set()
    result = []
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


def list_generated() -> list:
    if not GENERATED_DIR.exists():
        return []
    result = []
    for platform_dir in sorted(GENERATED_DIR.iterdir()):
        if not platform_dir.is_dir() or platform_dir.name.startswith("."):
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


def list_screenshots() -> list:
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


def parse_failed_tcs(log_text: str) -> list:
    """pytest 로그에서 실패한 TC 이름과 짧은 에러 메시지를 추출."""
    failures = []
    lines = log_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("FAILED "):
            tc = line.replace("FAILED ", "").split(" - ")[0].strip()
            error = line.split(" - ", 1)[1].strip() if " - " in line else ""
            failures.append({"tc": tc, "error": error})
        # short test summary section
        if "short test summary info" in line:
            for j in range(i + 1, min(i + 100, len(lines))):
                if lines[j].startswith("FAILED"):
                    tc = lines[j].replace("FAILED ", "").split(" - ")[0].strip()
                    error = lines[j].split(" - ", 1)[1].strip() if " - " in lines[j] else ""
                    entry = {"tc": tc, "error": error}
                    if entry not in failures:
                        failures.append(entry)
        i += 1
    # 중복 제거
    seen = set()
    unique = []
    for f in failures:
        key = f["tc"]
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def _read_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    return json.loads(handler.rfile.read(length).decode("utf-8")) if length else {}


# ── 스크립트 맵 ───────────────────────────────────────────────

TESTCASES_DIR = PROJECT_ROOT / "testcases"

SCRIPT_MAP = {
    "analyze":  ("scripts/01_analyze.py",  ["--platform", "{platform}"],                               "run_analyze.txt"),
    "generate": ("scripts/02_generate.py", ["--platform", "{platform}"],                               "run_generate.txt"),
    "lint":     ("scripts/03_lint.py",     [],                                                         "run_lint.txt"),
    "execute":  ("scripts/05_execute.py",  ["--platform", "{platform}"],                               "run_execute.txt"),
    "heal":     ("scripts/06_heal.py",     ["--platform", "{platform}"],                               "run_heal.txt"),
}


def list_tc_folders() -> list[str]:
    """testcases/ 하위 폴더 목록 반환. 빈 폴더는 제외."""
    if not TESTCASES_DIR.exists():
        return []
    return sorted([
        d.name for d in TESTCASES_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".") and list(d.glob("tc_*.md"))
    ])


# ── HTML ──────────────────────────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>App QA Dashboard</title>
<style>
:root {
  --bg:#0d1117; --surface:rgba(30,41,59,.5); --surface2:rgba(30,41,59,.8);
  --border:rgba(255,255,255,.1); --text:#f8fafc; --text2:#94a3b8; --text3:#64748b;
  --pass:#10b981; --fail:#f43f5e; --warn:#f59e0b; --accent:#6366f1;
  --android:#3ddc84; --ios:#007aff; --radius:14px; --radius-sm:9px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,sans-serif;background:var(--bg);color:var(--text);padding:28px 36px}
h1{font-size:21px;font-weight:800}
.subtitle{font-size:12px;color:var(--text3);margin-top:3px;margin-bottom:24px}

/* 상태 바 */
.status-bar{display:flex;align-items:center;gap:18px;flex-wrap:wrap;
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:12px 18px;margin-bottom:20px}
.si{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text2)}
.sdiv{width:1px;height:16px;background:var(--border)}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot.on{background:var(--pass);box-shadow:0 0 6px var(--pass)}
.dot.off{background:var(--fail)}
.step-badge{padding:2px 9px;border-radius:10px;font-size:11px;font-weight:600;
  background:rgba(99,102,241,.15);color:var(--accent);border:1px solid rgba(99,102,241,.3)}

/* 레이아웃 */
.grid{display:grid;grid-template-columns:360px 1fr;gap:18px;align-items:start}

/* 카드 */
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px}
.card-title{font-size:11px;text-transform:uppercase;letter-spacing:.9px;
  color:var(--text3);font-weight:600;margin-bottom:16px}

/* 플랫폼 라디오 */
.platform-radio{display:none}
.platform-selector{display:flex;gap:10px;margin-bottom:18px}
.pl-label{flex:1;display:flex;flex-direction:column;align-items:center;gap:8px;
  padding:16px 10px;border-radius:var(--radius);border:2px solid var(--border);
  cursor:pointer;transition:all .18s;background:rgba(255,255,255,.03)}
.pl-label:hover{border-color:rgba(255,255,255,.25)}
.pl-icon{font-size:28px}
.pl-name{font-size:13px;font-weight:700}
.pl-desc{font-size:10px;color:var(--text3);text-align:center;line-height:1.4}
#radio-android:checked ~ .platform-selector label[for="radio-android"]
  {border-color:var(--android);background:rgba(61,220,132,.08)}
#radio-ios:checked ~ .platform-selector label[for="radio-ios"]
  {border-color:var(--ios);background:rgba(0,122,255,.08)}
.pl-name.android{color:var(--android)}
.pl-name.ios{color:var(--ios)}

/* 파이프라인 스텝 */
.steps{display:flex;flex-direction:column;gap:0}
.step-row{display:flex;align-items:center;gap:8px;position:relative}
.step-connector{width:2px;height:10px;background:var(--border);margin-left:10px}
.step-num{width:20px;height:20px;border-radius:50%;background:rgba(255,255,255,.08);
  display:flex;align-items:center;justify-content:center;
  font-size:10px;font-weight:700;color:var(--text3);flex-shrink:0}
.step-num.running{background:var(--accent);color:#fff;animation:pulse 1s infinite}
.step-num.done{background:var(--pass);color:#fff}
.step-num.failed{background:var(--fail);color:#fff}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}

.btn{flex:1;padding:9px 14px;border-radius:var(--radius-sm);
  border:1px solid var(--border);font-size:12px;font-weight:600;cursor:pointer;
  transition:all .15s;display:flex;align-items:center;justify-content:space-between;
  background:rgba(255,255,255,.04);color:var(--text2)}
.btn:hover:not(:disabled){background:rgba(255,255,255,.08);color:var(--text);border-color:rgba(255,255,255,.2)}
.btn:disabled{opacity:.4;cursor:not-allowed}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover:not(:disabled){opacity:.85}
.btn.heal-btn{background:rgba(245,158,11,.12);border-color:rgba(245,158,11,.4);color:var(--warn)}
.btn.heal-btn:hover:not(:disabled){background:rgba(245,158,11,.2)}
.btn-right{display:flex;align-items:center;gap:6px}
.btn-tag{font-size:10px;font-weight:600;padding:2px 6px;border-radius:6px;
  background:rgba(255,255,255,.1);color:rgba(255,255,255,.5)}
.btn-tip{font-size:10px;color:var(--text3)}

/* 취소 버튼 */
.cancel-btn{width:26px;height:26px;border-radius:6px;border:1px solid rgba(244,63,94,.3);
  background:rgba(244,63,94,.1);color:var(--fail);font-size:14px;cursor:pointer;
  display:none;align-items:center;justify-content:center;flex-shrink:0;transition:all .15s}
.cancel-btn:hover{background:rgba(244,63,94,.25)}
.cancel-btn.visible{display:flex}

/* 스피너 */
@keyframes spin{to{transform:rotate(360deg)}}
.spinner{display:none;width:12px;height:12px;border:2px solid rgba(255,255,255,.2);
  border-top-color:#fff;border-radius:50%;animation:spin .6s linear infinite}
.btn.loading .spinner{display:inline-block}

/* 로그 */
.log-wrap{margin-top:14px}
.log-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:5px}
.log-label{font-size:11px;color:var(--text3)}
.log-clear{font-size:10px;color:var(--text3);cursor:pointer;background:none;border:none;padding:0}
.log-clear:hover{color:var(--text2)}
.log-box{background:#060a0f;border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:10px 12px;font-size:11px;font-family:monospace;color:#7dd3a8;
  max-height:180px;overflow-y:auto;white-space:pre-wrap;line-height:1.6}

/* 실패 요약 */
.fail-summary{margin-top:12px;display:none}
.fail-summary.visible{display:block}
.fail-title{font-size:11px;font-weight:600;color:var(--fail);margin-bottom:6px;
  display:flex;align-items:center;gap:6px}
.fail-item{background:rgba(244,63,94,.08);border:1px solid rgba(244,63,94,.2);
  border-radius:var(--radius-sm);padding:8px 10px;margin-bottom:6px;font-size:11px}
.fail-tc{font-weight:600;color:var(--fail);font-family:monospace;word-break:break-all}
.fail-err{color:var(--text3);margin-top:3px;font-size:10px;font-family:monospace;word-break:break-all}

/* 오른쪽 패널 */
.right-panel{display:flex;flex-direction:column;gap:14px}

/* 탭 */
.tabs{display:flex;gap:4px;margin-bottom:12px}
.tab{padding:5px 12px;border-radius:var(--radius-sm);font-size:11px;font-weight:600;
  cursor:pointer;border:1px solid var(--border);background:transparent;color:var(--text3)}
.tab.active{background:var(--surface2);color:var(--text);border-color:rgba(255,255,255,.2)}
.tab-content{display:none}.tab-content.active{display:block}

/* 생성 파일 */
.gen-item{display:flex;align-items:center;justify-content:space-between;
  padding:7px 0;border-bottom:1px solid var(--border);font-size:12px}
.gen-item:last-child{border-bottom:none}
.gen-badge{font-size:10px;font-weight:600;padding:2px 7px;border-radius:7px;margin-right:6px}
.gen-badge.android{background:rgba(61,220,132,.12);color:var(--android)}
.gen-badge.ios{background:rgba(0,122,255,.12);color:var(--ios)}
.gen-count{color:var(--text3);font-size:11px}

/* 리포트 */
.report-link{display:flex;align-items:center;justify-content:space-between;
  padding:8px 0;border-bottom:1px solid var(--border);text-decoration:none;
  color:var(--text2);font-size:12px;transition:color .15s}
.report-link:last-child{border-bottom:none}
.report-link:hover{color:var(--accent)}

.empty{font-size:12px;color:var(--text3);padding:6px 0}

/* 다음 스텝 하이라이트 */
.btn.suggested{border-color:#f59e0b!important;box-shadow:0 0 0 1px rgba(245,158,11,.4)}
/* TC 폴더 선택 */
.tc-folder-bar{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.tc-folder-bar label{font-size:11px;color:var(--text3);white-space:nowrap}
.tc-folder-select{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);
  color:var(--text);font-size:12px;padding:5px 10px;cursor:pointer;flex:1;min-width:0}
.tc-folder-select:focus{outline:none;border-color:var(--accent)}

/* 컨피그 가이드 */
.guide-tabs{display:flex;gap:4px;margin-bottom:10px}
.guide-tab{padding:5px 12px;border-radius:var(--radius-sm);font-size:11px;font-weight:600;
  cursor:pointer;border:1px solid var(--border);background:transparent;color:var(--text3)}
.guide-tab.active{background:var(--surface2);color:var(--text);border-color:rgba(255,255,255,.2)}
.guide-panel{display:none}.guide-panel.active{display:block}
.guide-desc{font-size:11px;color:var(--text3);margin-bottom:8px;line-height:1.5}
.guide-code{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:12px 14px;font-size:11px;font-family:monospace;color:var(--text2);
  white-space:pre;overflow-x:auto;line-height:1.6;margin:0}
</style>
</head>
<body>

<h1>App QA Dashboard</h1>
<div class="subtitle">Appium 기반 모바일 자동화</div>

<!-- 상태 바 -->
<div class="status-bar">
  <div class="si"><span class="dot" id="dot-appium"></span><span id="txt-appium">확인 중...</span></div>
  <div class="sdiv"></div>
  <div class="si"><span class="dot" id="dot-device"></span><span id="txt-device">확인 중...</span></div>
  <div class="sdiv"></div>
  <div class="si">파이프라인:&nbsp;<span class="step-badge" id="txt-step">-</span></div>
  <div class="sdiv"></div>
  <div class="si" id="heal-row" style="display:none">힐링: <span id="heal-cnt" style="color:var(--warn);font-weight:700;margin-left:3px"></span>회</div>
</div>

<!-- 메인 그리드 -->
<div class="grid">

  <!-- 왼쪽: 플랫폼 + 파이프라인 -->
  <div class="card">
    <div class="card-title">플랫폼 선택 &amp; 파이프라인</div>

    <input type="radio" name="platform" id="radio-android" class="platform-radio" value="android" checked>
    <input type="radio" name="platform" id="radio-ios"     class="platform-radio" value="ios">

    <!-- 진행률 인디케이터 -->
    <div id="progress-bar" style="display:flex;align-items:center;gap:0;margin-bottom:14px;padding:0 4px">
      <!-- JS로 동적 렌더링 -->
    </div>

    <div class="platform-selector">
      <label for="radio-android" class="pl-label">
        <span class="pl-icon">🤖</span>
        <span class="pl-name android">Android</span>
        <span class="pl-desc">UiAutomator2<br>에뮬레이터 · 실기기</span>
      </label>
      <label for="radio-ios" class="pl-label">
        <span class="pl-icon">🍎</span>
        <span class="pl-name ios">iOS</span>
        <span class="pl-desc">XCUITest<br>Simulator · 실기기</span>
      </label>
    </div>

    <!-- TC 폴더 선택 -->
    <div class="tc-folder-bar">
      <label for="tc-folder-select">TC 폴더</label>
      <select id="tc-folder-select" class="tc-folder-select">
        <option value="">(최상위 testcases/)</option>
      </select>
    </div>

    <!-- 전체 실행 버튼 -->
    <button class="btn primary" id="btn-run-all" onclick="runAll()" style="width:100%;margin-bottom:14px;justify-content:center;gap:8px;font-size:13px">
      <span>▶ 전체 실행</span>
      <span style="font-size:10px;opacity:.7">analyze → generate → lint → execute</span>
      <div class="spinner"></div>
    </button>

    <!-- 파이프라인 버튼 -->
    <div class="steps">

      <div class="step-row">
        <div class="step-num" id="sn-analyze">1</div>
        <button class="btn" id="btn-analyze" onclick="runStep('analyze')">
          <span>UI 분석 <span style="color:var(--text3);font-size:10px">01_analyze</span></span>
          <div class="btn-right">
            <span class="btn-tip">page_source</span>
            <div class="spinner"></div>
          </div>
        </button>
        <button class="cancel-btn" id="cancel-analyze" title="실행 취소" onclick="cancelStep('analyze')">✕</button>
      </div>
      <div class="step-connector"></div>

      <div class="step-row">
        <div class="step-num" id="sn-generate">2</div>
        <button class="btn" id="btn-generate" onclick="runStep('generate')">
          <span>코드 생성 <span style="color:var(--text3);font-size:10px">02_generate</span></span>
          <div class="btn-right">
            <span class="btn-tip">TC scaffold</span>
            <div class="spinner"></div>
          </div>
        </button>
        <button class="cancel-btn" id="cancel-generate" onclick="cancelStep('generate')">✕</button>
      </div>
      <div class="step-connector"></div>

      <div class="step-row">
        <div class="step-num" id="sn-lint">3</div>
        <button class="btn" id="btn-lint" onclick="runStep('lint')">
          <span>린트 검사 <span style="color:var(--text3);font-size:10px">03_lint</span></span>
          <div class="btn-right">
            <span class="btn-tip">flake8</span>
            <div class="spinner"></div>
          </div>
        </button>
        <button class="cancel-btn" id="cancel-lint" onclick="cancelStep('lint')">✕</button>
      </div>
      <div class="step-connector"></div>

      <div class="step-row">
        <div class="step-num" id="sn-execute">4</div>
        <button class="btn primary" id="btn-execute" onclick="runStep('execute')">
          <span>테스트 실행 <span style="color:rgba(255,255,255,.5);font-size:10px">05_execute</span></span>
          <div class="btn-right">
            <span class="btn-tag">pytest</span>
            <div class="spinner"></div>
          </div>
        </button>
        <button class="cancel-btn" id="cancel-execute" onclick="cancelStep('execute')">✕</button>
      </div>
      <div class="step-connector"></div>

      <div class="step-row">
        <div class="step-num" id="sn-heal">5</div>
        <button class="btn heal-btn" id="btn-heal" onclick="runStep('heal')">
          <span>힐링 <span style="color:rgba(245,158,11,.5);font-size:10px">06_heal</span></span>
          <div class="btn-right">
            <span class="btn-tip" style="color:var(--warn)">실패 시 자동 패치</span>
            <div class="spinner"></div>
          </div>
        </button>
        <button class="cancel-btn" id="cancel-heal" onclick="cancelStep('heal')">✕</button>
      </div>

    </div>

    <!-- 결과 요약 -->
    <div id="step-summary" style="display:none;margin-top:12px;padding:8px 12px;
      border-radius:9px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);
      font-size:11px;color:#94a3b8;font-family:monospace"></div>
    <!-- 다음 액션 가이드 배너 -->
    <div id="guide-banner" style="display:none;margin-top:10px;padding:10px 14px;
      border-radius:9px;font-size:12px;font-weight:600;position:relative"></div>

    <!-- 로그 -->
    <div class="log-wrap">
      <div class="log-header">
        <span class="log-label">실행 로그</span>
        <div style="display:flex;gap:6px;align-items:center">
          <button id="log-toggle" class="log-clear" onclick="toggleLog()">확장</button>
          <button class="log-clear" onclick="clearLog()">지우기</button>
        </div>
      </div>
      <div class="log-box" id="log-box" style="transition:max-height 0.2s">대기 중...</div>
    </div>

    <!-- 실패 TC 요약 -->
    <div class="fail-summary" id="fail-summary">
      <div class="fail-title">
        <span>⚠</span><span id="fail-count"></span>개 실패
      </div>
      <div id="fail-list"></div>
    </div>
  </div>

  <!-- 오른쪽 패널 -->
  <div class="right-panel">

    <!-- 생성된 파일 -->
    <div class="card">
      <div class="card-title">생성된 테스트 파일</div>
      <div class="tabs">
        <button class="tab active" onclick="switchTab('gen','all',this)">전체</button>
        <button class="tab" onclick="switchTab('gen','android',this)">Android</button>
        <button class="tab" onclick="switchTab('gen','ios',this)">iOS</button>
      </div>
      <div id="gen-all"  class="tab-content active"><div class="empty">없음</div></div>
      <div id="gen-android" class="tab-content"><div class="empty">없음</div></div>
      <div id="gen-ios"     class="tab-content"><div class="empty">없음</div></div>
    </div>

    <!-- 리포트 -->
    <div class="card">
      <div class="card-title">최근 리포트</div>
      <div id="report-list"><div class="empty">없음</div></div>
    </div>

    <!-- 컨피그 작성 가이드 -->
    <div class="card">
      <div class="card-title">컨피그 작성 가이드</div>
      <div class="guide-tabs">
        <button class="guide-tab active" onclick="switchGuide('screens',this)">screens.json</button>
        <button class="guide-tab" onclick="switchGuide('test_data',this)">test_data.json</button>
        <button class="guide-tab" onclick="switchGuide('devices',this)">devices.json</button>
      </div>

      <div id="guide-screens" class="guide-panel active">
        <div class="guide-desc">화면 정의 파일. 분석 단계에서 어떤 화면을 탐색할지 지정합니다.</div>
        <pre class="guide-code">{
  "screen_key": {
    "description": "화면 설명",
    "actions": [
      {"type": "tap",        "target": "element-id-or-text"},
      {"type": "input_text", "target": "field-id", "value_key": "account.id"}
    ],
    "platform": ["android", "ios"]
  }
}

/* actions 타입 */
// "tap"        — 요소 탭
// "input_text" — 텍스트 입력 (value_key: test_data.json 경로)
// actions: []  — 앱 초기 화면 그대로 (탐색 불필요)

/* platform 값 */
// ["android", "ios"] — 양 플랫폼
// ["android"]        — Android 전용
// ["ios"]            — iOS 전용</pre>
      </div>

      <div id="guide-test_data" class="guide-panel">
        <div class="guide-desc">앱 식별자 및 테스트 입력값. 플랫폼별로 작성합니다.</div>
        <pre class="guide-code">{
  "app": {
    "android": {
      "package":  "com.example.app",
      "activity": "com.example.app.MainActivity",
      "app_path": ""
    },
    "ios": {
      "bundle_id": "com.example.app",
      "app_path":  ""
    }
  }
}

/* app_path */
// 비워두면 이미 설치된 앱 사용
// 절대경로 지정 시 해당 .apk / .ipa 설치 후 실행

/* 테스트 입력값 추가 예시 */
// screens.json action의 value_key로 참조됨
// "account": { "id": "user@example.com", "password": "pass" }
// → value_key: "account.id"  또는  "account.password"</pre>
      </div>

      <div id="guide-devices" class="guide-panel">
        <div class="guide-desc">Appium Capabilities 설정. 에뮬레이터/실기기별로 작성합니다.</div>
        <pre class="guide-code">{
  "android": {
    "emulator": {
      "deviceName":        "Android Emulator",
      "platformVersion":   "14.0",
      "automationName":    "UiAutomator2",
      "avd":               "avd_name",
      "noReset":           true,
      "forceAppLaunch":    true,
      "shouldTerminateApp": true
    },
    "real_device": {
      "deviceName":      "Galaxy S24",
      "platformVersion": "14.0",
      "automationName":  "UiAutomator2",
      "udid":            ""
    }
  },
  "ios": {
    "simulator": {
      "deviceName":      "iPhone 16",
      "platformVersion": "18.5",
      "automationName":  "XCUITest",
      "udid":            "simulator-udid"
    },
    "real_device": {
      "deviceName":      "iPhone 16",
      "platformVersion": "18.5",
      "automationName":  "XCUITest",
      "udid":            ""
    }
  }
}

/* udid 확인 */
// Android emulator: emulator -list-avds
// Android 연결기기:  adb devices
// iOS Simulator:    xcrun simctl list devices booted
// iOS 실기기:        idevice_id -l</pre>
      </div>
    </div>

  </div>
</div>

<script>
// ── 상태 ────────────────────────────────────────────────────
var _pollTimer = null;
var _currentLog = 'run_execute.txt';
var _currentStep = null;
var _initialPlatformSync = true;  // Fix 4: 최초 로드 시 한 번만 플랫폼 동기화
var _logExpanded = false;
var _stepStartTime = null;
function _analyzeFailMsg(){
  return getPlatform() === 'ios'
    ? 'Appium 연결 또는 iOS Simulator 상태를 확인하세요. (xcrun simctl list devices booted) 재실행 권장.'
    : 'Appium 연결 또는 Android 디바이스 상태를 확인하세요. (adb devices) 재실행 권장.';
}
var _guideMessages = {
  analyze:  {ok:"다음: 코드 생성 (2단계)을 실행하세요.",  fail:null},
  generate: {ok:"다음: 린트 검사 (3단계)를 실행하세요.",  fail:"TC 마크다운 또는 screens.json 설정을 확인하세요."},
  lint:     {ok:"다음: 테스트 실행 (4단계)을 실행하세요.", fail:"생성된 코드에 문법 오류. 수정 후 lint 재실행 or heal 실행."},
  execute:  {ok:"다음: 완료. 리포트를 확인하세요.",        fail:"테스트 실패 발생. 아래 실패 목록 확인. heal 실행으로 자동 패치 시도 가능."},
  heal:     {ok:"파이프라인 완료! 리포트를 확인하세요.",   fail:"자동 패치 실패. 수동 수정 필요."}
};
var _nextStep = {
  analyze:'generate', generate:'lint', lint:'execute', execute:null, heal:null
};
// 소프트 순서 강제: 이 단계가 done이어야 다음 단계가 활성화
var _prereq = {
  analyze: null, generate:'analyze', lint:'generate', execute:'lint', heal:'execute'
};
var STEP_ORDER = ['analyze','generate','lint','execute','heal'];
var STEP_LABEL = {analyze:'분석',generate:'생성',lint:'린트',execute:'실행',heal:'힐링'};
var _stepState = {analyze:'idle',generate:'idle',lint:'idle',execute:'idle',heal:'idle'};

function getPlatform(){
  return document.querySelector('input[name="platform"]:checked').value;
}

function getTcFolder(){
  var sel = document.getElementById('tc-folder-select');
  return sel ? sel.value : '';
}

function updateStepLocks(){
  STEP_ORDER.forEach(function(step){
    var btn = document.getElementById('btn-'+step);
    if(!btn || btn.classList.contains('loading')) return;
    var pre = _prereq[step];
    var locked = pre && _stepState[pre] !== 'done';
    btn.disabled = locked;
    btn.title = locked ? ('이전 단계(' + STEP_LABEL[pre] + ')를 먼저 완료하세요') : '';
    btn.style.opacity = locked ? '0.45' : '';
  });
}

function toggleLog(){
  _logExpanded = !_logExpanded;
  var box = document.getElementById('log-box');
  box.style.maxHeight = _logExpanded ? '500px' : '180px';
  document.getElementById('log-toggle').textContent = _logExpanded ? '축소' : '확장';
}

function renderProgressBar(){
  var bar = document.getElementById('progress-bar');
  if(!bar) return;
  var doneCount = STEP_ORDER.filter(function(s){ return _stepState[s]==='done'; }).length;
  var html = '';
  STEP_ORDER.forEach(function(s, i){
    var st = _stepState[s];
    var color = {done:'#10b981',failed:'#f43f5e',running:'#6366f1',idle:'rgba(255,255,255,.15)',skipped:'rgba(255,255,255,.08)'}[st]||'rgba(255,255,255,.15)';
    var border = st==='skipped' ? '1px dashed rgba(255,255,255,.2)' : 'none';
    var anim = st==='running' ? 'animation:pulse 1s infinite' : '';
    html += '<div style="display:flex;flex-direction:column;align-items:center;flex:1;gap:3px">'
      + '<div style="width:16px;height:16px;border-radius:50%;background:'+color+';border:'+border+';'+anim+';flex-shrink:0"></div>'
      + '<span style="font-size:9px;color:rgba(255,255,255,.3)">'+STEP_LABEL[s]+'</span>'
      + '</div>';
    if(i < STEP_ORDER.length - 1){
      var lineColor = (_stepState[STEP_ORDER[i]]==='done') ? '#10b981' : 'rgba(255,255,255,.1)';
      html += '<div style="flex:1;height:2px;background:'+lineColor+';margin-bottom:14px;margin-top:7px"></div>';
    }
  });
  html += '<span style="font-size:10px;color:#64748b;margin-left:8px;white-space:nowrap">'+doneCount+'/5</span>';
  bar.innerHTML = html;
}

function setStepState(step, state){
  if(_stepState[step] !== undefined) _stepState[step] = state;
  renderProgressBar();
  updateStepLocks();
}

function setLog(text){
  var b=document.getElementById('log-box');
  b.textContent=text;
  b.scrollTop=b.scrollHeight;
}
function clearLog(){
  document.getElementById('log-box').textContent='';
  hideFails();
}

// ── 스텝 숫자 상태 ──────────────────────────────────────────
function setStepNum(step, state){
  var el=document.getElementById('sn-'+step);
  if(!el) return;
  el.className='step-num '+(state||'');
  // 진행률 인디케이터 동기화
  var pState = {running:'running', done:'done', failed:'failed', '':'idle'}[state||''] || 'idle';
  setStepState(step, pState);
}

// ── 실행 / 취소 ─────────────────────────────────────────────
var _runAllSteps = ['analyze','generate','lint','execute','heal'];
var _runAllActive = false;

async function runAll(){
  if(_runAllActive) return;
  _runAllActive = true;
  var btn = document.getElementById('btn-run-all');
  btn.classList.add('loading');
  btn.disabled = true;
  hideGuideBanner();
  hideFails();
  clearLog();

  // 모든 스텝을 running 표시로 초기화
  _runAllSteps.forEach(function(s){ setStepState(s, 'idle'); });

  var platform = getPlatform();
  var tcFolder = getTcFolder();

  try {
    var res = await fetch('/api/run_all', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({platform: platform, tc_folder: tcFolder})
    });
    var data = await res.json();
    if(!data.ok){
      setLog('[오류] ' + (data.error || '알 수 없는 오류'));
      _finishRunAll(false); return;
    }
  } catch(e){
    setLog('[요청 실패] ' + e.message);
    _finishRunAll(false); return;
  }

  // execute까지 순서대로 폴링, 이후 heal은 로그 감지로 처리
  _pollRunAllStep(0, platform);
}

function _isHealLogActive(healRound){
  // run_heal_1.txt ~ run_heal_3.txt 존재 여부로 heal 활성 감지
  return fetch('/api/run_log', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({log: 'run_heal_' + healRound + '.txt'})})
    .then(function(r){ return r.json(); })
    .then(function(d){ return d.ok && d.log.length > 0; })
    .catch(function(){ return false; });
}

function _pollRunAllStep(idx, platform){
  var MAIN_STEPS = ['analyze','generate','lint','execute'];
  if(idx >= MAIN_STEPS.length){
    // execute 완료 후 — state에서 실패 여부 즉시 확인
    _checkNeedHeal(function(needHeal){
      if(needHeal){ _pollHealRounds(1); }
      else { _finishRunAll(true); }
    });
    return;
  }
  var step = MAIN_STEPS[idx];
  var logFiles = {analyze:'run_analyze.txt', generate:'run_generate.txt', lint:'run_lint.txt', execute:'run_execute.txt'};
  _currentLog = logFiles[step];
  _currentStep = step;
  setStepNum(step, 'running');
  setLog('[전체실행] ' + (idx+1) + '/' + MAIN_STEPS.length + ' — ' + step + ' 실행 중...\n');

  var prevLen = 0;
  var timer = setInterval(async function(){
    try {
      var r = await fetch('/api/run_log', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({log: logFiles[step]})});
      var d = await r.json();
      if(d.ok && d.log.length !== prevLen){ setLog(d.log); prevLen = d.log.length; }
      if(d.done){
        clearInterval(timer);
        var ok = d.exit_code === 0;
        setStepNum(step, ok ? 'done' : 'failed');
        if(!ok){
          showGuideBanner(step, false);
          _finishRunAll(false);
        } else {
          _pollRunAllStep(idx+1, platform);
        }
      }
    } catch(_){}
  }, 1200);
}

function _checkNeedHeal(cb){
  fetch('/api/state').then(function(r){ return r.json(); }).then(function(st){
    var failed = (((st.execute_results||{}).summary)||{}).failed || 0;
    cb(failed > 0);
  }).catch(function(){ cb(false); });
}

function _pollHealRounds(round){
  if(round > 3){ _finishRunAll(true); return; }
  // heal 로그 파일이 생겼는지 최대 8초 대기 (서버가 즉시 heal 없이 끝났을 수도 있음)
  var waited = 0;
  var checkTimer = setInterval(async function(){
    waited += 1000;
    var healLog = 'run_heal_' + round + '.txt';
    try {
      var r = await fetch('/api/run_log', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({log: healLog})});
      var d = await r.json();
      if(d.ok && d.log.length > 0){
        clearInterval(checkTimer);
        setStepNum('heal', 'running');
        setLog('[힐링 ' + round + '/3] 실행 중...\n');
        _pollSingleLog(healLog, 'heal', function(ok){
          if(!ok){ _finishRunAll(false); return; }
          // heal 후 execute 재실행 결과 확인
          var exLog = 'run_execute_' + round + '.txt';
          _pollSingleLog(exLog, 'execute', function(exOk){
            if(exOk){ _finishRunAll(true); }
            else { _pollHealRounds(round + 1); }
          });
        });
      } else if(waited >= 8000){
        // 8초 내 heal이 시작 안 됐으면 서버가 이미 완료한 것으로 간주
        clearInterval(checkTimer);
        _finishRunAll(true);
      }
    } catch(_){}
  }, 1000);
}

function _pollSingleLog(logName, step, onDone){
  var prevLen = 0;
  var timer = setInterval(async function(){
    try {
      var r = await fetch('/api/run_log', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({log: logName})});
      var d = await r.json();
      if(d.ok && d.log.length !== prevLen){ setLog(d.log); prevLen = d.log.length; }
      if(d.done){
        clearInterval(timer);
        setStepNum(step, d.exit_code === 0 ? 'done' : 'failed');
        onDone(d.exit_code === 0);
      }
    } catch(_){}
  }, 1200);
}

function _finishRunAll(success){
  _runAllActive = false;
  var btn = document.getElementById('btn-run-all');
  btn.classList.remove('loading');
  btn.disabled = false;
  _currentStep = null;
  refreshStatus(); refreshGenerated(); refreshReports();
  if(success) showGuideBanner('execute', true);
}

async function runStep(step){
  _stepStartTime = Date.now();
  hideGuideBanner();
  var platform = getPlatform();
  var btnId = 'btn-'+step;
  var cancelId = 'cancel-'+step;
  var logFiles = {
    analyze:'run_analyze.txt', generate:'run_generate.txt',
    lint:'run_lint.txt', execute:'run_execute.txt', heal:'run_heal.txt'
  };
  _currentLog = logFiles[step];
  _currentStep = step;

  // UI 업데이트
  var btn = document.getElementById(btnId);
  btn.classList.add('loading');
  btn.disabled = true;
  document.getElementById(cancelId).classList.add('visible');
  setStepNum(step,'running');
  setLog('['+step+'] 플랫폼: '+platform+' — 실행 중...\n');
  hideFails();

  try {
    var tcFolder = getTcFolder();
    var res = await fetch('/api/run',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({step, platform, tc_folder: tcFolder})
    });
    var data = await res.json();
    if(!data.ok){
      setLog('[오류] '+(data.error||'알 수 없는 오류'));
      finishStep(step, false);
      return;
    }
    setLog('['+step+'] PID: '+data.pid+'\n');
    startLogPoll(step, _currentLog);
  } catch(e){
    setLog('[요청 실패] '+e.message);
    finishStep(step, false);
  }
}

async function cancelStep(step){
  await fetch('/api/cancel',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({step})
  });
  finishStep(step, false);
  setLog('[취소됨] '+step+' 실행이 중단됐어요.');
}

function finishStep(step, success){
  var btn=document.getElementById('btn-'+step);
  btn.classList.remove('loading');
  document.getElementById('cancel-'+step).classList.remove('visible');
  setStepNum(step, success===true?'done': success===false?'failed':'');
  if(_pollTimer){ clearInterval(_pollTimer); _pollTimer=null; }
  // Fix 5: 스텝 완료 시 _currentStep 초기화 → 이후 refreshStatus가 플랫폼 동기화 재개
  _currentStep = null;
  refreshStatus();
  refreshGenerated();
  refreshReports();

  // 소요 시간
  var elapsed = _stepStartTime ? Math.round((Date.now() - _stepStartTime) / 1000) : 0;
  // 결과 요약
  var summary = document.getElementById('step-summary');
  var summaryText = '[' + step + '] 소요 ' + elapsed + 's';
  if(step === 'execute' || step === 'heal'){
    var logText = document.getElementById('log-box').textContent;
    var passMatch = logText.match(/(\d+) passed/);
    var failMatch = logText.match(/(\d+) failed/);
    if(passMatch || failMatch){
      summaryText += ' | 통과: ' + (passMatch?passMatch[1]:'0') + ' | 실패: ' + (failMatch?failMatch[1]:'0');
    }
  }
  if(step === 'generate'){
    var logText = document.getElementById('log-box').textContent;
    var genMatch = logText.match(/(\d+)개/);
    if(genMatch) summaryText += ' | 생성: ' + genMatch[1] + '개';
  }
  summary.textContent = summaryText;
  summary.style.display = 'block';

  // 가이드 배너
  showGuideBanner(step, success === true);

  // suggested 버튼 하이라이트
  document.querySelectorAll('.btn.suggested').forEach(function(b){ b.classList.remove('suggested'); });
  if(success === true && _nextStep[step]){
    var nextBtn = document.getElementById('btn-' + _nextStep[step]);
    if(nextBtn && !nextBtn.disabled) nextBtn.classList.add('suggested');
  }
}

// ── 로그 폴링 ────────────────────────────────────────────────
function startLogPoll(step, logFile){
  if(_pollTimer) clearInterval(_pollTimer);
  var prevLen=0;
  _pollTimer = setInterval(async ()=>{
    try{
      var res=await fetch('/api/run_log',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({log:logFile})
      });
      var data=await res.json();
      if(data.ok && data.log.length!==prevLen){
        setLog(data.log);
        prevLen=data.log.length;
        // 실패 파싱
        if(step==='execute'||step==='heal'){
          updateFailSummary(data.log);
        }
      }
      if(data.done){
        clearInterval(_pollTimer);
        _pollTimer=null;
        finishStep(step, data.exit_code===0);
      }
    }catch(_){}
  }, 1200);
  // 최대 10분 타임아웃
  setTimeout(()=>{ if(_pollTimer){ clearInterval(_pollTimer); _pollTimer=null; finishStep(step,false); }}, 600000);
}

// ── 실패 요약 ────────────────────────────────────────────────
function updateFailSummary(logText){
  var lines=logText.split('\n');
  var fails=[];
  var inSummary=false;
  lines.forEach(function(l){
    if(l.includes('short test summary info')) inSummary=true;
    if(inSummary && l.startsWith('FAILED')){
      var parts=l.replace('FAILED ','').split(' - ');
      fails.push({tc:parts[0]||'', error:parts[1]||''});
    }
    // inline FAILED lines
    if(!inSummary && l.startsWith('FAILED ')){
      var parts=l.replace('FAILED ','').split(' - ');
      var entry={tc:parts[0]||'', error:parts[1]||''};
      if(!fails.some(function(f){return f.tc===entry.tc;})) fails.push(entry);
    }
  });
  if(!fails.length){ hideFails(); return; }
  var panel=document.getElementById('fail-summary');
  var list=document.getElementById('fail-list');
  document.getElementById('fail-count').textContent=fails.length;
  list.innerHTML=fails.map(function(f){
    return '<div class="fail-item"><div class="fail-tc">'+esc(f.tc)+'</div>'
      +(f.error?'<div class="fail-err">'+esc(f.error)+'</div>':'')+'</div>';
  }).join('');
  panel.classList.add('visible');
}
function hideFails(){
  document.getElementById('fail-summary').classList.remove('visible');
  document.getElementById('fail-list').innerHTML='';
}
function esc(s){ var d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

function showGuideBanner(step, success){
  var banner = document.getElementById('guide-banner');
  var msgVal = (_guideMessages[step]||{})[success?'ok':'fail'];
  var msg = (msgVal === null && step === 'analyze' && !success) ? _analyzeFailMsg() : (msgVal || '');
  if(!msg){ banner.style.display='none'; return; }
  banner.style.background = success ? 'rgba(16,185,129,.12)' : 'rgba(244,63,94,.12)';
  banner.style.border = '1px solid ' + (success ? 'rgba(16,185,129,.35)' : 'rgba(244,63,94,.35)');
  banner.style.color = success ? '#10b981' : '#f43f5e';
  banner.innerHTML = msg + '<button onclick="hideGuideBanner()" style="position:absolute;right:10px;top:50%;transform:translateY(-50%);background:none;border:none;color:inherit;cursor:pointer;font-size:14px;opacity:.7">&#x2715;</button>';
  banner.style.display = 'block';
}
function hideGuideBanner(){
  document.getElementById('guide-banner').style.display='none';
}

// ── 탭 ──────────────────────────────────────────────────────
function switchTab(group, key, el){
  var prefix = group+'-';
  document.querySelectorAll('[id^="'+prefix+'"]').forEach(function(c){c.classList.remove('active');});
  document.getElementById(prefix+key).classList.add('active');
  el.closest('.card').querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});
  el.classList.add('active');
}

function switchGuide(key, el){
  document.querySelectorAll('.guide-panel').forEach(function(p){p.classList.remove('active');});
  document.getElementById('guide-'+key).classList.add('active');
  el.closest('.card').querySelectorAll('.guide-tab').forEach(function(t){t.classList.remove('active');});
  el.classList.add('active');
}


// ── API 새로고침 ─────────────────────────────────────────────
async function refreshStatus(){
  try{
    var platform = getPlatform();
    var [sr,stR]=await Promise.all([
      fetch('/api/status?platform=' + platform),
      fetch('/api/state')
    ]);
    var st=await sr.json(), state=await stR.json();

    var dA=document.getElementById('dot-appium'), tA=document.getElementById('txt-appium');
    dA.className='dot '+(st.appium?'on':'off');
    tA.textContent=st.appium?'Appium 연결됨':'Appium 미기동';

    var dD=document.getElementById('dot-device'), tD=document.getElementById('txt-device');
    var isIos = (platform === 'ios');
    var noDevTxt = isIos ? 'Simulator 없음 (xcrun simctl boot)' : '디바이스 없음 (adb devices)';
    if(st.device_count>0){ dD.className='dot on'; tD.textContent=st.devices.join(', '); }
    else{ dD.className='dot off'; tD.textContent=noDevTxt; }

    document.getElementById('txt-step').textContent=state.step||'init';

    var hc=state.heal_count||0;
    var hr=document.getElementById('heal-row');
    if(hc>0){ hr.style.display='flex'; document.getElementById('heal-cnt').textContent=hc; }

    // 최초 로드 시 pipeline.json 플랫폼으로 라디오 동기화
    if(state.platform && _initialPlatformSync){
      var r=document.getElementById('radio-'+state.platform);
      if(r) r.checked=true;
      _initialPlatformSync = false;
    }
  }catch(_){}
}

// 라디오 버튼 변경 시 즉시 상태 갱신
document.addEventListener('change', function(e){
  if(e.target && e.target.name === 'platform'){
    refreshStatus();
  }
});

async function refreshGenerated(){
  try{
    var res=await fetch('/api/generated'); var data=await res.json();
    var allHtml='', andHtml='', iosHtml='';
    data.forEach(function(g){
      var badge='<span class="gen-badge '+g.platform+'">'+(g.platform==='android'?'🤖':'🍎')+' '+g.platform+'</span>';
      var snippet=g.files.slice(0,3).join(', ')+(g.files.length>3?' 외 '+(g.files.length-3)+'개':'');
      var row='<div class="gen-item"><div>'+badge+snippet+'</div><span class="gen-count">'+g.count+'개</span></div>';
      allHtml+=row;
      if(g.platform==='android') andHtml+=row;
      if(g.platform==='ios') iosHtml+=row;
    });
    document.getElementById('gen-all').innerHTML=allHtml||'<div class="empty">없음</div>';
    document.getElementById('gen-android').innerHTML=andHtml||'<div class="empty">없음</div>';
    document.getElementById('gen-ios').innerHTML=iosHtml||'<div class="empty">없음</div>';
  }catch(_){}
}

async function refreshReports(){
  try{
    var res=await fetch('/api/reports'); var data=await res.json();
    document.getElementById('report-list').innerHTML=
      data.slice(0,8).map(function(r){
        return '<a href="/reports/'+r.name+'" target="_blank" class="report-link">'
          +'<span>'+r.name+'</span><span>↗</span></a>';
      }).join('')||'<div class="empty">없음</div>';
  }catch(_){}
}

// ── TC 폴더 목록 ─────────────────────────────────────────────
async function refreshTcFolders(){
  try{
    var res = await fetch('/api/tc-folders');
    var data = await res.json();
    var sel = document.getElementById('tc-folder-select');
    if(!sel) return;
    var cur = sel.value;
    sel.innerHTML = '<option value="">(최상위 testcases/)</option>';
    (data.folders||[]).forEach(function(f){
      var opt = document.createElement('option');
      opt.value = f; opt.textContent = f + '/';
      if(f === cur) opt.selected = true;
      sel.appendChild(opt);
    });
  }catch(_){}
}

// ── 초기화 ───────────────────────────────────────────────────
(async function init(){
  renderProgressBar();
  updateStepLocks();
  await Promise.all([refreshStatus(),refreshGenerated(),refreshReports(),refreshTcFolders()]);
  setInterval(refreshStatus, 6000);
  setInterval(refreshGenerated, 10000);
  setInterval(refreshReports, 15000);
  setInterval(refreshTcFolders, 15000);
})();
</script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        path = self.path.split("?")[0]

        if path in ("/", "/index.html"):
            self._serve_str(DASHBOARD_HTML, "text/html; charset=utf-8")
            return

        routes = {
            "/api/state":       self._get_state,
            "/api/status":      self._get_status,
            "/api/reports":     self._get_reports,
            "/api/generated":   self._get_generated,
            "/api/screenshots": self._get_screenshots,
            "/api/tc-folders":  self._get_tc_folders,
        }
        if path in routes:
            routes[path]()
            return

        if path.startswith("/reports/"):
            self._serve_file_from(REPORTS_DIR, path[len("/reports/"):], "text/html; charset=utf-8")
            return

        if path.startswith("/screenshots/"):
            name = path[len("/screenshots/"):]
            fpath = SCREENSHOTS_DIR / name
            ext = fpath.suffix.lower()
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext.lstrip("."), "image/png")
            self._serve_file_from(SCREENSHOTS_DIR, name, mime)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        path = self.path.split("?")[0]
        routes = {
            "/api/run":        self._post_run,
            "/api/run_all":    self._post_run_all,
            "/api/cancel":     self._post_cancel,
            "/api/run_log":    self._post_run_log,
            "/api/reset":      self._post_reset,
        }
        if path in routes:
            try:
                routes[path]()
            except Exception as e:
                self._serve_json({"ok": False, "error": str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    # ── GET handlers ─────────────────────────────────────────────

    def _get_state(self):
        self._serve_json(read_state())

    def _get_status(self):
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        appium_ok = check_appium_status()
        state = read_state()
        # UI에서 선택한 플랫폼을 쿼리 파라미터로 받으면 우선 적용
        platform = (qs.get("platform") or [None])[0] or state.get("platform", "android")
        if platform == "ios":
            devices = check_ios_simulators()
        else:
            devices = check_android_devices()
        with _process_lock:
            running_steps = [s for s, p in _running.items() if p.poll() is None]
        self._serve_json({
            "appium": appium_ok,
            "devices": devices,
            "device_count": len(devices),
            "running_steps": running_steps,
            "platform": platform,
        })

    def _get_reports(self):
        self._serve_json(list_reports())

    def _get_generated(self):
        self._serve_json(list_generated())

    def _get_screenshots(self):
        self._serve_json(list_screenshots())

    def _get_tc_folders(self):
        self._serve_json({"folders": list_tc_folders()})

    def _serve_file_from(self, base_dir: Path, name: str, content_type: str):
        if ".." in name:
            self.send_response(403); self.end_headers(); return
        fpath = base_dir / name
        if not fpath.exists():
            self.send_response(404); self.end_headers(); return
        content = fpath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-XSS-Protection", "0")
        self.end_headers()
        self.wfile.write(content)

    # ── POST handlers ─────────────────────────────────────────────

    def _post_run(self):
        body = _read_body(self)
        platform = body.get("platform", "android")
        step = body.get("step", "execute")
        tc_folder = body.get("tc_folder", "").strip()

        if platform not in ("android", "ios"):
            self._serve_json({"ok": False, "error": "invalid platform"}); return
        if step not in SCRIPT_MAP:
            self._serve_json({"ok": False, "error": "invalid step"}); return
        if tc_folder and (".." in tc_folder or "/" in tc_folder):
            self._serve_json({"ok": False, "error": "invalid tc_folder"}); return

        # 이미 같은 스텝 실행 중이면 거부
        with _process_lock:
            if step in _running and _running[step].poll() is None:
                self._serve_json({"ok": False, "error": f"{step} 이미 실행 중입니다"}); return

        # pipeline.json에 플랫폼 저장
        state = read_state()
        state["platform"] = platform
        save_state(state)

        script_rel, extra_args_tmpl, log_name = SCRIPT_MAP[step]
        extra_args = [a.replace("{platform}", platform) for a in extra_args_tmpl]
        # iOS analyze는 simulator 모드로 실행 (05_execute는 --mode 인수 없음)
        if step == "analyze" and platform == "ios":
            extra_args += ["--mode", "simulator"]
        if step in ("generate", "execute") and tc_folder:
            extra_args += ["--tc-dir", tc_folder]
        script = PROJECT_ROOT / script_rel

        if not script.exists():
            self._serve_json({"ok": False, "error": f"{script_rel} 없음 (미구현)"}); return

        log_path = LOGS_DIR / log_name
        # Fix 1: 새 세션 그룹 생성 → os.killpg가 서버 자체를 종료하지 않도록
        extra_popen: dict = {}
        if sys.platform != "win32":
            extra_popen["preexec_fn"] = os.setsid
        # Fix 3: with 블록으로 Popen 예외 시 파일 핸들 누수 방지
        with open(log_path, "w", encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                [PYTHON_BIN, "-u", str(script)] + extra_args,
                cwd=str(PROJECT_ROOT),
                stdout=log_file, stderr=subprocess.STDOUT,
                **extra_popen,
            )

        with _process_lock:
            _running[step] = proc

        # Fix 2: _running에서 삭제하지 않음 → exit_code를 poll()로 계속 읽을 수 있음
        # (6개 스텝 한정이므로 메모리 문제 없음; zombie 방지를 위해 wait()만 호출)
        def _wait(p):
            p.wait()
        threading.Thread(target=_wait, args=(proc,), daemon=True).start()

        self._serve_json({"ok": True, "pid": proc.pid, "log": log_name})

    def _post_cancel(self):
        body = _read_body(self)
        step = body.get("step", "")
        with _process_lock:
            proc = _running.get(step)
        if proc and proc.poll() is None:
            try:
                # Fix 1: preexec_fn=os.setsid로 새 세션 생성했으므로 killpg 안전
                if sys.platform == "win32":
                    proc.terminate()
                else:
                    os.killpg(os.getpgid(proc.pid), 15)
            except Exception:
                proc.terminate()
            self._serve_json({"ok": True, "message": f"{step} 취소됨"})
        else:
            self._serve_json({"ok": False, "error": "실행 중인 프로세스 없음"})

    def _post_run_log(self):
        body = _read_body(self)
        log_name = body.get("log", "run_execute.txt")
        if ".." in log_name or "/" in log_name:
            self._serve_json({"ok": False}); return

        log_path = LOGS_DIR / log_name
        content = ""
        if log_path.exists():
            content = log_path.read_text(encoding="utf-8", errors="replace")

        # 해당 스텝의 프로세스 종료 여부로 done 판단
        step = log_name.replace("run_", "").replace(".txt", "")
        with _process_lock:
            proc = _running.get(step)
        done = proc is None or proc.poll() is not None
        exit_code = proc.returncode if (proc and proc.poll() is not None) else None

        self._serve_json({"ok": True, "log": content, "done": done, "exit_code": exit_code})

    def _post_run_all(self):
        """analyze → generate → lint → execute 순차 실행 (백그라운드 스레드)."""
        body = _read_body(self)
        platform = body.get("platform", "android")
        tc_folder = body.get("tc_folder", "").strip()

        if platform not in ("android", "ios"):
            self._serve_json({"ok": False, "error": "invalid platform"}); return

        # pipeline.json에 플랫폼 저장
        state = read_state()
        state["platform"] = platform
        save_state(state)

        MAX_HEAL = 3
        PIPELINE = ["analyze", "generate", "lint", "execute"]

        def _spawn(step, extra=None, log_suffix=""):
            script_rel, extra_args_tmpl, log_name = SCRIPT_MAP[step]
            extra_args = [a.replace("{platform}", platform) for a in extra_args_tmpl]
            if step == "analyze" and platform == "ios":
                extra_args += ["--mode", "simulator"]
            if step in ("generate", "execute") and tc_folder:
                extra_args += ["--tc-dir", tc_folder]
            if extra:
                extra_args += extra
            script = PROJECT_ROOT / script_rel
            # log_suffix로 heal 회차 구분 (e.g. run_heal_1.txt)
            lname = log_name.replace(".txt", f"{log_suffix}.txt") if log_suffix else log_name
            log_path = LOGS_DIR / lname
            extra_popen: dict = {}
            if sys.platform != "win32":
                extra_popen["preexec_fn"] = os.setsid
            with open(log_path, "w", encoding="utf-8") as lf:
                proc = subprocess.Popen(
                    [PYTHON_BIN, "-u", str(script)] + extra_args,
                    cwd=str(PROJECT_ROOT),
                    stdout=lf, stderr=subprocess.STDOUT,
                    **extra_popen,
                )
            with _process_lock:
                _running[step] = proc
            proc.wait()
            return proc.returncode, lname

        def _record_video(suffix: str) -> "Path | None":
            """실패 영상 촬영: iOS=simctl recordVideo, Android=adb screenrecord."""
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            vid_dir = PROJECT_ROOT / "reports" / "recordings"
            vid_dir.mkdir(parents=True, exist_ok=True)
            vid_path = vid_dir / f"fail_{platform}_{suffix}_{ts}.mp4"

            if platform == "ios":
                rec_proc = subprocess.Popen(
                    ["xcrun", "simctl", "io", "booted", "recordVideo",
                     "--codec=h264", str(vid_path)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
                device_id = ""
                r = subprocess.run([ADB_BIN, "devices"], capture_output=True, text=True)
                for ln in r.stdout.splitlines()[1:]:
                    if ln.strip() and "offline" not in ln:
                        device_id = ln.split()[0]; break
                if not device_id:
                    return None
                subprocess.run(
                    [ADB_BIN, "-s", device_id, "shell", "rm", "-f", "/sdcard/qa_fail.mp4"],
                    capture_output=True,
                )
                rec_proc = subprocess.Popen(
                    [ADB_BIN, "-s", device_id, "shell", "screenrecord",
                     "--time-limit", "300", "/sdcard/qa_fail.mp4"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )

            return rec_proc, vid_path, device_id if platform == "android" else None

        def _stop_video(rec_info):
            rec_proc, vid_path, device_id = rec_info
            rec_proc.terminate()
            import time as _time; _time.sleep(2)
            if platform == "android" and device_id:
                subprocess.run(
                    [ADB_BIN, "-s", device_id, "pull", "/sdcard/qa_fail.mp4", str(vid_path)],
                    capture_output=True,
                )
            return vid_path if vid_path.exists() else None

        def _run_pipeline():
            # 1단계: analyze → generate → lint → execute
            for step in PIPELINE:
                rc, _ = _spawn(step)
                if rc != 0:
                    return  # 앞단계 실패 시 중단

            # 2단계: execute 결과 확인 → 실패 시 heal 최대 3회
            execute_ok = (load_state().get("execute_results", {})
                          .get("summary", {}).get("failed", 0) == 0)

            for heal_round in range(1, MAX_HEAL + 1):
                if execute_ok:
                    break

                log_sfx = f"_{heal_round}"

                if heal_round == MAX_HEAL:
                    # 마지막 회차: 영상 찍으면서 execute 재실행
                    rec_info = _record_video(f"heal{heal_round}")
                    _spawn("execute", log_suffix=f"_record{heal_round}")
                    if rec_info:
                        saved = _stop_video(rec_info)
                        if saved:
                            st = load_state()
                            st["last_fail_video"] = str(saved)
                            save_state(st)
                    break
                else:
                    # heal 실행
                    _spawn("heal", log_suffix=log_sfx)
                    # heal 후 execute 재실행
                    rc, _ = _spawn("execute", log_suffix=log_sfx)
                    execute_ok = (load_state().get("execute_results", {})
                                  .get("summary", {}).get("failed", 0) == 0)

        threading.Thread(target=_run_pipeline, daemon=True).start()
        self._serve_json({"ok": True, "steps": PIPELINE + ["heal(x3)", "record"]})

    def _post_reset(self):
        # 실행 중인 모든 프로세스 종료
        with _process_lock:
            for step, proc in list(_running.items()):
                if proc.poll() is None:
                    proc.terminate()
            _running.clear()
        init = {
            "step": "init", "platform": "android",
            "dom_info": {}, "heal_count": 0, "last_exit_code": None,
        }
        save_state(init)
        self._serve_json({"ok": True})

    # ── Helpers ───────────────────────────────────────────────────

    def _serve_json(self, obj: dict):
        content = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._serve_bytes(content, "application/json; charset=utf-8")

    def _serve_str(self, text: str, content_type: str):
        self._serve_bytes(text.encode("utf-8"), content_type)

    def _serve_bytes(self, content: bytes, content_type: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        pass  # 콘솔 로그 억제


class ReusableHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    allow_reuse_port = True


def _kill_port(port: int):
    """포트를 점유 중인 기존 프로세스를 종료한다."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().splitlines()
        for pid in pids:
            try:
                os.kill(int(pid), 15)  # SIGTERM
            except Exception:
                pass
        if pids:
            import time
            time.sleep(0.5)
    except Exception:
        pass


def main():
    _kill_port(PORT)
    server = ReusableHTTPServer(("127.0.0.1", PORT), DashboardHandler)
    url = f"http://localhost:{PORT}"
    print(f"[Dashboard] 서버 시작: {url}")
    print(f"[Dashboard] 종료: Ctrl+C")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Dashboard] 서버 종료")


if __name__ == "__main__":
    main()
