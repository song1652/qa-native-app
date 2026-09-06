"""
App QA Dashboard 서버.

Usage:
    python agents/dashboard/serve.py
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from html import escape as html_escape
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
IMPORT_DIR    = PROJECT_ROOT / "import"
LOGS_DIR      = PROJECT_ROOT / "logs"

for d in (LOGS_DIR, REPORTS_DIR, SCREENSHOTS_DIR, IMPORT_DIR):
    d.mkdir(parents=True, exist_ok=True)

ALLOWED_ORIGIN = f"http://localhost:{PORT}"

# ── 동시성 제어 ───────────────────────────────────────────────
_state_lock   = threading.Lock()   # pipeline.json 읽기/쓰기 보호
_process_lock = threading.Lock()   # _running dict 보호
_running: dict[str, subprocess.Popen] = {}  # step → 실행 중인 프로세스
_test_runs: dict[str, dict] = {}  # 생성 파일 단위 실행 상태


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


def list_import_files() -> list:
    if not IMPORT_DIR.exists():
        return []
    return sorted(f.name for f in IMPORT_DIR.glob("*.xlsx") if f.is_file())


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
    "generate": ("scripts/02_generate.py", ["--platform", "{platform}", "--strict-locators"],       "run_generate.txt"),
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
  color-scheme:dark;
  --bg:#08071b;
  --bg-gradient:radial-gradient(ellipse at 20% 0%,rgba(88,40,180,.15),transparent 50%),
    radial-gradient(ellipse at 80% 100%,rgba(60,30,140,.1),transparent 50%),#08071b;
  --surface:rgba(18,16,42,.55); --surface2:rgba(28,24,60,.5);
  --border:rgba(140,120,220,.12); --border-glass:rgba(140,120,220,.1);
  --text:#f0eff5; --text2:#b8b3d0; --text3:#8c87a8;
  --pass:#34d399; --fail:#fb7185; --warn:#fbbf24; --accent:#8b5cf6;
  --android:#3ddc84; --ios:#60a5fa; --radius:12px; --radius-sm:8px;
}
*{box-sizing:border-box;margin:0;padding:0}
html{height:100%;overflow:hidden}
body{font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:var(--bg-gradient);color:var(--text);font-size:14px;height:100%;min-height:100vh;overflow:hidden}
h1{font-size:21px;font-weight:800;letter-spacing:.2px;
  background:linear-gradient(135deg,#fff 0%,#d8ccf8 50%,#a78bfa 100%);
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.subtitle{font-size:12px;color:var(--text3);margin-top:3px;margin-bottom:24px}

/* fixed 앱과 동일한 외곽 셸 */
.title-row{height:54px;display:flex;align-items:center;gap:14px;padding:0 24px;
  background:rgba(12,10,30,.7);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);
  border-bottom:1px solid var(--border-glass);position:relative;z-index:10}
.title-row::after{content:'';position:absolute;left:0;right:0;bottom:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(139,92,246,.2) 30%,rgba(167,139,250,.15) 70%,transparent)}
.title-row>div:first-child{display:flex;align-items:center;gap:14px}
.title-row h1{font-size:15px;white-space:nowrap}
.title-row .subtitle{display:none}
.title-row::before{content:'●  LIVE';font-size:10px;font-weight:600;letter-spacing:.8px;color:var(--pass);
  background:rgba(52,211,153,.06);border:1px solid rgba(52,211,153,.12);padding:3px 10px;border-radius:16px}

/* 상태 바 */
.status-bar{height:46px;display:flex;align-items:center;gap:18px;flex-wrap:wrap;flex-shrink:0;
  background:rgba(12,10,30,.62);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
  border-bottom:1px solid var(--border-glass);padding:0 24px;margin:0;position:relative;z-index:9}
.reset-btn{flex-shrink:0;margin-left:auto;font-size:11px;font-weight:600;padding:6px 13px;border-radius:8px;
  background:rgba(255,255,255,.03);color:var(--text2);border:1px solid var(--border);
  cursor:pointer;transition:all .18s}
.reset-btn:hover:not(:disabled){background:rgba(251,113,133,.08);color:var(--fail);
  border-color:rgba(251,113,133,.35)}
.reset-btn:disabled{opacity:.5;cursor:wait}
.si{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text2)}
.sdiv{width:1px;height:16px;background:var(--border)}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot.on{background:var(--pass);box-shadow:0 0 6px var(--pass)}
.dot.off{background:var(--fail)}
.step-badge{padding:2px 9px;border-radius:10px;font-size:11px;font-weight:600;
  background:rgba(99,102,241,.15);color:var(--accent);border:1px solid rgba(99,102,241,.3)}
.automation-badge{padding:3px 9px;border-radius:10px;font-size:11px;font-weight:600;
  color:var(--text2);background:rgba(139,92,246,.1);border:1px solid rgba(139,92,246,.22)}

/* 레이아웃 */
.grid{display:grid;grid-template-columns:360px minmax(0,1fr);gap:18px;align-items:start}
.app-layout{display:flex;height:calc(100vh - 100px);min-height:0;overflow:hidden}
.sidebar{position:static;left:auto;top:auto;bottom:auto;width:260px;flex-shrink:0;z-index:5;background:rgba(12,10,30,.5);
  backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:0;border-right:1px solid var(--border-glass);
  border-radius:0;padding:14px 0;min-height:0;overflow-y:auto}
.sidebar-section{padding:8px 0 12px;border-bottom:1px solid var(--border)}
.sidebar-section:last-child{border-bottom:none}
.sidebar-label{padding:6px 16px;font-size:10px;font-weight:600;color:var(--text3);
  text-transform:uppercase;letter-spacing:1px;opacity:.75}
.sidebar-item{display:flex;align-items:center;gap:9px;padding:9px 16px;cursor:pointer;
  color:var(--text2);font-size:14px;font-weight:500;border-left:2px solid transparent;
  transition:all .18s}
.sidebar-item:hover{background:rgba(139,92,246,.07);color:var(--text)}
.sidebar-item.active{background:linear-gradient(90deg,rgba(139,92,246,.12),transparent);
  border-left-color:var(--accent);color:#fff;font-weight:600}
.sidebar-dot{width:7px;height:7px;border-radius:50%;background:rgba(140,120,220,.25);
  border:1px solid rgba(140,120,220,.35);flex-shrink:0}
.sidebar-item.active .sidebar-dot{background:var(--accent);border-color:var(--accent);
  box-shadow:0 0 7px rgba(139,92,246,.6)}
.app-main{flex:1;min-width:0;min-height:0;overflow-y:auto;padding:24px 32px 48px}
.app-main::before{content:'Dashboard';display:none;font-size:29px;font-weight:800;margin:0 0 10px 0;
  letter-spacing:-.7px;color:#f0eff5}
.app-main.dashboard-view::before{display:none}
.app-main.quick-view::before{content:'빠른 실행'}
.app-main.quick-view::before{display:none}
.app-main.report-view::before{display:none}
.app-main.quick-view .grid.focus-right #view-tests .tabs{display:none}
.quick-mode .app-layout,.report-mode .app-layout{height:calc(100vh - 100px)}
.quick-mode .app-main,.report-mode .app-main{overflow:hidden}
.app-main>.grid{max-width:920px;margin:0 auto}
.app-main.report-view>.grid{max-width:none;margin:0}
.app-main.dashboard-view>.grid{display:none}
body.dashboard-mode .app-layout{height:calc(100vh - 100px)}
.overview-view{max-width:920px;margin:0 auto;padding:0 0 24px}
.overview-heading{font-size:29px;font-weight:800;letter-spacing:-.7px;margin:0 0 20px;
  background:linear-gradient(135deg,#fff 0%,#d8ccf8 60%,#a78bfa 100%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.overview-hero{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
.overview-card{background:var(--surface);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border:1px solid var(--border);border-radius:var(--radius);padding:20px 24px;box-shadow:0 4px 24px rgba(0,0,0,.22);position:relative;overflow:hidden}
.overview-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(139,92,246,.24),transparent)}
.overview-hero-main{display:flex;align-items:center;gap:24px;min-height:194px;padding:22px 28px}
.overview-donut{width:150px;height:150px;flex-shrink:0;transform:rotate(-90deg);overflow:visible}
.overview-donut-bg,.overview-donut-fill{fill:none;stroke-width:5}
.overview-donut-bg{stroke:rgba(140,120,220,.08)}
.overview-donut-fill{stroke:var(--pass);stroke-linecap:butt;filter:drop-shadow(0 0 4px var(--pass));transition:stroke-dasharray .35s ease}
.overview-donut-value{font-size:24px;font-weight:800;fill:var(--text);transform:rotate(90deg);transform-origin:60px 60px}
.overview-donut-label{font-size:9px;font-weight:600;letter-spacing:.7px;fill:var(--text3);transform:rotate(90deg);transform-origin:60px 60px}
.overview-context{font-size:11px;color:var(--text3);font-weight:500;margin-bottom:12px;white-space:nowrap}
.overview-hero-stats{display:flex;gap:16px}
.overview-stat b{display:block;font-size:22px;font-weight:800;line-height:1}
.overview-stat small{display:block;margin-top:4px;font-size:10px;color:var(--text3);font-weight:600}
.overview-hero-legend,.overview-trend-legend{display:flex;align-items:center;gap:12px;flex-wrap:wrap;color:var(--text3);font-size:10px;white-space:nowrap}
.overview-hero-legend{margin-top:12px}.overview-legend-item{display:inline-flex;align-items:center;gap:4px}
.overview-legend-dot{width:6px;height:6px;border-radius:50%;display:inline-block}
.overview-trend-title{font-size:12px;font-weight:600;color:var(--text3);margin-bottom:8px}
.overview-trend-empty,.overview-trend-chart{height:144px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--text3);font-size:12px;opacity:.7}
.overview-trend-empty-message{flex:1;display:flex;align-items:center}
.overview-trend-chart{display:block;opacity:1}
.overview-trend-chart svg{width:100%;height:100%}
.overview-trend-footer{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-top:2px;color:var(--text3);font-size:10px}
.overview-trend-footer .overview-trend-legend{justify-content:flex-end;gap:12px;margin-left:auto}
.overview-kpi-row{display:flex;gap:12px;margin-bottom:20px}
.overview-kpi{flex:1;display:flex;align-items:center;gap:12px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;position:relative;overflow:hidden}
.overview-kpi-icon{font-size:10px;color:var(--accent);opacity:.7}.overview-kpi-label{font-size:10px;font-weight:600;color:var(--text3);margin-bottom:2px}.overview-kpi-value{font-size:16px;font-weight:700}
.overview-log-head{display:flex;align-items:center;justify-content:space-between;font-size:12px;font-weight:600;color:var(--text3);margin-bottom:12px}
.overview-log{background:rgba(8,7,20,.6);border:1px solid var(--border);border-radius:10px;padding:14px;font:11px/1.7 monospace;color:#a78bfa;max-height:180px;overflow-y:auto;white-space:pre-wrap;word-break:break-all}
.overview-log-head .log-clear{border:1px solid var(--border);border-radius:6px;padding:3px 7px;font-size:14px;line-height:1;color:var(--text3)}
@media (max-width:900px){.overview-view{max-width:none}.overview-hero{grid-template-columns:1fr}.overview-kpi-row{flex-wrap:wrap}.overview-kpi{min-width:180px}}
.pipeline-card-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px}.pipeline-card-head .card-title{margin-bottom:0}
.pipeline-card-head .reset-btn{font-size:13px;padding:7px 15px;color:var(--text);background:rgba(139,92,246,.14);border-color:rgba(139,92,246,.45);box-shadow:0 0 0 1px rgba(139,92,246,.08)}
.pipeline-card-head .reset-btn:hover:not(:disabled){background:rgba(139,92,246,.26);color:#fff;border-color:var(--accent)}
.view-hidden{display:none!important}
.grid.focus-left{display:block}
.grid.focus-left .right-panel{display:none}
.grid.focus-right{display:block}
.grid.focus-right #view-pipeline{display:none}

/* 카드 */
.card{background:var(--surface);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
  border:1px solid var(--border);border-radius:var(--radius);padding:20px;box-shadow:0 8px 30px rgba(0,0,0,.12)}
.card-title{font-size:12px;text-transform:uppercase;letter-spacing:.9px;
  color:var(--text3);font-weight:600;margin-bottom:16px}

/* 플랫폼 라디오 */
.platform-radio{display:none}
.platform-selector{display:flex;gap:10px;margin-bottom:18px}
.pl-label{flex:1;display:flex;flex-direction:column;align-items:center;gap:8px;
  padding:16px 10px;border-radius:var(--radius);border:2px solid var(--border);
  cursor:pointer;transition:all .18s;background:rgba(255,255,255,.03)}
.pl-label:hover{border-color:rgba(255,255,255,.25)}
.pl-icon{font-size:28px}
.pl-name{font-size:14px;font-weight:700}
.pl-desc{font-size:11px;color:var(--text3);text-align:center;line-height:1.5}
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
  border:1px solid var(--border);font-size:13px;font-weight:600;cursor:pointer;
  transition:all .15s;display:flex;align-items:center;justify-content:space-between;
  background:rgba(255,255,255,.03);color:var(--text2)}
.btn:hover:not(:disabled){background:rgba(139,92,246,.08);color:var(--text);border-color:rgba(139,92,246,.35)}
.btn:disabled{opacity:.4;cursor:not-allowed}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover:not(:disabled){opacity:.85}
.btn.heal-btn{background:rgba(245,158,11,.12);border-color:rgba(245,158,11,.4);color:var(--warn)}
.btn.heal-btn:hover:not(:disabled){background:rgba(245,158,11,.2)}
.btn-right{display:flex;align-items:center;gap:6px}
.btn-tag{font-size:11px;font-weight:600;padding:2px 6px;border-radius:6px;
  background:rgba(255,255,255,.1);color:rgba(255,255,255,.5)}
.btn-tip{font-size:11px;color:var(--text3)}

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
.log-label{font-size:12px;color:var(--text3)}
.log-clear{font-size:11px;color:var(--text3);cursor:pointer;background:none;border:none;padding:0}
.log-clear:hover{color:var(--text2)}
.log-box{background:#060a0f;border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:10px 12px;font-size:12px;font-family:monospace;color:#7dd3a8;
  max-height:180px;overflow-y:auto;white-space:pre-wrap;line-height:1.7}

/* 실패 요약 */
.fail-summary{margin-top:12px;display:none}
.fail-summary.visible{display:block}
.fail-title{font-size:12px;font-weight:600;color:var(--fail);margin-bottom:6px;
  display:flex;align-items:center;gap:6px}
.fail-item{background:rgba(244,63,94,.08);border:1px solid rgba(244,63,94,.2);
  border-radius:var(--radius-sm);padding:8px 10px;margin-bottom:6px;font-size:12px}
.fail-tc{font-weight:600;color:var(--fail);font-family:monospace;word-break:break-all}
.fail-err{color:var(--text3);margin-top:3px;font-size:11px;font-family:monospace;word-break:break-all}

/* 오른쪽 패널 */
.right-panel{display:flex;flex-direction:column;gap:14px}

/* 탭 */
.tabs{display:flex;gap:4px;margin-bottom:12px}
.tab{padding:6px 13px;border-radius:var(--radius-sm);font-size:12px;font-weight:600;
  cursor:pointer;border:1px solid var(--border);background:transparent;color:var(--text3)}
.tab.active{background:var(--surface2);color:var(--text);border-color:rgba(255,255,255,.2)}
.tab-content{display:none}.tab-content.active{display:block}

/* 생성 파일 */
.gen-item{display:flex;align-items:center;justify-content:space-between;
  padding:8px 0;border-bottom:1px solid var(--border);font-size:13px}
.gen-item:last-child{border-bottom:none}
.gen-badge{font-size:11px;font-weight:600;padding:3px 8px;border-radius:7px;margin-right:6px}
.gen-badge.android{background:rgba(61,220,132,.12);color:var(--android)}
.gen-badge.ios{background:rgba(0,122,255,.12);color:var(--ios)}
.gen-count{color:var(--text3);font-size:12px}
.gen-file{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 0;border-bottom:1px solid var(--border);font-size:11px}
.gen-file:last-child{border-bottom:none}
.gen-file-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text2);font-family:monospace}
.gen-run-btn{flex-shrink:0;padding:4px 9px;border-radius:6px;border:1px solid rgba(139,92,246,.35);background:rgba(139,92,246,.1);color:var(--accent);font-size:10px;cursor:pointer}
.gen-run-btn:hover{background:rgba(139,92,246,.22);color:#fff}
.quick-view-title{font-size:29px;font-weight:800;letter-spacing:-.7px;margin-bottom:10px;color:var(--text)}
.quick-view-subtitle{font-size:13px;color:var(--text3);margin-bottom:16px}
.quick-select-card,.quick-result-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:16px}
.quick-select-head,.quick-result-head{display:flex;align-items:center;justify-content:space-between;font-size:13px;font-weight:600;margin-bottom:12px}
.quick-select-head label,.quick-action-row label{font-size:13px;color:var(--text2);font-weight:400;cursor:pointer}
.quick-group-list{display:flex;flex-direction:column;gap:2px}
.quick-group-item{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:8px;cursor:pointer;font-size:14px}
.quick-group-item:hover{background:rgba(139,92,246,.06)}
.quick-group-item input{width:16px;height:16px;accent-color:#60a5fa;cursor:pointer}
.quick-group-name{flex:1;font-weight:500;color:var(--text)}
.quick-group-count{font-size:13px;color:var(--text2)}
.quick-action-row{display:flex;align-items:center;gap:10px;margin-top:14px}
.quick-run-action{background:var(--accent);border:0;border-radius:8px;color:#fff;padding:10px 20px;font-weight:600;font-size:13px;cursor:pointer}
.quick-run-action:disabled{opacity:.5;cursor:wait}
.quick-log{background:#060a0f;border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;font:11px/1.6 monospace;color:#7dd3a8;white-space:pre-wrap;max-height:220px;overflow:auto;margin-bottom:16px}
.quick-result-head{margin-bottom:16px}.quick-result-badge{padding:4px 12px;border-radius:16px;font-size:10px}.quick-result-badge.pass{color:var(--pass);border:1px solid rgba(52,211,153,.3);background:rgba(52,211,153,.08)}.quick-result-badge.fail{color:var(--fail);border:1px solid rgba(251,113,133,.3);background:rgba(251,113,133,.08)}
.quick-result-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.quick-result-stats>div{text-align:center;border:1px solid var(--border);border-radius:10px;padding:12px 8px}.quick-result-stats b{display:block;font-size:25px;color:var(--text)}.quick-result-stats small{font-size:10px;color:var(--text2);letter-spacing:.5px}.pass-text{color:var(--pass)!important}.fail-text{color:var(--fail)!important}.quick-result-meta{margin-top:12px;font-size:11px;color:var(--text3)}
.reports-view .report-preview{margin-top:0;padding-top:0;border-top:0}
.report-delete-dialog{position:fixed;inset:0;width:min(460px,90vw);max-height:min(80vh,520px);margin:auto;padding:26px;border:1px solid var(--border);border-radius:var(--radius);background:#12102a;color:var(--text);box-shadow:0 16px 48px #0008}.report-delete-dialog::backdrop{background:#0009}.report-delete-dialog h2{margin:0 0 16px;font-size:18px}.report-delete-dialog p{overflow-wrap:anywhere;line-height:1.8;font-size:13px;color:var(--text3)}.report-dialog-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:24px}.report-delete-dialog button{font:12px inherit;border:1px solid var(--border);border-radius:8px;padding:8px 12px;background:var(--surface2);color:var(--text);cursor:pointer}.report-delete-dialog .report-danger{color:var(--fail);border-color:rgba(251,113,133,.3)}
.report-pager button{font:12px inherit;padding:8px 12px;border:1px solid var(--border);border-radius:8px;background:var(--surface2);color:var(--text2);cursor:pointer}.report-pager button:disabled{opacity:.4;color:var(--text3);background:rgba(255,255,255,.03);cursor:default}
.reports-view{width:100%}.reports-title{font-size:29px;font-weight:800;letter-spacing:-.7px;margin-bottom:10px}.reports-subtitle{font-size:13px;color:var(--text3);margin-bottom:18px}.report-controls{display:flex;gap:10px;align-items:center;padding:14px;margin-bottom:14px;border:1px solid var(--border);border-radius:var(--radius);background:var(--surface)}.report-search{flex:1;min-width:140px;padding:9px 12px;border:1px solid var(--border);border-radius:8px;background:#08071b;color:var(--text);font:12px inherit}.report-controls button,.report-controls select,.report-actions button,.report-actions a,.report-panel-head button{font:12px inherit;border:1px solid var(--border);border-radius:8px;padding:8px 12px;background:var(--surface2);color:var(--text);cursor:pointer;text-decoration:none}.report-danger{color:var(--fail)!important}.report-count,.report-selection-count{color:var(--text3);font-size:12px;white-space:nowrap}.report-workspace{display:grid;grid-template-columns:minmax(370px,.95fr) minmax(360px,1.3fr);gap:14px;align-items:stretch}.report-panel{display:flex;flex-direction:column;min-width:0;height:max(570px,calc(100vh - 290px));border:1px solid var(--border);border-radius:var(--radius);background:var(--surface);overflow:hidden}.report-panel-head{display:flex;flex-shrink:0;align-items:center;justify-content:space-between;gap:12px;min-height:62px;padding:14px 16px;border-bottom:1px solid var(--border);background:var(--surface2);font-size:13px}.report-select-all{display:flex;align-items:center;gap:9px;cursor:pointer}.reports-view input[type=checkbox]{width:16px;height:16px;accent-color:var(--accent);cursor:pointer}.report-list{flex:1;min-height:0;overflow-y:auto}.report-item{display:grid;grid-template-columns:20px minmax(0,1fr);gap:8px 10px;align-items:center;padding:15px 16px;border-bottom:1px solid var(--border)}.report-item:hover,.report-item.is-open{background:rgba(139,92,246,.11)}.report-info{min-width:0}.report-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px;font-weight:600;color:var(--text)}.report-meta{margin-top:4px;font-size:11px;color:var(--text3)}.report-actions{grid-column:2;display:flex;gap:6px}.report-actions button,.report-actions a{padding:5px 9px;font-size:11px;background:transparent}.report-empty{padding:36px 20px;text-align:center;line-height:1.7;color:var(--text3);font-size:13px}.report-pager{display:flex;justify-content:center;align-items:center;gap:12px;padding:14px;color:var(--text3);font-size:12px}.report-preview{display:flex;flex-direction:column}.report-iframe-wrap{flex:1;min-height:0;margin:16px;border:1px solid var(--border);border-radius:10px;overflow:hidden;background:#fff}.report-iframe-wrap iframe{display:block;width:100%;height:100%;min-height:540px;border:none}.report-preview-empty{margin:auto}.report-panel-head button{padding:5px 9px;font-size:11px;background:transparent}
.import-controls{display:flex;flex-direction:column;gap:10px}
.import-row{display:flex;align-items:center;gap:8px}
.import-row label{font-size:12px;color:var(--text3);min-width:44px}
.import-select,.import-file{flex:1;min-width:0;background:var(--surface2);color:var(--text);
  border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 10px;font-size:12px}
.import-platforms{display:flex;gap:12px;font-size:12px;color:var(--text2)}
.import-platforms label{display:flex;align-items:center;gap:5px;min-width:0}
.import-help{font-size:11px;color:var(--text3);line-height:1.6}
.import-result{font-size:12px;color:var(--pass);line-height:1.6;white-space:pre-wrap}

/* 리포트 */
.report-link{display:flex;align-items:center;justify-content:space-between;
  padding:8px 0;border-bottom:1px solid var(--border);text-decoration:none;
  color:var(--text2);font-size:13px;transition:color .15s}
.report-link:last-child{border-bottom:none}
.report-link:hover{color:var(--accent)}
.report-preview{margin-top:14px;padding-top:14px;border-top:1px solid var(--border)}
.report-preview-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.report-preview-title{font-size:12px;color:var(--text2)}
.report-preview-close{font-size:10px;padding:4px 9px;border:1px solid var(--border);
  border-radius:6px;background:transparent;color:var(--text3);cursor:pointer}
.report-preview-close:hover{color:var(--text);border-color:rgba(139,92,246,.4)}
.report-preview iframe{width:100%;height:560px;border:1px solid var(--border);
  border-radius:var(--radius-sm);background:#fff}

/* 실행 히스토리 — native-fixed의 KPI / 필터 / 결과 행 구조 */
.app-main.history-view::before{content:'실행 히스토리'}
.history-card{background:transparent;border:0;box-shadow:none;padding:0;overflow:visible}
.history-toolbar{display:flex;align-items:center;justify-content:flex-end;margin-bottom:16px}
.history-reset{padding:6px 12px;border:1px solid rgba(251,113,133,.45);border-radius:6px;
  background:rgba(251,113,133,.04);color:#fb7185;font-size:12px;font-weight:600;cursor:pointer}
.history-reset:hover{background:rgba(251,113,133,.12)}
.history-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:20px}
.history-kpi{min-height:72px;padding:14px 16px;background:var(--surface);border:1px solid var(--border);
  border-radius:12px;box-shadow:0 4px 18px rgba(0,0,0,.12)}
.history-kpi-label{font-size:11px;color:var(--text2);font-weight:600;letter-spacing:.2px;margin-bottom:5px}
.history-kpi-value{font-size:24px;line-height:1;font-weight:800;color:var(--text)}
.history-kpi-value.pass{color:var(--pass)}
.history-kpi-value.accent{color:var(--accent)}
.history-kpi-suffix{font-size:13px;color:var(--text2);font-weight:600;margin-left:2px}
.history-filters{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:16px;color:var(--text2);font-size:12px}
.history-filter-label{font-weight:600;margin-right:2px}
.history-filter{padding:5px 12px;border:1px solid var(--border);border-radius:8px;
  background:rgba(255,255,255,.02);color:var(--text2);font:600 12px inherit;cursor:pointer}
.history-filter:hover,.history-filter.active{background:rgba(139,92,246,.14);border-color:rgba(139,92,246,.45);color:#fff}
.history-filter.group{border-radius:7px;padding:5px 11px}
.history-table{border:1px solid var(--border);border-radius:12px;background:rgba(18,16,42,.42);overflow:hidden}
.history-row{display:grid;grid-template-columns:1.15fr .82fr .92fr .68fr .72fr 1.85fr .9fr;align-items:center;gap:12px;
  min-height:70px;padding:12px 16px;border-bottom:1px solid var(--border);font-size:12px}
.history-row:last-child{border-bottom:0}
.history-row.header{min-height:42px;background:rgba(255,255,255,.025);color:var(--text3);font-size:10px;text-transform:uppercase;letter-spacing:.4px}
.history-date{font-family:monospace;color:var(--text2);line-height:1.35}
.history-date strong{display:block;color:var(--text);font-size:13px}
.history-pass{color:var(--pass);font-size:18px;font-weight:800}
.history-progress{height:4px;margin-top:5px;background:rgba(52,211,153,.18);border-radius:4px;overflow:hidden}
.history-progress span{display:block;width:100%;height:100%;background:var(--pass)}
.history-count{font-size:17px;font-weight:800;color:var(--text)}
.history-count small{font-size:11px;color:var(--text2);font-weight:600}
.history-type{display:inline-flex;align-items:center;justify-content:center;padding:5px 8px;border-radius:7px;
  background:rgba(139,92,246,.12);color:#a78bfa;font-size:11px;font-weight:700;white-space:nowrap}
.history-platform{display:inline-flex;align-items:center;justify-content:center;padding:5px 8px;border-radius:7px;
  font-size:11px;font-weight:700;white-space:nowrap}
.history-platform.android{color:#34d399;background:rgba(52,211,153,.1);border:1px solid rgba(52,211,153,.22)}
.history-platform.ios{color:#60a5fa;background:rgba(96,165,250,.1);border:1px solid rgba(96,165,250,.22)}
.history-groups{display:flex;gap:6px;flex-wrap:wrap}
.history-group{padding:4px 7px;border-radius:4px;background:rgba(139,92,246,.14);color:#a78bfa;font:700 10px monospace;white-space:nowrap}
.history-result{display:inline-flex;justify-content:center;padding:5px 10px;border-radius:6px;
  border:1px solid rgba(52,211,153,.3);background:rgba(52,211,153,.08);color:var(--pass);font-size:11px;font-weight:700;white-space:nowrap}
.history-empty{padding:34px;text-align:center;color:var(--text3);font-size:13px}

.empty{font-size:13px;color:var(--text3);padding:6px 0}

/* 다음 스텝 하이라이트 */
.btn.suggested{border-color:#f59e0b!important;box-shadow:0 0 0 1px rgba(245,158,11,.4)}
/* TC 폴더 선택 */
.tc-folder-bar{margin-bottom:12px}
.tc-folder-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:7px}
.tc-folder-head label{font-size:13px;color:var(--text2);font-weight:600}
.tc-folder-actions{display:flex;gap:8px}
.tc-folder-action{border:0;background:none;color:var(--accent);font-size:11px;cursor:pointer;padding:0}
.tc-folder-list{display:flex;flex-direction:column;gap:6px;padding:9px 10px;background:var(--surface2);
  border:1px solid var(--border);border-radius:var(--radius-sm);max-height:120px;overflow-y:auto}
.tc-folder-option{display:flex;align-items:center;gap:8px;color:var(--text2);font-size:13px;cursor:pointer}
.tc-folder-option input{accent-color:var(--accent);width:15px;height:15px}
.tc-folder-empty{color:var(--text3);font-size:12px}
.tc-folder-count{color:var(--text3);font-size:12px}

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

button,select{font-family:inherit}
button:focus-visible,select:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (max-width:900px){
  body{padding:0}
  .app-layout{display:block;height:auto;overflow:visible}
  .status-bar{height:auto;min-height:46px;padding:10px 20px;gap:12px}
  .sidebar{position:static;width:100%;min-height:0;display:flex;overflow-x:auto;padding:4px}
  .app-main{overflow:visible;padding:20px}
  .app-main::before{font-size:24px}
  .sidebar-section{display:flex;align-items:center;border-bottom:none;padding:0}
  .sidebar-label{display:none}
  .sidebar-item{white-space:nowrap;border-left:none;border-bottom:2px solid transparent}
  .sidebar-item.active{border-left:none;border-bottom-color:var(--accent)}
  .grid{grid-template-columns:1fr}
  .history-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  .history-table{overflow-x:auto}
  .history-row{min-width:820px}
}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;
  animation-iteration-count:1!important;scroll-behavior:auto!important;transition-duration:.01ms!important}}
</style>
</head>
<body class="dashboard-mode">

<div class="title-row">
  <div><h1>QA CONTROL CENTER</h1><div class="subtitle">Appium 기반 모바일 자동화</div></div>
</div>

<!-- 상단 고정 상태바 -->
<div class="status-bar" aria-label="실행 상태">
  <div class="si"><span class="dot" id="dot-appium"></span><span id="txt-appium">확인 중...</span></div>
  <div class="sdiv"></div>
  <div class="si"><span class="dot" id="dot-device"></span><span id="txt-device">확인 중...</span></div>
  <div class="sdiv"></div>
  <div class="si"><span id="txt-automation" class="automation-badge">자동화: 확인 중...</span></div>
  <div class="sdiv"></div>
  <div class="si">파이프라인:&nbsp;<span class="step-badge" id="txt-step">-</span></div>
  <div class="sdiv"></div>
  <div class="si" id="heal-row" style="display:none">힐링: <span id="heal-cnt" style="color:var(--warn);font-weight:700;margin-left:3px"></span>회</div>
</div>

<!-- 메인 그리드 -->
<div class="app-layout">

  <aside class="sidebar" aria-label="주 메뉴">
    <div class="sidebar-section">
      <div class="sidebar-label">개요</div>
      <div class="sidebar-item active" data-view="dashboard" onclick="selectView('dashboard',this)">
        <span class="sidebar-dot"></span><span>Dashboard</span>
      </div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-label">Import</div>
      <div class="sidebar-item" data-view="import" onclick="selectView('import',this)">
        <span class="sidebar-dot"></span><span>Import Studio</span>
      </div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-label">파이프라인</div>
      <div class="sidebar-item" data-view="pipeline" onclick="selectView('pipeline',this)">
        <span class="sidebar-dot"></span><span>파이프라인 실행</span>
      </div>
      <div class="sidebar-item" data-view="tests" onclick="selectView('tests',this)">
        <span class="sidebar-dot"></span><span>빠른 실행</span>
      </div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-label">테스트 결과</div>
      <div class="sidebar-item" data-view="reports" onclick="selectView('reports',this)">
        <span class="sidebar-dot"></span><span>리포트 목록</span>
      </div>
      <div class="sidebar-item" data-view="history" onclick="selectView('history',this)">
        <span class="sidebar-dot"></span><span>실행 히스토리</span>
      </div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-label">설정</div>
      <div class="sidebar-item" data-view="config" onclick="selectView('config',this)">
        <span class="sidebar-dot"></span><span>Appium 설정</span>
      </div>
    </div>
  </aside>
  <main class="app-main dashboard-view">
  <div id="view-overview" class="overview-view">
    <div class="overview-heading">Dashboard</div>
    <div class="overview-hero">
      <div class="overview-card overview-hero-main">
        <svg class="overview-donut" viewBox="0 0 120 120"><circle class="overview-donut-bg" cx="60" cy="60" r="48"></circle><circle id="overview-donut-fill" class="overview-donut-fill" cx="60" cy="60" r="48" stroke-dasharray="0 302"></circle><text id="overview-rate" class="overview-donut-value" x="60" y="61" text-anchor="middle">0%</text><text class="overview-donut-label" x="60" y="76" text-anchor="middle">PASS RATE</text></svg>
        <div><div class="overview-context" id="overview-context">최근 실행 없음</div><div class="overview-hero-stats"><div class="overview-stat"><b id="overview-total">0</b><small>Total</small></div><div class="overview-stat"><b id="overview-passed" style="color:var(--pass)">0</b><small>Passed</small></div><div class="overview-stat"><b id="overview-failed" style="color:var(--fail)">0</b><small>Failed</small></div></div><div class="overview-hero-legend"><span class="overview-legend-item"><i class="overview-legend-dot" style="background:var(--pass)"></i>통과</span><span class="overview-legend-item"><i class="overview-legend-dot" style="background:var(--fail)"></i>실패</span><span class="overview-legend-item"><i class="overview-legend-dot" style="background:var(--warn)"></i>경고 (80%↑)</span></div></div>
      </div>
      <div class="overview-card"><div class="overview-trend-title">Run History</div><div class="overview-trend-empty" id="overview-trend">실행 이력 없음</div></div>
    </div>
    <div class="overview-kpi-row"><div class="overview-kpi"><span class="overview-kpi-icon">◆</span><div><div class="overview-kpi-label">Appium</div><div class="overview-kpi-value" id="overview-appium">확인 중</div></div></div><div class="overview-kpi"><span class="overview-kpi-icon">◆</span><div><div class="overview-kpi-label">Generated Tests</div><div class="overview-kpi-value" id="overview-generated">0개</div></div></div><div class="overview-kpi"><span class="overview-kpi-icon">◆</span><div><div class="overview-kpi-label">Healing</div><div class="overview-kpi-value" id="overview-healing">0회</div></div></div></div>
    <div class="overview-card"><div class="overview-log-head"><span>Recent Logs</span><button class="log-clear" onclick="refreshOverview()">↻</button></div><div class="overview-log" id="overview-log">로그 없음</div></div>
  </div>
  <div class="grid">

  <!-- 왼쪽: 플랫폼 + 테스트 실행 -->
  <div class="card" id="view-pipeline">
    <div class="pipeline-card-head"><div class="card-title">플랫폼 선택 &amp; 파이프라인 실행</div><button id="reset-btn" class="reset-btn" onclick="resetDashboard()">↺ 리셋</button></div>

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
      <div class="tc-folder-head">
        <label>실행할 TC 폴더</label>
        <div class="tc-folder-actions">
          <button class="tc-folder-action" type="button" onclick="toggleAllTcFolders(true)">전체 선택</button>
          <button class="tc-folder-action" type="button" onclick="toggleAllTcFolders(false)">전체 해제</button>
        </div>
      </div>
      <div id="tc-folder-list" class="tc-folder-list">
        <div class="tc-folder-empty">testcases 폴더를 확인 중...</div>
      </div>
      <div id="tc-folder-count" class="tc-folder-count" style="margin-top:5px">직렬 실행 순서대로 선택됩니다.</div>
    </div>

    <!-- 전체 실행 버튼 -->
    <button class="btn primary" id="btn-run-all" onclick="runAll()" style="width:100%;margin-bottom:14px;justify-content:center;gap:8px;font-size:13px">
      <span>▶ 전체 실행</span>
      <span style="font-size:10px;opacity:.7">analyze → generate → lint → execute</span>
      <div class="spinner"></div>
    </button>

    <!-- 실행 단계 -->
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
    <div class="card" id="view-tests">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px">
        <div class="card-title" style="margin-bottom:0">생성된 테스트 파일 실행</div>
      </div>
      <div class="tabs">
        <button class="tab active" onclick="switchTab('gen','all',this)">전체</button>
        <button class="tab" onclick="switchTab('gen','android',this)">Android</button>
        <button class="tab" onclick="switchTab('gen','ios',this)">iOS</button>
      </div>
      <div id="gen-all"  class="tab-content active"><div class="empty">없음</div></div>
      <div id="gen-android" class="tab-content"><div class="empty">없음</div></div>
        <div id="gen-ios"     class="tab-content"><div class="empty">없음</div></div>
    </div>

    <div class="card" id="view-import">
      <div class="card-title">Import Studio</div>
      <div class="import-controls">
        <div class="import-help">Excel 테스트 케이스를 현재 Appium용 Markdown 형식으로 변환합니다.</div>
        <div class="import-row"><label for="import-file-upload">Excel</label>
          <input id="import-file-upload" class="import-file" type="file" accept=".xlsx" onchange="uploadImportFile(this)"></div>
        <div class="import-row"><label for="import-file">파일</label>
          <select id="import-file" class="import-select" onchange="loadImportSheets()"><option value="">Excel 파일 선택</option></select></div>
        <div class="import-row"><label for="import-sheet">시트</label>
          <select id="import-sheet" class="import-select"><option value="">시트 선택</option></select></div>
        <div class="import-platforms">
          <label><input type="checkbox" name="import-platform" value="android" checked> Android</label>
          <label><input type="checkbox" name="import-platform" value="ios" checked> iOS</label>
        </div>
        <button class="btn primary" onclick="convertImport()">Excel → Markdown 변환</button>
        <div id="import-result" class="import-result"></div>
      </div>
    </div>

    <!-- 리포트 -->
    <div class="card" id="view-reports">
      <div class="reports-view">
        <div class="reports-title">테스트 리포트</div>
        <p class="reports-subtitle">생성된 실행 결과를 확인하고 필요한 리포트만 관리하세요.</p>
        <div class="report-controls">
          <input class="report-search" id="report-search-input" type="text" placeholder="리포트 이름 검색">
          <select id="report-sort"><option value="newest">최신순</option><option value="oldest">오래된순</option><option value="name">파일명순</option></select>
          <button type="button" id="report-refresh">새로고침</button>
          <button type="button" id="report-delete-selected" class="report-danger">선택 삭제</button>
          <span class="report-count" id="report-count">0개 리포트</span>
        </div>
        <div class="report-workspace">
          <section class="report-panel">
            <div class="report-panel-head"><label class="report-select-all"><input type="checkbox" id="report-select-all">전체 선택</label><span class="report-selection-count" id="report-selection-count">0개 선택</span></div>
            <div class="report-list" id="report-list"><div class="report-empty">리포트 없음 — 테스트 실행 후 리포트가 여기에 표시됩니다.</div></div>
            <div class="report-pager"><button id="report-prev" disabled>이전</button><span id="report-page">1 / 1</span><button id="report-next" disabled>다음</button></div>
          </section>
          <section class="report-panel report-preview">
            <div class="report-panel-head"><strong id="report-preview-title">미리보기</strong><button id="report-close" style="display:none" onclick="closeReport()">닫기</button></div>
            <div class="report-iframe-wrap" id="report-iframe-wrap" style="display:none"><iframe id="report-iframe" title="리포트 미리보기"></iframe></div>
            <div class="report-empty report-preview-empty" id="report-preview-empty">왼쪽에서 리포트를 열어 확인하세요.</div>
          </section>
        </div>
      </div>
    </div>

    <!-- 실행 히스토리 -->
    <div class="card history-card" id="view-history">
      <div class="history-toolbar">
        <button class="history-reset" type="button" onclick="resetHistory()">▣ 이력 초기화</button>
      </div>
      <div class="history-kpis">
        <div class="history-kpi"><div class="history-kpi-label">총 실행 수</div><div class="history-kpi-value" id="history-total">1</div></div>
        <div class="history-kpi"><div class="history-kpi-label">평균 PASS RATE</div><div class="history-kpi-value pass" id="history-rate">100%</div></div>
        <div class="history-kpi"><div class="history-kpi-label">FIRST PASS</div><div class="history-kpi-value pass" id="history-first">1<span class="history-kpi-suffix">/1</span></div></div>
        <div class="history-kpi"><div class="history-kpi-label">총 힐링 횟수</div><div class="history-kpi-value accent" id="history-heal">0</div></div>
      </div>
      <div class="history-filters">
        <span class="history-filter-label">유형</span>
        <button class="history-filter active" type="button" data-filter-kind="type" data-filter-value="all">전체</button>
        <button class="history-filter" type="button" data-filter-kind="type" data-filter-value="pipeline">파이프라인 실행</button>
        <button class="history-filter" type="button" data-filter-kind="type" data-filter-value="quick">빠른 실행</button>
        <span class="history-filter-label" style="margin-left:6px">그룹</span>
        <button class="history-filter group active" type="button" data-filter-kind="group" data-filter-value="all">전체 그룹</button>
        <button class="history-filter group" type="button" data-filter-kind="group" data-filter-value="customer_login">customer_login</button>
        <button class="history-filter group" type="button" data-filter-kind="group" data-filter-value="partner_login">partner_login</button>
        <span class="history-filter-label" style="margin-left:6px">플랫폼</span>
        <button class="history-filter platform-filter active" type="button" data-filter-kind="platform" data-filter-value="all">전체</button>
        <button class="history-filter platform-filter" type="button" data-filter-kind="platform" data-filter-value="android">Android</button>
        <button class="history-filter platform-filter" type="button" data-filter-kind="platform" data-filter-value="ios">iOS</button>
      </div>
      <div class="history-table">
        <div class="history-row header"><span>날짜</span><span>PASS RATE</span><span>통과 / 전체</span><span>유형</span><span>플랫폼</span><span>그룹</span><span>결과</span></div>
        <div id="history-list">
          <div class="history-row" data-history-type="quick" data-history-platform="android" data-history-groups="customer_login partner_login">
            <div class="history-date"><strong>2026-09-06<br>19:57:02</strong></div>
            <div><div class="history-pass">100%</div><div class="history-progress"><span></span></div></div>
            <div><span class="history-count">4<small> / 4</small></span><div style="color:var(--text3);font-size:11px;margin-top:3px">10s</div></div>
            <div><span class="history-type">빠른 실행</span></div>
            <div><span class="history-platform android">🤖 Android</span></div>
            <div class="history-groups"><span class="history-group">customer_login</span><span class="history-group">partner_login</span></div>
            <div><span class="history-result">First Pass</span></div>
          </div>
        </div>
      </div>
    </div>

    <!-- 컨피그 작성 가이드 -->
    <div class="card" id="view-config">
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
</main>
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

function getTcFolders(){
  return Array.from(document.querySelectorAll('input[name="tc-folder"]:checked')).map(function(el){ return el.value; });
}
function getTcFolder(){
  return getTcFolders()[0] || '';
}
async function refreshOverview(){
  try{
    var results=await Promise.all([
      fetch('/api/state').then(function(r){return r.json();}).catch(function(){return {}; }),
      fetch('/api/status').then(function(r){return r.json();}).catch(function(){return {}; }),
      fetch('/api/generated').then(function(r){return r.json();}).catch(function(){return []; }),
      fetch('/api/run_log',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({log:'run_execute.txt'})}).then(function(r){return r.json();}).catch(function(){return {}; })
    ]);
    var state=results[0]||{}, status=results[1]||{}, generated=results[2]||[], log=results[3]||{};
    var summary=(state.execute_results||{}).summary||{};
    var total=summary.total||0, passed=summary.passed||0, failed=summary.failed||0;
    var rate=total?Math.round(passed/total*100):0;
    var set=function(id,value){var el=document.getElementById(id);if(el)el.textContent=value;};
    set('overview-rate',rate+'%');
    set('overview-total',total);
    set('overview-passed',passed);
    set('overview-failed',failed);
    set('overview-appium',status.appium?'연결됨':'미기동');
    set('overview-healing',(state.heal_count||0)+'회');
    set('overview-generated',generated.reduce(function(n,g){return n+(g.count||0);},0)+'개');
    var donut=document.getElementById('overview-donut-fill');
    if(donut) donut.setAttribute('stroke-dasharray',(302*rate/100)+' 302');
    set('overview-context',total?'최근 '+(state.platform==='ios'?'iOS':'Android')+' 실행':'최근 실행 없음');
    set('overview-log',log.log||'로그 없음');
    var trend=document.getElementById('overview-trend');
    if(trend){
      trend.className=total?'overview-trend-chart':'overview-trend-empty';
      trend.innerHTML=(total
        ? '<svg viewBox="0 0 320 150" preserveAspectRatio="none"><line x1="18" y1="28" x2="302" y2="28" stroke="rgba(140,120,220,.08)"/><line x1="18" y1="74" x2="302" y2="74" stroke="rgba(140,120,220,.08)"/><line x1="18" y1="120" x2="302" y2="120" stroke="rgba(140,120,220,.08)"/><polyline points="18,120 95,95 175,72 250,42 302,28" fill="none" stroke="var(--accent)" stroke-width="2"/><circle cx="302" cy="28" r="4" fill="var(--pass)" style="filter:drop-shadow(0 0 4px var(--pass))"/><text x="302" y="17" text-anchor="end" fill="var(--pass)" font-size="10">'+rate+'%</text><text x="18" y="143" fill="var(--text3)" font-size="9">최근 실행</text><text x="302" y="143" text-anchor="end" fill="var(--text3)" font-size="9">First Pass</text></svg>'
        : '<div class="overview-trend-empty-message">실행 이력 없음</div>')
        +'<div class="overview-trend-footer"><span>실행 추이</span><span class="overview-trend-legend"><span class="overview-legend-item"><i class="overview-legend-dot" style="background:var(--pass)"></i>100%</span><span class="overview-legend-item"><i class="overview-legend-dot" style="background:var(--warn)"></i>80%↑</span><span class="overview-legend-item"><i class="overview-legend-dot" style="background:var(--fail)"></i>80%↓</span></span></div>';
    }
  }catch(_){
    // Dashboard remains usable when an optional status/log endpoint is unavailable.
  }
}
function toggleAllTcFolders(checked){
  document.querySelectorAll('input[name="tc-folder"]').forEach(function(el){ el.checked=checked; });
  updateTcFolderCount();
}
function updateTcFolderCount(){
  var selected=getTcFolders(), el=document.getElementById('tc-folder-count');
  if(el) el.textContent=selected.length ? selected.length+'개 폴더를 선택한 순서대로 직렬 실행합니다.' : '실행할 폴더를 선택하세요.';
}

function selectView(view, item){
  document.querySelectorAll('.sidebar-item').forEach(function(el){
    el.classList.toggle('active', el === item);
  });
  var grid=document.querySelector('.grid');
  var pipeline=document.getElementById('view-pipeline');
  var overview=document.getElementById('view-overview');
  var rightViews=['tests','import','reports','history','config'];
  if(!grid || !pipeline) return;
  if(overview) overview.classList.toggle('view-hidden', view !== 'dashboard');
  grid.classList.toggle('view-hidden', view === 'dashboard');
  grid.classList.remove('focus-left','focus-right');
  pipeline.classList.remove('view-hidden');
  document.querySelectorAll('.right-panel > .card').forEach(function(card){
    card.classList.toggle('view-hidden', view !== 'dashboard' && card.id !== 'view-'+view);
  });
  if(view === 'pipeline') grid.classList.add('focus-left');
  if(rightViews.indexOf(view) !== -1) grid.classList.add('focus-right');
  var main = document.querySelector('.app-main');
  if(main) main.classList.toggle('dashboard-view', view === 'dashboard');
  document.body.classList.toggle('quick-mode', view === 'tests');
  document.body.classList.toggle('report-mode', view === 'reports');
  document.body.classList.toggle('dashboard-mode', view === 'dashboard');
  if(main) main.classList.toggle('report-view', view === 'reports');
  if(main) main.classList.toggle('quick-view', view === 'tests');
  if(main) main.classList.toggle('history-view', view === 'history');
  if(view === 'dashboard') refreshOverview();
  if(main) main.scrollTo({top:0, behavior:'smooth'});
}

function resetHistory(){
  if(!window.confirm('실행 히스토리를 초기화할까요?')) return;
  document.getElementById('history-total').textContent='0';
  document.getElementById('history-rate').textContent='0%';
  document.getElementById('history-first').innerHTML='0<span class="history-kpi-suffix">/0</span>';
  document.getElementById('history-heal').textContent='0';
  document.getElementById('history-list').innerHTML='<div class="history-empty">실행 이력이 없습니다.</div>';
  document.querySelectorAll('.history-filter').forEach(function(btn){btn.classList.toggle('active',btn.dataset.filterValue==='all');});
}

document.addEventListener('click', function(e){
  if(e.target && e.target.classList.contains('history-filter')){
    var kind=e.target.dataset.filterKind;
    var selector=kind==='platform' ? '.history-filter.platform-filter' : kind==='group' ? '.history-filter.group' : '.history-filter:not(.group):not(.platform-filter)';
    e.target.parentElement.querySelectorAll(selector).forEach(function(btn){btn.classList.remove('active');});
    e.target.classList.add('active');
    document.querySelectorAll('.history-row:not(.header)').forEach(function(row){
      var typeBtn=document.querySelector('.history-filter[data-filter-kind="type"].active');
      var groupBtn=document.querySelector('.history-filter[data-filter-kind="group"].active');
      var platformBtn=document.querySelector('.history-filter[data-filter-kind="platform"].active');
      var groups=(row.dataset.historyGroups||'').split(' ');
      var visible=(!typeBtn||typeBtn.dataset.filterValue==='all'||row.dataset.historyType===typeBtn.dataset.filterValue)
        &&(!groupBtn||groupBtn.dataset.filterValue==='all'||groups.indexOf(groupBtn.dataset.filterValue)!==-1)
        &&(!platformBtn||platformBtn.dataset.filterValue==='all'||row.dataset.historyPlatform===platformBtn.dataset.filterValue);
      row.style.display=visible?'':'none';
    });
  }
});

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
      + '<span style="font-size:11px;color:rgba(255,255,255,.45)">'+STEP_LABEL[s]+'</span>'
      + '</div>';
    if(i < STEP_ORDER.length - 1){
      var lineColor = (_stepState[STEP_ORDER[i]]==='done') ? '#10b981' : 'rgba(255,255,255,.1)';
      html += '<div style="flex:1;height:2px;background:'+lineColor+';margin-bottom:14px;margin-top:7px"></div>';
    }
  });
  html += '<span style="font-size:12px;color:#8c87a8;margin-left:8px;white-space:nowrap">'+doneCount+'/5</span>';
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

async function resetDashboard(){
  if(!window.confirm('실행 중인 파이프라인을 중지하고 상태를 초기화할까요?')) return;
  var btn=document.getElementById('reset-btn');
  if(btn){ btn.disabled=true; btn.textContent='초기화 중...'; }
  try{
    var res=await fetch('/api/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    var data=await res.json();
    if(!data.ok) throw new Error(data.error||'초기화 실패');
    if(_pollTimer){ clearInterval(_pollTimer); _pollTimer=null; }
    _currentStep=null; _runAllActive=false;
    STEP_ORDER.forEach(function(step){ _stepState[step]='idle'; setStepNum(step,''); });
    hideFails(); closeReport(); clearLog(); renderProgressBar(); updateStepLocks();
    var healRow=document.getElementById('heal-row');
    var healCount=document.getElementById('heal-cnt');
    if(healRow) healRow.style.display='none';
    if(healCount) healCount.textContent='';
    await Promise.all([refreshStatus(),refreshGenerated(),refreshReports(),refreshTcFolders()]);
    setLog('대시보드 상태가 초기화되었습니다.\n새 실행을 시작할 수 있습니다.');
  }catch(err){
    setLog('초기화 실패: '+err.message);
  }finally{
    if(btn){ btn.disabled=false; btn.textContent='↺ 리셋'; }
  }
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
  var tcFolders = getTcFolders();
  if(!tcFolders.length){ setLog('[안내] 실행할 TC 폴더를 하나 이상 선택하세요.'); _finishRunAll(false); return; }

  try {
    var res = await fetch('/api/run_all', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({platform: platform, tc_folders: tcFolders})
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
    updateAutomationStatus(platform);
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
    var noDevTxt = '디바이스 없음';
    if(st.device_count>0){ dD.className='dot on'; tD.textContent=st.devices.join(', '); }
    else{ dD.className='dot off'; tD.textContent=noDevTxt; }

    document.getElementById('txt-step').textContent=state.step||'init';

    var hc=state.heal_count||0;
    var hr=document.getElementById('heal-row');
    if(hc>0){
      hr.style.display='flex';
      document.getElementById('heal-cnt').textContent=hc;
    }else{
      hr.style.display='none';
      document.getElementById('heal-cnt').textContent='';
    }

    // 최초 로드 시 pipeline.json 플랫폼으로 라디오 동기화
    if(state.platform && _initialPlatformSync){
      var r=document.getElementById('radio-'+state.platform);
      var changed = r && !r.checked;
      if(r) r.checked=true;
      _initialPlatformSync = false;
      updateAutomationStatus(state.platform);
      if(changed) setTimeout(refreshStatus, 0);
    }
  }catch(_){}
}

function updateAutomationStatus(platform){
  var el=document.getElementById('txt-automation');
  if(!el) return;
  if(platform === 'ios'){
    el.textContent='자동화: XCUITest';
    el.title='iOS · XCUITest · Simulator / 실기기';
  }else{
    el.textContent='자동화: ADB';
    el.title='Android · ADB · UiAutomator2';
  }
}

// 라디오 버튼 변경 시 즉시 상태 갱신
document.addEventListener('change', function(e){
  if(e.target && e.target.name === 'platform'){
    updateAutomationStatus(e.target.value);
    refreshStatus();
  }
});

async function refreshGenerated(){
  try{
    var res=await fetch('/api/generated'); var data=await res.json();
    window._generatedTests = data;
    var allHtml='', andHtml='', iosHtml='';
    data.forEach(function(g){
      var badge='<span class="gen-badge '+g.platform+'">'+(g.platform==='android'?'🤖':'🍎')+' '+g.platform+'</span>';
      var block='<div class="gen-item"><div>'+badge+'<span class="gen-count">'+g.count+'개 파일</span></div></div>';
      block+=g.files.map(function(file){
        var key=g.platform+':'+file.split('/')[0];
        return '<label class="quick-group-item"><input type="checkbox" class="quick-group-cb" value="'+esc(key)+'" checked>'
          +'<span class="quick-group-name">'+esc(key)+'</span><span class="quick-group-count">1개 파일</span></label>';
      }).join('');
      allHtml+=block;
      if(g.platform==='android') andHtml+=block;
      if(g.platform==='ios') iosHtml+=block;
    });
    var groupMap={};
    data.forEach(function(g){ g.files.forEach(function(file){ var key=g.platform+':'+file.split('/')[0]; (groupMap[key]||(groupMap[key]=[])).push({platform:g.platform,file:file}); }); });
    var groups=Object.keys(groupMap);
    var folderHtml=groups.map(function(key){ return '<label class="quick-group-item"><input type="checkbox" class="quick-group-cb" value="'+esc(key)+'" checked onchange="syncQuickSelection()">'
      +'<span class="quick-group-name">'+esc(key.split(':').slice(1).join(':'))+'</span><span class="quick-group-count">'+groupMap[key].length+'개 파일</span></label>'; }).join('');
    var quickHtml='<div class="quick-view-title">빠른 실행</div><p class="quick-view-subtitle">tests/generated/ 에 이미 생성된 테스트 코드를 바로 실행합니다. 전체 파이프라인을 거치지 않습니다.</p>'
      +'<div class="quick-select-card"><div class="quick-select-head"><span>테스트 폴더 선택</span><label><input type="checkbox" id="quick-select-all" checked onchange="quickToggleGenerated(this.checked)"> 전체 선택</label></div>'
      +'<div class="quick-group-list">'+(folderHtml||'<div class="tc-folder-empty">생성된 테스트 폴더가 없습니다.</div>')+'</div>'
      +'<div class="quick-action-row"><button class="quick-run-action" id="quick-generated-run" onclick="runSelectedGenerated()" '+(!groups.length?'disabled':'')+'>테스트 실행</button><label><input type="checkbox" id="generated-heal"> 힐링 생략</label></div></div>'
      +'<div id="quick-generated-log" class="quick-log" style="display:none"></div><div id="quick-generated-result"></div>';
    document.getElementById('gen-all').innerHTML=quickHtml||'<div class="empty">없음</div>';
    document.getElementById('gen-android').innerHTML=andHtml||'<div class="empty">없음</div>';
    document.getElementById('gen-ios').innerHTML=iosHtml||'<div class="empty">없음</div>';
  }catch(_){}
}

async function refreshImportFiles(){
  try{
    var res=await fetch('/api/import/files'); var data=await res.json();
    var sel=document.getElementById('import-file'); if(!sel) return;
    var current=sel.value;
    sel.innerHTML='<option value="">Excel 파일 선택</option>';
    (data.files||[]).forEach(function(name){
      var opt=document.createElement('option'); opt.value=name; opt.textContent=name;
      if(name===current) opt.selected=true; sel.appendChild(opt);
    });
  }catch(_){ }
}

function quickToggleGenerated(checked){
  document.querySelectorAll('.quick-group-cb').forEach(function(cb){ cb.checked=checked; });
}
function syncQuickSelection(){
  var all=document.querySelectorAll('.quick-group-cb'), selected=document.querySelectorAll('.quick-group-cb:checked');
  var toggle=document.getElementById('quick-select-all');
  if(toggle) toggle.checked=all.length>0 && all.length===selected.length;
}

async function runSelectedGenerated(){
  var keys=Array.from(document.querySelectorAll('.quick-group-cb:checked')).map(function(cb){return cb.value;});
  var all=(window._generatedTests||[]), files=[];
  all.forEach(function(g){ g.files.forEach(function(file){ if(keys.indexOf(g.platform+':'+file.split('/')[0])!==-1) files.push({platform:g.platform,file:file}); }); });
  if(!files.length){ setLog('[안내] 실행할 테스트 폴더를 선택하세요.'); return; }
  var btn=document.getElementById('quick-generated-run'); if(btn){btn.disabled=true;btn.textContent='실행 중...';}
  var noHeal=document.getElementById('generated-heal')?.checked === true;
  var passed=0, failed=0, done=0, groupStats={};
  var logEl=document.getElementById('quick-generated-log'), resultEl=document.getElementById('quick-generated-result');
  if(logEl){logEl.style.display='block';logEl.textContent='';}
  if(resultEl) resultEl.innerHTML='';
  for(var i=0;i<files.length;i++){
    var item=files[i];
    var groupKey=item.platform+':'+item.file.split('/')[0];
    groupStats[groupKey] = groupStats[groupKey] || {total:0,passed:0,failed:0};
    groupStats[groupKey].total++;
    if(logEl) logEl.textContent+='['+(i+1)+'/'+files.length+'] '+item.platform+'/'+item.file+'\\n';
    var result=await executeGeneratedFile(item.platform,item.file,!noHeal);
    if(result.ok && result.exit_code===0){ passed++; groupStats[groupKey].passed++; } else { failed++; groupStats[groupKey].failed++; } done++;
  }
  var rate=done?Math.round(passed/done*100):0;
  var groupRows=Object.keys(groupStats).map(function(key){ var g=groupStats[key], ok=g.failed===0;
    return '<div class="quick-group-result"><span>▸ <i class="quick-result-dot '+(ok?'pass':'fail')+'"></i> '+esc(key.split(':').slice(1).join(':').toUpperCase())+'</span><span>'+g.passed+'/'+g.total+' passed <b class="'+(ok?'pass-text':'fail-text')+'">'+(ok?'PASS':'FAIL')+'</b></span></div>'; }).join('');
  if(resultEl) resultEl.innerHTML='<div class="quick-result-card"><div class="quick-result-head"><span>실행 결과</span><span class="quick-result-badge '+(failed?'fail':'pass')+'">'+(failed?'FAILED':'ALL PASS')+'</span></div>'
    +'<div class="quick-result-stats"><div><b>'+done+'</b><small>TOTAL</small></div><div><b class="pass-text">'+passed+'</b><small>PASSED</small></div><div><b class="fail-text">'+failed+'</b><small>FAILED</small></div><div><b class="'+(failed?'fail-text':'pass-text')+'">'+rate+'%</b><small>PASS RATE</small></div></div>'
    +'<div class="quick-group-results">'+groupRows+'</div>'
    +'<div class="quick-result-meta">실행: '+new Date().toLocaleString('ko-KR')+' | 힐링: '+(noHeal?'생략':'사용')+'</div></div>';
  if(btn){btn.disabled=false;btn.textContent='테스트 실행';}
}

async function runGeneratedFile(platform, file){
  var noHeal=document.getElementById('generated-heal')?.checked === true;
  return executeGeneratedFile(platform,file,!noHeal);
}
function executeGeneratedFile(platform,file,heal){
  return new Promise(async function(resolve){
    try{
    var res=await fetch('/api/run_test',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({platform:platform,test_file:file,heal:heal})});
    var data=await res.json();
    if(!data.ok){ setLog('[오류] '+(data.error||'실행 실패')); resolve({ok:false,exit_code:1}); return; }
    var logName=data.log;
    var timer=setInterval(async function(){
    try{
      var res=await fetch('/api/run_log',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({log:logName})});
      var data=await res.json();
      if(data.ok) setLog(data.log||'실행 중...');
      if(data.done){ clearInterval(timer); refreshStatus(); refreshReports(); refreshGenerated(); resolve(data); }
    }catch(_){ }
    },1000);
    }catch(err){ setLog('[요청 실패] '+err.message); resolve({ok:false,exit_code:1}); }
  });
}

async function uploadImportFile(input){
  var file=input.files && input.files[0]; if(!file) return;
  var result=document.getElementById('import-result');
  try{
    var dataUrl=await new Promise(function(resolve,reject){
      var reader=new FileReader(); reader.onload=function(){resolve(reader.result)}; reader.onerror=reject;
      reader.readAsDataURL(file);
    });
    var res=await fetch('/api/import/upload',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name:file.name,data:dataUrl.split(',')[1]})});
    var data=await res.json(); if(!data.ok) throw new Error(data.error||'업로드 실패');
    result.textContent='업로드 완료: '+file.name; result.style.color='var(--pass)';
    await refreshImportFiles(); document.getElementById('import-file').value=file.name;
    await loadImportSheets();
  }catch(err){ result.textContent='업로드 실패: '+err.message; result.style.color='var(--fail)'; }
}

async function loadImportSheets(){
  var file=document.getElementById('import-file').value, sel=document.getElementById('import-sheet');
  if(!file){ sel.innerHTML='<option value="">시트 선택</option>'; return; }
  try{
    var res=await fetch('/api/import/sheets?file='+encodeURIComponent(file)); var data=await res.json();
    sel.innerHTML='<option value="">시트 선택</option>';
    (data.sheets||[]).forEach(function(sheet){
      var opt=document.createElement('option'); opt.value=sheet.name; opt.textContent=sheet.name+' ('+sheet.count+'건)'; sel.appendChild(opt);
    });
  }catch(_){ sel.innerHTML='<option value="">시트 조회 실패</option>'; }
}

async function convertImport(){
  var file=document.getElementById('import-file').value, sheet=document.getElementById('import-sheet').value;
  var platforms=Array.from(document.querySelectorAll('input[name="import-platform"]:checked')).map(function(el){return el.value});
  var result=document.getElementById('import-result');
  if(!file||!sheet||!platforms.length){ result.textContent='Excel 파일, 시트, 플랫폼을 선택하세요.'; return; }
  try{
    var res=await fetch('/api/import/convert',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({file:file,sheet:sheet,platforms:platforms})});
    var data=await res.json(); if(!data.ok) throw new Error(data.error||'변환 실패');
    result.style.color='var(--pass)'; result.textContent=data.count+'개 Markdown 생성 완료\n'+data.files.join('\n');
    refreshTcFolders(); refreshGenerated();
  }catch(err){ result.style.color='var(--fail)'; result.textContent='변환 실패: '+err.message; }
}

var _reports=[], _reportSelected=new Set(), _reportPage=1, _reportSort='newest', _reportSearch='';
function renderReports(){
  var list=document.getElementById('report-list'); if(!list) return;
  var filtered=_reports.filter(function(r){return r.name.toLowerCase().includes(_reportSearch.toLowerCase());}).sort(function(a,b){
    if(_reportSort==='name') return a.name.localeCompare(b.name);
    var d=new Date(b.modified_at)-new Date(a.modified_at); return _reportSort==='oldest'?-d:d;
  });
  var pages=Math.max(1,Math.ceil(filtered.length/8)); _reportPage=Math.min(_reportPage,pages);
  var pageItems=filtered.slice((_reportPage-1)*8,_reportPage*8);
  list.innerHTML=pageItems.map(function(r){return '<div class="report-item" data-name="'+esc(r.name)+'"><input type="checkbox" '+(_reportSelected.has(r.name)?'checked':'')+' onchange="toggleReportSelection(this.dataset.name,this.checked)" data-name="'+esc(r.name)+'"><div class="report-info"><div class="report-name" title="'+esc(r.name)+'">'+esc(r.name)+'</div><div class="report-meta">'+new Date(r.modified_at).toLocaleString('ko-KR')+' · '+Math.round(r.size/1024)+' KB</div></div><div class="report-actions"><button onclick="showReport(this.closest(\'.report-item\').dataset.name)">열기</button><a href="/reports/'+encodeURIComponent(r.name)+'" target="_blank">새 탭</a><button class="report-danger" onclick="deleteReports([this.closest(\'.report-item\').dataset.name])">삭제</button></div></div>';}).join('')||'<div class="report-empty">검색 결과가 없습니다.</div>';
  document.getElementById('report-count').textContent=filtered.length+'개 리포트';
  document.getElementById('report-selection-count').textContent=_reportSelected.size+'개 선택';
  document.getElementById('report-page').textContent=_reportPage+' / '+pages;
  document.getElementById('report-prev').disabled=_reportPage<=1; document.getElementById('report-next').disabled=_reportPage>=pages;
  var all=document.getElementById('report-select-all'); all.checked=!!filtered.length && filtered.every(function(r){return _reportSelected.has(r.name);}); all.indeterminate=filtered.some(function(r){return _reportSelected.has(r.name);})&&!all.checked;
}
async function refreshReports(){try{var res=await fetch('/api/reports');_reports=await res.json();renderReports();}catch(_){} }
function toggleReportSelection(name,checked){if(checked)_reportSelected.add(name);else _reportSelected.delete(name);renderReports();}
function showReport(name){var frame=document.getElementById('report-iframe'),wrap=document.getElementById('report-iframe-wrap'),empty=document.getElementById('report-preview-empty'),title=document.getElementById('report-preview-title'),close=document.getElementById('report-close');if(!frame||!wrap)return;frame.src='/reports/'+encodeURIComponent(name);wrap.style.display='block';empty.style.display='none';title.textContent=name;close.style.display='block';document.querySelectorAll('.report-item').forEach(function(r){r.classList.toggle('is-open',r.dataset.name===name);});}
function closeReport(){var frame=document.getElementById('report-iframe'),wrap=document.getElementById('report-iframe-wrap'),empty=document.getElementById('report-preview-empty'),title=document.getElementById('report-preview-title'),close=document.getElementById('report-close');if(frame)frame.src='';if(wrap)wrap.style.display='none';if(empty)empty.style.display='flex';if(title)title.textContent='미리보기';if(close)close.style.display='none';}
function reportConfirmDelete(names){
  return new Promise(function(resolve){
    var dialog=document.createElement('dialog'); dialog.className='report-delete-dialog';
    dialog.innerHTML='<form method="dialog"><h2>리포트 삭제</h2><p>'+(names.length===1?esc(names[0]):names.length+'개 리포트')+'를 삭제하시겠습니까?<br>삭제한 리포트는 복구할 수 없습니다.</p><div class="report-dialog-actions"><button value="cancel" autofocus>취소</button><button value="delete" class="report-danger">삭제</button></div></form>';
    dialog.addEventListener('close',function(){var ok=dialog.returnValue==='delete';dialog.remove();resolve(ok);},{once:true});
    document.body.appendChild(dialog); dialog.showModal();
  });
}
async function deleteReports(names){if(!names.length||!(await reportConfirmDelete(names)))return;try{var res=await fetch('/api/reports/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({names:names})});var data=await res.json();if(!res.ok||!data.ok)throw new Error(data.error||'삭제 실패');names.forEach(function(n){_reportSelected.delete(n);});refreshReports();closeReport();}catch(e){alert(e.message);}}
function initReportControls(){
  var search=document.getElementById('report-search-input'), sort=document.getElementById('report-sort');
  if(search) search.oninput=function(){_reportSearch=this.value;_reportPage=1;renderReports();};
  if(sort) sort.onchange=function(){_reportSort=this.value;_reportPage=1;renderReports();};
  document.getElementById('report-refresh').onclick=function(){refreshReports();};
  document.getElementById('report-delete-selected').onclick=function(){deleteReports(Array.from(_reportSelected));};
  document.getElementById('report-select-all').onchange=function(){var q=_reports.filter(function(r){return r.name.toLowerCase().includes(_reportSearch.toLowerCase());});q.forEach(function(r){this.checked?_reportSelected.add(r.name):_reportSelected.delete(r.name);},this);renderReports();};
  document.getElementById('report-prev').onclick=function(){_reportPage--;renderReports();};document.getElementById('report-next').onclick=function(){_reportPage++;renderReports();};
}

// ── TC 폴더 목록 ─────────────────────────────────────────────
async function refreshTcFolders(){
  try{
    var res = await fetch('/api/tc-folders');
    var data = await res.json();
    var list = document.getElementById('tc-folder-list');
    if(!list) return;
    var selected = getTcFolders();
    var folders = data.folders||[];
    list.innerHTML = folders.length ? folders.map(function(f){
      var checked = selected.length ? selected.indexOf(f)!==-1 : true;
      return '<label class="tc-folder-option"><input type="checkbox" name="tc-folder" value="'+esc(f)+'" '+(checked?'checked':'')+' onchange="updateTcFolderCount()"><span>'+esc(f)+'/</span></label>';
    }).join('') : '<div class="tc-folder-empty">생성된 TC 폴더가 없습니다.</div>';
    updateTcFolderCount();
  }catch(_){}
}

// ── 초기화 ───────────────────────────────────────────────────
(async function init(){
  initReportControls();
  renderProgressBar();
  updateStepLocks();
  refreshOverview();
  await Promise.all([refreshStatus(),refreshGenerated(),refreshReports(),refreshTcFolders(),refreshImportFiles()]);
  setInterval(refreshStatus, 6000);
  setInterval(refreshGenerated, 10000);
  setInterval(refreshReports, 15000);
  setInterval(refreshTcFolders, 15000);
  setInterval(refreshImportFiles, 15000);
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
            "/api/import/files": self._get_import_files,
            "/api/import/sheets": self._get_import_sheets,
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
            "/api/run_test":  self._post_run_test,
            "/api/reports/delete": self._post_reports_delete,
            "/api/cancel":     self._post_cancel,
            "/api/run_log":    self._post_run_log,
            "/api/reset":      self._post_reset,
            "/api/import/convert": self._post_import_convert,
            "/api/import/upload": self._post_import_upload,
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

    def _get_import_files(self):
        self._serve_json({"files": list_import_files()})

    def _get_import_sheets(self):
        from urllib.parse import parse_qs, urlparse
        filename = parse_qs(urlparse(self.path).query).get("file", [""])[0]
        if filename != Path(filename).name or not filename.endswith(".xlsx"):
            self._serve_json({"ok": False, "error": "허용되지 않은 Excel 파일명입니다"})
            return
        source = (IMPORT_DIR / filename).resolve()
        if not source.is_file() or not source.is_relative_to(IMPORT_DIR.resolve()):
            self._serve_json({"ok": False, "error": "Excel 파일을 찾을 수 없습니다"})
            return
        try:
            sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
            from import_excel import list_sheets
            self._serve_json({"ok": True, "sheets": list_sheets(source)})
        except Exception as exc:
            self._serve_json({"ok": False, "error": str(exc)})

    def _serve_file_from(self, base_dir: Path, name: str, content_type: str):
        if ".." in name:
            self.send_response(403); self.end_headers(); return
        fpath = base_dir / name
        if not fpath.is_file():
            if base_dir == REPORTS_DIR:
                fname = html_escape(name, quote=True)
                body = (
                    "<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
                    "<style>body{display:flex;align-items:center;justify-content:center;"
                    "height:100vh;margin:0;font-family:Inter,-apple-system,sans-serif;"
                    "background:#08071b;color:#b8b3d0}.box{text-align:center;padding:32px;"
                    "border:1px solid rgba(140,120,220,.12);border-radius:16px;"
                    "background:rgba(18,16,42,.55);backdrop-filter:blur(12px)}"
                    ".icon{font-size:44px;margin-bottom:16px}.title{font-size:16px;"
                    "font-weight:600;color:#f0eff5;margin-bottom:8px}.sub{font-size:12px;"
                    "color:rgba(184,179,208,.5);font-family:monospace;word-break:break-all;"
                    "max-width:320px}</style></head><body><div class='box'>"
                    "<div class='icon'>🗑️</div><div class='title'>리포트가 삭제되었습니다</div>"
                    f"<div class='sub'>{fname}</div></div></body></html>"
                ).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
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
        state.pop("last_fail_video", None)
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

    def _post_reports_delete(self):
        body = _read_body(self)
        names = body.get("names", [])
        if not isinstance(names, list) or not names:
            self._serve_json({"ok": False, "error": "삭제할 리포트를 선택하세요"}); return
        deleted, missing, failed = [], [], []
        base = REPORTS_DIR.resolve()
        for raw_name in names:
            name = str(raw_name)
            target = (base / name).resolve()
            if target.suffix != ".html" or not target.is_relative_to(base):
                failed.append({"name": name, "error": "invalid report path"}); continue
            if not target.is_file():
                missing.append(name); continue
            try:
                target.unlink()
                deleted.append(name)
            except OSError as exc:
                failed.append({"name": name, "error": str(exc)})
        self._serve_json({"ok": not failed, "deleted": deleted, "missing": missing, "failed": failed})

    def _post_run_test(self):
        """생성된 단일 테스트 파일 실행 및 선택적 힐링 재실행."""
        body = _read_body(self)
        platform = body.get("platform", "android")
        test_file = str(body.get("test_file", "")).strip()
        heal = bool(body.get("heal", True))
        if platform not in ("android", "ios") or not test_file or ".." in test_file or test_file.startswith("/"):
            self._serve_json({"ok": False, "error": "invalid test file or platform"}); return
        root = (GENERATED_DIR / platform).resolve()
        candidate = (root / test_file).resolve()
        if candidate.suffix != ".py" or not candidate.is_file() or not candidate.is_relative_to(root):
            self._serve_json({"ok": False, "error": "생성된 테스트 파일을 찾을 수 없습니다"}); return

        run_key = f"test:{platform}:{test_file}"
        log_name = "run_test_" + platform + "_" + test_file.replace("/", "_").replace("\\", "_").replace(".py", "") + ".txt"
        log_path = LOGS_DIR / log_name
        with _process_lock:
            old = _running.get(run_key)
            if old and old.poll() is None:
                self._serve_json({"ok": False, "error": "해당 테스트가 이미 실행 중입니다"}); return
            _test_runs[log_name] = {"key": run_key, "done": False, "returncode": None}

        def spawn(args, mode="a"):
            popen_opts = {"preexec_fn": os.setsid} if sys.platform != "win32" else {}
            with open(log_path, mode, encoding="utf-8") as log_file:
                proc = subprocess.Popen([PYTHON_BIN, "-u"] + args, cwd=str(PROJECT_ROOT),
                                        stdout=log_file, stderr=subprocess.STDOUT, **popen_opts)
            with _process_lock:
                _running[run_key] = proc
            proc.wait()
            return proc.returncode

        def run():
            execute_args = [str(PROJECT_ROOT / "scripts/05_execute.py"), "--platform", platform,
                            "--test-file", test_file]
            rc = spawn(execute_args, "w")
            if rc != 0 and heal:
                heal_args = [str(PROJECT_ROOT / "scripts/06_heal.py"), "--platform", platform]
                spawn(heal_args)
                spawn(execute_args)
            with _process_lock:
                _test_runs[log_name]["done"] = True
                _test_runs[log_name]["returncode"] = rc

        threading.Thread(target=run, daemon=True).start()
        self._serve_json({"ok": True, "pid": 0, "log": log_name, "heal": heal})

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
            test_meta = _test_runs.get(log_name)
            proc = _running.get(test_meta["key"]) if test_meta else _running.get(step)
        done = test_meta["done"] if test_meta else (proc is None or proc.poll() is not None)
        exit_code = test_meta["returncode"] if test_meta else (proc.returncode if (proc and proc.poll() is not None) else None)

        self._serve_json({"ok": True, "log": content, "done": done, "exit_code": exit_code})

    def _post_run_all(self):
        """선택한 TC 폴더들을 각각 analyze → generate → lint → execute 순서로 직렬 실행."""
        body = _read_body(self)
        platform = body.get("platform", "android")
        tc_folders = body.get("tc_folders")
        if not isinstance(tc_folders, list):
            legacy_folder = body.get("tc_folder", "").strip()
            tc_folders = [legacy_folder] if legacy_folder else [""]
        tc_folders = [str(folder).strip() for folder in tc_folders]

        if platform not in ("android", "ios"):
            self._serve_json({"ok": False, "error": "invalid platform"}); return
        available_folders = set(list_tc_folders())
        for tc_folder in tc_folders:
            if tc_folder and (".." in tc_folder or "/" in tc_folder or tc_folder not in available_folders):
                self._serve_json({"ok": False, "error": f"invalid tc_folder: {tc_folder}"}); return

        # pipeline.json에 플랫폼 저장
        state = read_state()
        state["platform"] = platform
        state.pop("last_fail_video", None)
        save_state(state)

        MAX_HEAL = 3
        PIPELINE = ["analyze", "generate", "lint", "execute"]

        def _spawn(step, folder="", extra=None, log_suffix=""):
            script_rel, extra_args_tmpl, log_name = SCRIPT_MAP[step]
            extra_args = [a.replace("{platform}", platform) for a in extra_args_tmpl]
            if step == "analyze" and platform == "ios":
                extra_args += ["--mode", "simulator"]
            if step in ("generate", "execute") and folder:
                extra_args += ["--tc-dir", folder]
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

        def _report_final_failure():
            """최종 실패를 이 프로젝트 전용 Jira 설정으로 보고한다."""
            reporter = PROJECT_ROOT / "scripts" / "jira_reporter.py"
            if not reporter.exists():
                return
            result = subprocess.run(
                [PYTHON_BIN, "-u", str(reporter), "--platform", platform],
                cwd=str(PROJECT_ROOT), capture_output=True, text=True,
            )
            if result.stdout:
                print(result.stdout.rstrip())
            if result.stderr:
                print(result.stderr.rstrip())

        def _run_pipeline(folder):
            # 1단계: analyze → generate → lint → execute
            for step in PIPELINE:
                rc, _ = _spawn(step, folder=folder)
                if rc != 0:
                    return  # 앞단계 실패 시 중단

            # 2단계: execute 결과 확인 → 실패 시 heal 최대 3회
            execute_ok = (read_state().get("execute_results", {})
                          .get("summary", {}).get("failed", 0) == 0)

            for heal_round in range(1, MAX_HEAL + 1):
                if execute_ok:
                    break

                log_sfx = f"_{heal_round}"

                if heal_round == MAX_HEAL:
                    # 마지막 회차: 영상 찍으면서 execute 재실행
                    rec_info = _record_video(f"heal{heal_round}")
                    _spawn("execute", folder=folder, log_suffix=f"_record{heal_round}")
                    if rec_info:
                        saved = _stop_video(rec_info)
                        if saved:
                            st = read_state()
                            st["last_fail_video"] = str(saved)
                            save_state(st)
                    # 최종 실패 이후에만 Jira 이슈를 생성한다.
                    _report_final_failure()
                    break
                else:
                    # heal 실행
                    _spawn("heal", folder=folder, log_suffix=log_sfx)
                    # heal 후 execute 재실행
                    rc, _ = _spawn("execute", folder=folder, log_suffix=log_sfx)
                    execute_ok = (read_state().get("execute_results", {})
                                  .get("summary", {}).get("failed", 0) == 0)

        def _run_selected_folders():
            for folder in tc_folders:
                _run_pipeline(folder)

        threading.Thread(target=_run_selected_folders, daemon=True).start()
        self._serve_json({"ok": True, "folders": tc_folders, "mode": "serial",
                          "steps": PIPELINE + ["heal(x3)", "record"]})

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
        self._serve_json({"ok": True, "state": init})

    def _post_import_convert(self):
        body = _read_body(self)
        filename = str(body.get("file", "")).strip()
        sheet = str(body.get("sheet", "")).strip()
        platforms = body.get("platforms", ["android", "ios"])
        if not filename or not sheet or not isinstance(platforms, list):
            self._serve_json({"ok": False, "error": "file, sheet, platforms가 필요합니다"})
            return
        if filename != Path(filename).name or not filename.endswith(".xlsx"):
            self._serve_json({"ok": False, "error": "허용되지 않은 Excel 파일명입니다"})
            return
        source = (IMPORT_DIR / filename).resolve()
        if not source.is_file() or not source.is_relative_to(IMPORT_DIR.resolve()):
            self._serve_json({"ok": False, "error": "Excel 파일을 찾을 수 없습니다"})
            return
        try:
            sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
            from import_excel import convert_sheet
            created = convert_sheet(source, sheet, TESTCASES_DIR, platforms)
            self._serve_json({
                "ok": True,
                "count": len(created),
                "files": [str(path.relative_to(PROJECT_ROOT)) for path in created],
            })
        except Exception as exc:
            self._serve_json({"ok": False, "error": str(exc)})

    def _post_import_upload(self):
        body = _read_body(self)
        filename = str(body.get("name", "")).strip()
        encoded = str(body.get("data", "")).strip()
        if filename != Path(filename).name or not filename.lower().endswith(".xlsx"):
            self._serve_json({"ok": False, "error": "xlsx 파일만 업로드할 수 있습니다"})
            return
        if not encoded or len(encoded) > 30 * 1024 * 1024:
            self._serve_json({"ok": False, "error": "파일 크기는 20MB 이하이어야 합니다"})
            return
        try:
            content = base64.b64decode(encoded, validate=True)
        except Exception:
            self._serve_json({"ok": False, "error": "파일 데이터가 올바르지 않습니다"})
            return
        if len(content) > 20 * 1024 * 1024:
            self._serve_json({"ok": False, "error": "파일 크기는 20MB 이하이어야 합니다"})
            return
        (IMPORT_DIR / filename).write_bytes(content)
        self._serve_json({"ok": True, "file": filename, "size": len(content)})

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
