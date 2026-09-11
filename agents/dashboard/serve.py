"""
App QA Dashboard 서버 (FastAPI + Uvicorn).

Usage:
    python agents/dashboard/serve.py
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from html import escape as html_escape
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

PORT = 8767
HERE = Path(__file__).parent
PROJECT_ROOT = HERE.parent.parent

# Appium이 설치된 Python 탐색
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

STATE_PATH             = PROJECT_ROOT / "state" / "pipeline.json"
CAPTURE_SESSION_PATH   = PROJECT_ROOT / "state" / "capture_session.json"
REPORTS_DIR            = PROJECT_ROOT / "tests" / "reports"
GENERATED_DIR          = PROJECT_ROOT / "tests" / "generated"
SCREENSHOTS_DIR        = PROJECT_ROOT / "reports" / "screenshots"
IMPORT_DIR             = PROJECT_ROOT / "import"
LOGS_DIR               = PROJECT_ROOT / "logs"
CAPTURES_DIR           = PROJECT_ROOT / "state" / "captures"
TESTCASES_DIR          = PROJECT_ROOT / "testcases"

for d in (LOGS_DIR, REPORTS_DIR, SCREENSHOTS_DIR, IMPORT_DIR, CAPTURES_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── 동시성 제어 ───────────────────────────────────────────────
_state_lock   = threading.Lock()
_process_lock = threading.Lock()
_running: dict[str, subprocess.Popen] = {}
_test_runs: dict[str, dict] = {}

# ── WebSocket 연결 관리 (Action Timeline) ─────────────────────
_ws_connections: list[WebSocket] = []
_ws_lock = asyncio.Lock()


# ── 유틸 ─────────────────────────────────────────────────────

def load_json(path: Path) -> Any:
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
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "booted"],
            capture_output=True, text=True, timeout=5
        )
        devices = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("==") and not line.startswith("--"):
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


def list_generated(platform: str | None = None) -> list:
    if not GENERATED_DIR.exists():
        return []
    result = []
    for platform_dir in sorted(GENERATED_DIR.iterdir()):
        if not platform_dir.is_dir() or platform_dir.name.startswith("."):
            continue
        if platform and platform_dir.name != platform:
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
    return sorted(
        [
            {
                "name": file.name,
                "size": file.stat().st_size,
                "modified_at": datetime.fromtimestamp(file.stat().st_mtime).isoformat(),
            }
            for file in IMPORT_DIR.glob("*.xlsx")
            if file.is_file()
        ],
        key=lambda item: item["name"].lower(),
    )


def parse_failed_tcs(log_text: str) -> list:
    failures = []
    lines = log_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("FAILED "):
            tc = line.replace("FAILED ", "").split(" - ")[0].strip()
            error = line.split(" - ", 1)[1].strip() if " - " in line else ""
            failures.append({"tc": tc, "error": error})
        if "short test summary info" in line:
            for j in range(i + 1, min(i + 100, len(lines))):
                if lines[j].startswith("FAILED"):
                    tc = lines[j].replace("FAILED ", "").split(" - ")[0].strip()
                    error = lines[j].split(" - ", 1)[1].strip() if " - " in lines[j] else ""
                    entry = {"tc": tc, "error": error}
                    if entry not in failures:
                        failures.append(entry)
        i += 1
    seen = set()
    unique = []
    for f in failures:
        key = f["tc"]
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def list_tc_folders(platform: str | None = None) -> list[str]:
    if not TESTCASES_DIR.exists():
        return []
    if platform in ("android", "ios"):
        platform_dir = TESTCASES_DIR / platform
        return [platform] if platform_dir.is_dir() and any(platform_dir.rglob("tc_*.md")) else []
    return sorted([
        d.name for d in TESTCASES_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".") and list(d.glob("tc_*.md"))
    ])


# ── 스크립트 맵 ───────────────────────────────────────────────

SCRIPT_MAP = {
    "analyze":  ("scripts/01_analyze.py",  ["--platform", "{platform}"],                           "run_analyze.txt"),
    "generate": ("scripts/02_generate.py", ["--platform", "{platform}", "--strict-locators"],       "run_generate.txt"),
    "lint":     ("scripts/03_lint.py",     [],                                                     "run_lint.txt"),
    "execute":  ("scripts/05_execute.py",  ["--platform", "{platform}"],                           "run_execute.txt"),
    "heal":     ("scripts/06_heal.py",     ["--platform", "{platform}"],                           "run_heal.txt"),
}

# ── Capture Studio 세션 관리 ──────────────────────────────────

def load_capture_session() -> dict:
    return load_json(CAPTURE_SESSION_PATH) or {}


def save_capture_session(data: dict):
    CAPTURE_SESSION_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def is_capture_active() -> bool:
    """Capture Studio 세션이 활성 상태인지 확인."""
    session = load_capture_session()
    if not session.get("active"):
        return False
    # 30분 비활동 타임아웃 확인
    last_activity = session.get("last_activity_at", "")
    if last_activity:
        try:
            last_dt = datetime.fromisoformat(last_activity)
            elapsed = (datetime.now() - last_dt).total_seconds()
            if elapsed > 1800:  # 30분
                save_capture_session({**session, "active": False, "end_reason": "timeout"})
                return False
        except Exception:
            pass
    return True


def is_pipeline_active() -> bool:
    """파이프라인 실행 중인지 확인."""
    with _process_lock:
        return any(p.poll() is None for p in _running.values())


# ── FastAPI 앱 ────────────────────────────────────────────────

DASHBOARD_HTML = (HERE / "dashboard.html").read_text(encoding="utf-8")

app = FastAPI(title="QA Dashboard", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{PORT}"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WebSocket: Action Timeline ─────────────────────────────────

@app.websocket("/ws/timeline")
async def ws_timeline(websocket: WebSocket):
    await websocket.accept()
    async with _ws_lock:
        _ws_connections.append(websocket)
    try:
        while True:
            # 클라이언트에서 ping 메시지를 받아 연결 유지
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        async with _ws_lock:
            if websocket in _ws_connections:
                _ws_connections.remove(websocket)


async def _broadcast_timeline(event: dict):
    """연결된 모든 WebSocket 클라이언트에 Action Timeline 이벤트 전송."""
    message = json.dumps(event, ensure_ascii=False)
    async with _ws_lock:
        dead = []
        for ws in _ws_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_connections.remove(ws)


def broadcast_timeline_sync(event: dict):
    """동기 코드에서 WebSocket 브로드캐스트 호출 (threading)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(_broadcast_timeline(event), loop)
    except Exception:
        pass


# ── 기존 GET 엔드포인트 ───────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/api/state")
async def get_state():
    return JSONResponse(read_state())


@app.get("/api/status")
async def get_status(platform: str | None = None):
    appium_ok = check_appium_status()
    state = read_state()
    resolved_platform = platform or state.get("platform", "android")
    if resolved_platform == "ios":
        devices = check_ios_simulators()
    else:
        devices = check_android_devices()
    with _process_lock:
        running_steps = [s for s, p in _running.items() if p.poll() is None]
    return JSONResponse({
        "appium": appium_ok,
        "devices": devices,
        "device_count": len(devices),
        "running_steps": running_steps,
        "platform": resolved_platform,
        "capture_active": is_capture_active(),
    })


@app.get("/api/reports")
async def get_reports():
    return JSONResponse(list_reports())


@app.get("/api/generated")
async def get_generated(platform: str | None = None):
    if platform is not None and platform not in ("android", "ios"):
        return JSONResponse({"ok": False, "error": "invalid platform"}, status_code=400)
    return JSONResponse(list_generated(platform))


@app.get("/api/testcase")
async def get_testcase(platform: str = "", file: str = ""):
    if platform not in ("android", "ios") or not file:
        return JSONResponse({"ok": False, "error": "platform과 file이 필요합니다"}, status_code=400)

    from urllib.parse import unquote
    generated_file = unquote(file)
    generated_path = (GENERATED_DIR / platform / generated_file).resolve()
    generated_root = (GENERATED_DIR / platform).resolve()
    if (not generated_path.is_relative_to(generated_root)
            or generated_path.suffix != ".py"
            or generated_path.name.startswith(".")
            or not generated_path.is_file()):
        return JSONResponse({"ok": False, "error": "유효하지 않은 생성 테스트 파일입니다"}, status_code=400)

    testcase_path = (TESTCASES_DIR / platform / generated_path.relative_to(generated_root)).with_suffix(".md").resolve()
    testcase_root = (TESTCASES_DIR / platform).resolve()
    if not testcase_path.is_relative_to(testcase_root) or not testcase_path.is_file():
        return JSONResponse({"ok": False, "error": "대응하는 Markdown TC를 찾을 수 없습니다"}, status_code=404)
    return JSONResponse({
        "ok": True,
        "platform": platform,
        "file": str(testcase_path.relative_to(testcase_root)),
        "content": testcase_path.read_text(encoding="utf-8"),
    })


@app.get("/api/screenshots")
async def get_screenshots():
    return JSONResponse(list_screenshots())


@app.get("/api/tc-folders")
async def get_tc_folders(platform: str | None = None):
    if platform is not None and platform not in ("android", "ios"):
        return JSONResponse({"ok": False, "error": "invalid platform"}, status_code=400)
    return JSONResponse({"folders": list_tc_folders(platform)})


@app.get("/api/import/files")
async def get_import_files():
    return JSONResponse({"files": list_import_files()})


@app.get("/api/import/sheets")
async def get_import_sheets(file: str = ""):
    filename = file
    if filename != Path(filename).name or not filename.endswith(".xlsx"):
        return JSONResponse({"ok": False, "error": "허용되지 않은 Excel 파일명입니다"}, status_code=400)
    source = (IMPORT_DIR / filename).resolve()
    if not source.is_file() or not source.is_relative_to(IMPORT_DIR.resolve()):
        return JSONResponse({"ok": False, "error": "Excel 파일을 찾을 수 없습니다"}, status_code=404)
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from import_excel import list_sheets
        return JSONResponse({"ok": True, "sheets": list_sheets(source)})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.get("/reports/{name:path}")
async def serve_report(name: str):
    if ".." in name:
        return Response(status_code=403)
    fpath = REPORTS_DIR / name
    if not fpath.is_file():
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
        )
        return HTMLResponse(content=body, status_code=404)
    return FileResponse(str(fpath), media_type="text/html")


@app.get("/screenshots/{name:path}")
async def serve_screenshot(name: str):
    if ".." in name:
        return Response(status_code=403)
    fpath = SCREENSHOTS_DIR / name
    if not fpath.is_file():
        return Response(status_code=404)
    ext = fpath.suffix.lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
    return FileResponse(str(fpath), media_type=mime)


# ── 기존 POST 엔드포인트 ──────────────────────────────────────

@app.post("/api/run")
async def post_run(request: Request):
    body = await request.json()
    platform = body.get("platform", "android")
    step = body.get("step", "execute")
    tc_folder = body.get("tc_folder", "").strip()

    if platform not in ("android", "ios"):
        return JSONResponse({"ok": False, "error": "invalid platform"}, status_code=400)
    if step not in SCRIPT_MAP:
        return JSONResponse({"ok": False, "error": "invalid step"}, status_code=400)
    if tc_folder and (".." in tc_folder or "/" in tc_folder):
        return JSONResponse({"ok": False, "error": "invalid tc_folder"}, status_code=400)

    # Capture Studio 세션 충돌 방지
    if is_capture_active():
        return JSONResponse({"ok": False, "error": "Capture Studio 세션이 실행 중입니다. 먼저 Capture Studio를 종료하세요."}, status_code=409)

    with _process_lock:
        if step in _running and _running[step].poll() is None:
            return JSONResponse({"ok": False, "error": f"{step} 이미 실행 중입니다"}, status_code=409)

    state = read_state()
    state["platform"] = platform
    state.pop("last_fail_video", None)
    save_state(state)

    script_rel, extra_args_tmpl, log_name = SCRIPT_MAP[step]
    extra_args = [a.replace("{platform}", platform) for a in extra_args_tmpl]
    if step == "analyze" and platform == "ios":
        extra_args += ["--mode", "simulator"]
    if step == "generate" and tc_folder:
        extra_args += ["--tc-dir", tc_folder]
    if step == "execute" and tc_folder and tc_folder != platform:
        extra_args += ["--tc-dir", tc_folder]
    script = PROJECT_ROOT / script_rel

    if not script.exists():
        return JSONResponse({"ok": False, "error": f"{script_rel} 없음 (미구현)"}, status_code=404)

    log_path = LOGS_DIR / log_name
    extra_popen: dict = {}
    if sys.platform != "win32":
        extra_popen["preexec_fn"] = os.setsid
    with open(log_path, "w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            [PYTHON_BIN, "-u", str(script)] + extra_args,
            cwd=str(PROJECT_ROOT),
            stdout=log_file, stderr=subprocess.STDOUT,
            **extra_popen,
        )

    with _process_lock:
        _running[step] = proc

    def _wait(p):
        p.wait()
    threading.Thread(target=_wait, args=(proc,), daemon=True).start()

    return JSONResponse({"ok": True, "pid": proc.pid, "log": log_name})


@app.post("/api/run_all")
async def post_run_all(request: Request):
    body = await request.json()
    platform = body.get("platform", "android")
    tc_folders = body.get("tc_folders")
    if not isinstance(tc_folders, list):
        legacy_folder = body.get("tc_folder", "").strip()
        tc_folders = [legacy_folder] if legacy_folder else [""]
    tc_folders = [str(folder).strip() for folder in tc_folders]

    if platform not in ("android", "ios"):
        return JSONResponse({"ok": False, "error": "invalid platform"}, status_code=400)
    available_folders = set(list_tc_folders(platform))
    for tc_folder in tc_folders:
        if tc_folder and (".." in tc_folder or "/" in tc_folder or tc_folder not in available_folders):
            return JSONResponse({"ok": False, "error": f"invalid tc_folder: {tc_folder}"}, status_code=400)

    # Capture Studio 세션 충돌 방지
    if is_capture_active():
        return JSONResponse({"ok": False, "error": "Capture Studio 세션이 실행 중입니다. 먼저 Capture Studio를 종료하세요."}, status_code=409)

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
        if step == "generate" and folder:
            extra_args += ["--tc-dir", folder]
        if step == "execute" and folder and folder != platform:
            extra_args += ["--tc-dir", folder]
        if extra:
            extra_args += extra
        script = PROJECT_ROOT / script_rel
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

    def _record_video(suffix: str):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        vid_dir = PROJECT_ROOT / "reports" / "recordings"
        vid_dir.mkdir(parents=True, exist_ok=True)
        vid_path = vid_dir / f"fail_{platform}_{suffix}_{ts}.mp4"
        if platform == "ios":
            rec_proc = subprocess.Popen(
                ["xcrun", "simctl", "io", "booted", "recordVideo", "--codec=h264", str(vid_path)],
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
                [ADB_BIN, "-s", device_id, "shell", "screenrecord", "--time-limit", "300", "/sdcard/qa_fail.mp4"],
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
        for step in PIPELINE:
            rc, _ = _spawn(step, folder=folder)
            if rc != 0:
                return
        execute_ok = (read_state().get("execute_results", {})
                      .get("summary", {}).get("failed", 0) == 0)
        for heal_round in range(1, MAX_HEAL + 1):
            if execute_ok:
                break
            log_sfx = f"_{heal_round}"
            if heal_round == MAX_HEAL:
                rec_info = _record_video(f"heal{heal_round}")
                _spawn("execute", folder=folder, log_suffix=f"_record{heal_round}")
                if rec_info:
                    saved = _stop_video(rec_info)
                    if saved:
                        st = read_state()
                        st["last_fail_video"] = str(saved)
                        save_state(st)
                _report_final_failure()
                break
            else:
                _spawn("heal", folder=folder, log_suffix=log_sfx)
                rc, _ = _spawn("execute", folder=folder, log_suffix=log_sfx)
                execute_ok = (read_state().get("execute_results", {})
                              .get("summary", {}).get("failed", 0) == 0)

    def _run_selected_folders():
        for folder in tc_folders:
            _run_pipeline(folder)

    threading.Thread(target=_run_selected_folders, daemon=True).start()
    return JSONResponse({"ok": True, "folders": tc_folders, "mode": "serial",
                         "steps": PIPELINE + ["heal(x3)", "record"]})


@app.post("/api/run_test")
async def post_run_test(request: Request):
    body = await request.json()
    platform = body.get("platform", "android")
    test_file = str(body.get("test_file", "")).strip()
    test_folder = str(body.get("test_folder", "")).strip()
    heal = bool(body.get("heal", True))

    if platform not in ("android", "ios") or (not test_file and not test_folder):
        return JSONResponse({"ok": False, "error": "invalid test file or platform"}, status_code=400)

    root = (GENERATED_DIR / platform).resolve()
    if test_folder:
        if ".." in test_folder or test_folder.startswith("/") or "/" in test_folder.strip("/"):
            return JSONResponse({"ok": False, "error": "invalid test folder"}, status_code=400)
        candidate = (root / test_folder).resolve()
        if not candidate.is_dir() or not candidate.is_relative_to(root):
            return JSONResponse({"ok": False, "error": "생성된 테스트 폴더를 찾을 수 없습니다"}, status_code=404)
        run_target = test_folder
        run_key = f"folder:{platform}:{test_folder}"
        log_name = "run_test_" + platform + "_" + test_folder.replace("/", "_") + ".txt"
    else:
        if ".." in test_file or test_file.startswith("/"):
            return JSONResponse({"ok": False, "error": "invalid test file or platform"}, status_code=400)
        candidate = (root / test_file).resolve()
        if candidate.suffix != ".py" or not candidate.is_file() or not candidate.is_relative_to(root):
            return JSONResponse({"ok": False, "error": "생성된 테스트 파일을 찾을 수 없습니다"}, status_code=404)
        run_target = test_file
        run_key = f"test:{platform}:{test_file}"
        log_name = "run_test_" + platform + "_" + test_file.replace("/", "_").replace(".py", "") + ".txt"

    log_path = LOGS_DIR / log_name
    with _process_lock:
        old = _running.get(run_key)
        if old and old.poll() is None:
            return JSONResponse({"ok": False, "error": "해당 테스트가 이미 실행 중입니다"}, status_code=409)
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
        execute_args = [str(PROJECT_ROOT / "scripts/05_execute.py"), "--platform", platform]
        if test_folder:
            execute_args += ["--tc-dir", run_target]
        else:
            execute_args += ["--test-file", run_target]
        rc = spawn(execute_args, "w")
        if rc != 0 and heal:
            heal_args = [str(PROJECT_ROOT / "scripts/06_heal.py"), "--platform", platform]
            spawn(heal_args)
            spawn(execute_args)
        with _process_lock:
            _test_runs[log_name]["done"] = True
            _test_runs[log_name]["returncode"] = rc

    threading.Thread(target=run, daemon=True).start()
    return JSONResponse({"ok": True, "pid": 0, "log": log_name, "heal": heal})


@app.post("/api/reports/delete")
async def post_reports_delete(request: Request):
    body = await request.json()
    names = body.get("names", [])
    if not isinstance(names, list) or not names:
        return JSONResponse({"ok": False, "error": "삭제할 리포트를 선택하세요"}, status_code=400)
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
    return JSONResponse({"ok": not failed, "deleted": deleted, "missing": missing, "failed": failed})


@app.post("/api/cancel")
async def post_cancel(request: Request):
    body = await request.json()
    step = body.get("step", "")
    with _process_lock:
        proc = _running.get(step)
    if proc and proc.poll() is None:
        try:
            if sys.platform == "win32":
                proc.terminate()
            else:
                os.killpg(os.getpgid(proc.pid), 15)
        except Exception:
            proc.terminate()
        return JSONResponse({"ok": True, "message": f"{step} 취소됨"})
    return JSONResponse({"ok": False, "error": "실행 중인 프로세스 없음"}, status_code=404)


@app.post("/api/run_log")
async def post_run_log(request: Request):
    body = await request.json()
    log_name = body.get("log", "run_execute.txt")
    if ".." in log_name or "/" in log_name:
        return JSONResponse({"ok": False}, status_code=400)

    log_path = LOGS_DIR / log_name
    content = ""
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8", errors="replace")

    step = log_name.replace("run_", "").replace(".txt", "")
    with _process_lock:
        test_meta = _test_runs.get(log_name)
        proc = _running.get(test_meta["key"]) if test_meta else _running.get(step)
    done = test_meta["done"] if test_meta else (proc is None or proc.poll() is not None)
    exit_code = test_meta["returncode"] if test_meta else (proc.returncode if (proc and proc.poll() is not None) else None)

    response: dict = {"ok": True, "log": content, "done": done, "exit_code": exit_code}
    if done:
        execute_results = read_state().get("execute_results", {})
        response["result"] = {
            "passed": execute_results.get("passed", []),
            "errors": execute_results.get("errors", []),
            "summary": execute_results.get("summary", {}),
        }
    return JSONResponse(response)


@app.post("/api/reset")
async def post_reset():
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
    pipeline_logs = {entry[2] for entry in SCRIPT_MAP.values()}
    pipeline_logs.update(path.name for path in LOGS_DIR.glob("run_heal_*.txt"))
    pipeline_logs.update(path.name for path in LOGS_DIR.glob("run_execute_*.txt"))
    for log_name in pipeline_logs:
        try:
            (LOGS_DIR / log_name).write_text("", encoding="utf-8")
        except OSError:
            pass
    return JSONResponse({"ok": True, "state": init})


@app.post("/api/import/convert")
async def post_import_convert(request: Request):
    body = await request.json()
    filename = str(body.get("file", "")).strip()
    sheet = str(body.get("sheet", "")).strip()
    platforms = body.get("platforms", ["android", "ios"])
    mappings = body.get("mappings", {})
    policy = body.get("policy", "skip-conflict")
    if (not filename or not sheet or not isinstance(platforms, list)
            or not isinstance(mappings, dict)
            or any(not isinstance(value, str) for value in mappings.values())
            or policy not in ("skip-conflict", "overwrite")):
        return JSONResponse({"ok": False, "error": "file, sheet, platforms, mappings가 필요합니다"}, status_code=400)
    if filename != Path(filename).name or not filename.endswith(".xlsx"):
        return JSONResponse({"ok": False, "error": "허용되지 않은 Excel 파일명입니다"}, status_code=400)
    source = (IMPORT_DIR / filename).resolve()
    if not source.is_file() or not source.is_relative_to(IMPORT_DIR.resolve()):
        return JSONResponse({"ok": False, "error": "Excel 파일을 찾을 수 없습니다"}, status_code=404)
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from import_excel import convert_sheet
        created = convert_sheet(source, sheet, TESTCASES_DIR, platforms, mappings, policy)
        return JSONResponse({
            "ok": True,
            "count": len(created),
            "files": [str(path.relative_to(PROJECT_ROOT)) for path in created],
        })
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.post("/api/import/preview")
async def post_import_preview(request: Request):
    body = await request.json()
    filename = str(body.get("file", "")).strip()
    sheets = body.get("sheets", [])
    platforms = body.get("platforms", ["android", "ios"])
    mappings = body.get("mappings", {})
    if (not filename or not isinstance(sheets, list) or not sheets
            or any(not isinstance(sheet, str) for sheet in sheets)
            or not isinstance(platforms, list) or not isinstance(mappings, dict)
            or any(not isinstance(value, str) for value in mappings.values())):
        return JSONResponse({"ok": False, "error": "file, sheets, platforms, mappings가 필요합니다"}, status_code=400)
    if filename != Path(filename).name or not filename.endswith(".xlsx"):
        return JSONResponse({"ok": False, "error": "허용되지 않은 Excel 파일명입니다"}, status_code=400)
    source = (IMPORT_DIR / filename).resolve()
    if not source.is_file() or not source.is_relative_to(IMPORT_DIR.resolve()):
        return JSONResponse({"ok": False, "error": "Excel 파일을 찾을 수 없습니다"}, status_code=404)
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from import_excel import preview_sheets
        result = preview_sheets(source, sheets, TESTCASES_DIR, platforms, mappings)
        return JSONResponse({"ok": True, **result})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.post("/api/import/upload")
async def post_import_upload(request: Request):
    body = await request.json()
    filename = str(body.get("name", "")).strip()
    encoded = str(body.get("data", "")).strip()
    if filename != Path(filename).name or not filename.lower().endswith(".xlsx"):
        return JSONResponse({"ok": False, "error": "xlsx 파일만 업로드할 수 있습니다"}, status_code=400)
    if not encoded or len(encoded) > 30 * 1024 * 1024:
        return JSONResponse({"ok": False, "error": "파일 크기는 20MB 이하이어야 합니다"}, status_code=400)
    try:
        content = base64.b64decode(encoded, validate=True)
    except Exception:
        return JSONResponse({"ok": False, "error": "파일 데이터가 올바르지 않습니다"}, status_code=400)
    if len(content) > 20 * 1024 * 1024:
        return JSONResponse({"ok": False, "error": "파일 크기는 20MB 이하이어야 합니다"}, status_code=400)
    (IMPORT_DIR / filename).write_bytes(content)
    return JSONResponse({"ok": True, "file": filename, "size": len(content)})


# ── Capture Studio 전용 엔드포인트 ───────────────────────────

@app.post("/capture/session")
async def capture_start_session(request: Request):
    """
    Capture Studio 세션 시작 또는 기존 세션 재연결.

    Body:
      {
        "platform": "android",          # android | ios
        "target": "emulator",           # emulator | simulator | device
        "app_package": "com.example",   # Android only
        "app_activity": ".MainActivity",
        "bundle_id": "",                # iOS only
        "tc_group": "settings",
        "session_id": ""                # 재연결 시 기존 session_id
      }
    """
    body = await request.json()
    platform = body.get("platform", "android")

    if platform not in ("android", "ios"):
        return JSONResponse({"ok": False, "error": "invalid platform"}, status_code=400)

    # 파이프라인 실행 중이면 차단
    if is_pipeline_active():
        return JSONResponse({
            "ok": False,
            "error": "파이프라인이 실행 중입니다. 완료 후 Capture Studio를 시작하세요."
        }, status_code=409)

    session_id = body.get("session_id", "")
    existing = load_capture_session()

    # 재연결 시도
    if session_id and existing.get("session_id") == session_id:
        save_capture_session({
            **existing,
            "active": True,
            "last_activity_at": datetime.now().isoformat(),
        })
        return JSONResponse({
            "ok": True,
            "session_id": session_id,
            "reconnected": True,
            "mjpeg_url": f"http://localhost:{existing.get('mjpeg_port', 8093)}",
        })

    # 새 세션 시작
    import uuid
    new_session_id = str(uuid.uuid4())
    mjpeg_port = body.get("mjpeg_port", 8093)

    session_data = {
        "session_id": new_session_id,
        "platform": platform,
        "target": body.get("target", "emulator"),
        "app_package": body.get("app_package", ""),
        "app_activity": body.get("app_activity", ""),
        "bundle_id": body.get("bundle_id", ""),
        "tc_group": body.get("tc_group", ""),
        "mjpeg_port": mjpeg_port,
        "active": True,
        "started_at": datetime.now().isoformat(),
        "last_activity_at": datetime.now().isoformat(),
        "actions": [],
    }
    save_capture_session(session_data)

    # 세션 원본 디렉토리 생성
    session_dir = CAPTURES_DIR / new_session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "native").mkdir(exist_ok=True)
    (session_dir / "webview").mkdir(exist_ok=True)
    session_dir.joinpath("session.json").write_text(
        json.dumps(session_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    session_dir.joinpath("actions.json").write_text("[]", encoding="utf-8")

    return JSONResponse({
        "ok": True,
        "session_id": new_session_id,
        "reconnected": False,
        "mjpeg_url": f"http://localhost:{mjpeg_port}",
        "session_dir": str(session_dir.relative_to(PROJECT_ROOT)),
    })


@app.post("/capture/tap")
async def capture_tap(request: Request):
    """
    요소 탭 실행 및 Action Timeline 기록.

    Body:
      {
        "session_id": "...",
        "x": 120, "y": 340,          # 브라우저 좌표
        "img_width": 360,             # 미러링 이미지 표시 너비 (px)
        "display_width": 1080,        # 디바이스 실제 너비 (px)
        "context": "NATIVE_APP"
      }
    """
    body = await request.json()
    session = load_capture_session()
    if not session.get("active"):
        return JSONResponse({"ok": False, "error": "활성 Capture 세션이 없습니다"}, status_code=409)

    # 좌표 스케일 보정
    img_width = body.get("img_width", 360)
    display_width = body.get("display_width", 1080)
    scale = display_width / img_width if img_width > 0 else 1.0
    device_x = int(body.get("x", 0) * scale)
    device_y = int(body.get("y", 0) * scale)

    action_index = len(session.get("actions", [])) + 1
    action = {
        "index": action_index,
        "action": "tap",
        "surface": "native",
        "context": body.get("context", "NATIVE_APP"),
        "screen": session.get("current_screen", ""),
        "target_ref": "",
        "snapshot_id": f"{action_index:04d}",
        "locator": {},
        "device_x": device_x,
        "device_y": device_y,
        "timestamp": datetime.now().isoformat(),
    }

    # actions.json에 추가
    session_dir = CAPTURES_DIR / session["session_id"]
    actions_path = session_dir / "actions.json"
    actions = json.loads(actions_path.read_text(encoding="utf-8")) if actions_path.exists() else []
    actions.append(action)
    actions_path.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")

    # capture_session.json 업데이트
    save_capture_session({
        **session,
        "last_activity_at": datetime.now().isoformat(),
        "actions": actions,
    })

    # WebSocket으로 Timeline 업데이트 전송
    broadcast_timeline_sync({"type": "action_added", "action": action})

    return JSONResponse({"ok": True, "action": action})


@app.post("/capture/input")
async def capture_input(request: Request):
    """
    Input 실행 및 기록.

    Body:
      {
        "session_id": "...",
        "value": "test@example.com",
        "is_secret": false,
        "target_ref": "login.email_field",
        "context": "NATIVE_APP"
      }
    """
    body = await request.json()
    session = load_capture_session()
    if not session.get("active"):
        return JSONResponse({"ok": False, "error": "활성 Capture 세션이 없습니다"}, status_code=409)

    is_secret = bool(body.get("is_secret", False))
    raw_value = str(body.get("value", ""))
    stored_value = "***" if is_secret else raw_value  # 비밀값 마스킹

    action_index = len(session.get("actions", [])) + 1
    action = {
        "index": action_index,
        "action": "input",
        "surface": "native",
        "context": body.get("context", "NATIVE_APP"),
        "screen": session.get("current_screen", ""),
        "target_ref": body.get("target_ref", ""),
        "snapshot_id": f"{action_index:04d}",
        "locator": {},
        "input_key": body.get("input_key", f"input_{action_index}"),
        "is_secret": is_secret,
        "value_preview": stored_value,
        "timestamp": datetime.now().isoformat(),
    }

    session_dir = CAPTURES_DIR / session["session_id"]
    actions_path = session_dir / "actions.json"
    actions = json.loads(actions_path.read_text(encoding="utf-8")) if actions_path.exists() else []
    actions.append(action)
    actions_path.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")

    save_capture_session({
        **session,
        "last_activity_at": datetime.now().isoformat(),
        "actions": actions,
    })

    broadcast_timeline_sync({"type": "action_added", "action": action})
    return JSONResponse({"ok": True, "action": action})


@app.get("/capture/hierarchy")
async def capture_hierarchy(session_id: str = "", context: str = "native"):
    """
    현재 hierarchy (Native XML 또는 WebView DOM) 수집.
    실제 Appium 드라이버는 Capture Studio 프론트에서 직접 호출하거나
    별도 capture_driver.py 를 통해 처리합니다.
    이 엔드포인트는 마지막 저장된 hierarchy를 반환합니다.
    """
    session = load_capture_session()
    if not session.get("active"):
        return JSONResponse({"ok": False, "error": "활성 Capture 세션이 없습니다"}, status_code=409)

    session_dir = CAPTURES_DIR / session.get("session_id", "")
    subdir = session_dir / ("webview" if context == "webview" else "native")
    if not subdir.exists():
        return JSONResponse({"ok": True, "hierarchy": None, "snapshot_count": 0})

    xml_files = sorted(subdir.glob("*.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not xml_files:
        return JSONResponse({"ok": True, "hierarchy": None, "snapshot_count": 0})

    latest = xml_files[0]
    return JSONResponse({
        "ok": True,
        "snapshot_id": latest.stem,
        "hierarchy": latest.read_text(encoding="utf-8", errors="replace"),
        "snapshot_count": len(xml_files),
        "context": context,
    })


@app.post("/capture/save")
async def capture_save(request: Request):
    """
    Capture 세션 결과를 TC Markdown, screens.json, locators.json에 저장.

    Body:
      {
        "session_id": "...",
        "tc_id": "tc_001",
        "title": "로그인 화면 진입",
        "platform": "android",
        "tc_group": "login",
        "steps": [...],
        "expected": [...],
        "approved_locators": {...},
        "overwrite": false
      }
    """
    body = await request.json()
    session = load_capture_session()

    tc_id = str(body.get("tc_id", "tc_001")).strip()
    title = str(body.get("title", "")).strip()
    platform = body.get("platform", session.get("platform", "android"))
    tc_group = str(body.get("tc_group", session.get("tc_group", "default"))).strip()
    steps = body.get("steps", [])
    expected = body.get("expected", [])
    approved_locators = body.get("approved_locators", {})
    overwrite = bool(body.get("overwrite", False))

    if not tc_id or not title or platform not in ("android", "ios"):
        return JSONResponse({"ok": False, "error": "tc_id, title, platform이 필요합니다"}, status_code=400)

    # 품질 낮음 태그 (기대 결과 없는 step 존재)
    has_missing_expected = any(not e for e in expected) if expected else len(steps) > 0
    quality_tag = "low-quality" if has_missing_expected else ""

    # Markdown TC 생성
    tc_dir = TESTCASES_DIR / platform / tc_group
    tc_dir.mkdir(parents=True, exist_ok=True)
    tc_path = tc_dir / f"{tc_id}.md"

    if tc_path.exists() and not overwrite:
        return JSONResponse({
            "ok": False,
            "error": f"파일이 이미 존재합니다: {tc_path.relative_to(PROJECT_ROOT)}",
            "conflict": True,
        }, status_code=409)

    # Markdown 내용 구성
    steps_md = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) if steps else "_(steps 없음)_"
    expected_md = "\n".join(f"{i+1}. {e}" if e else f"{i+1}. _(기대 결과 미입력)_" for i, e in enumerate(expected)) if expected else "_(기대 결과 없음)_"
    quality_line = f"\n> ⚠️ 품질 낮음: 기대 결과가 누락된 step이 있습니다.\n" if quality_tag else ""

    md_content = f"""# {tc_id}: {title}

## 플랫폼
{platform.capitalize()}

## TC 그룹
{tc_group}
{quality_line}
## 단계

{steps_md}

## 기대결과

{expected_md}
"""
    tc_path.write_text(md_content, encoding="utf-8")

    # locators.json 갱신
    saved_locators = []
    if approved_locators:
        locators_path = PROJECT_ROOT / "config" / "locators.json"
        locators = load_json(locators_path) or {}
        for key, locator_data in approved_locators.items():
            locators[key] = locator_data
            saved_locators.append(key)
        locators_path.write_text(json.dumps(locators, ensure_ascii=False, indent=2), encoding="utf-8")

    # Capture 세션 비활성화
    if session.get("active"):
        save_capture_session({
            **session,
            "active": False,
            "end_reason": "saved",
            "ended_at": datetime.now().isoformat(),
        })

    return JSONResponse({
        "ok": True,
        "tc_file": str(tc_path.relative_to(PROJECT_ROOT)),
        "saved_locators": saved_locators,
        "quality_tag": quality_tag,
        "next_actions": ["generate", "run", "open_tc"],
    })


@app.post("/capture/end")
async def capture_end_session(request: Request):
    """Capture 세션 명시적 종료 (저장 없이)."""
    body = await request.json()
    session = load_capture_session()
    session_id = body.get("session_id", session.get("session_id", ""))
    if session.get("session_id") != session_id:
        return JSONResponse({"ok": False, "error": "session_id가 일치하지 않습니다"}, status_code=400)
    save_capture_session({
        **session,
        "active": False,
        "end_reason": "user_ended",
        "ended_at": datetime.now().isoformat(),
    })
    return JSONResponse({"ok": True, "message": "Capture 세션 종료됨"})


@app.get("/capture/session")
async def capture_get_session():
    """현재 Capture 세션 상태 반환."""
    session = load_capture_session()
    active = is_capture_active()
    return JSONResponse({
        "ok": True,
        "active": active,
        "session": session if active else {},
    })


# ── 환경 확인 엔드포인트 ──────────────────────────────────────

@app.get("/api/check/mjpeg")
async def check_mjpeg(port: int = 8093):
    """MJPEG 스트리밍 서버 응답 여부 확인."""
    import urllib.request
    try:
        req = urllib.request.urlopen(f"http://localhost:{port}/", timeout=2)
        return JSONResponse({"ok": True, "port": port, "status": req.status})
    except Exception as exc:
        return JSONResponse({"ok": False, "port": port, "error": str(exc)})


@app.get("/api/check/appium")
async def check_appium():
    """Appium 서버 상태 확인."""
    ok = check_appium_status()
    session = load_capture_session()
    return JSONResponse({
        "ok": ok,
        "capture_session_id": session.get("session_id", "") if ok else "",
    })


# ── 서버 시작 ─────────────────────────────────────────────────

def _kill_port(port: int):
    try:
        result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
        pids = result.stdout.strip().splitlines()
        for pid in pids:
            try:
                os.kill(int(pid), 15)
            except Exception:
                pass
        if pids:
            import time
            time.sleep(0.5)
    except Exception:
        pass


def main():
    _kill_port(PORT)
    url = f"http://localhost:{PORT}"
    print(f"[Dashboard] 서버 시작: {url}")
    print("[Dashboard] WebSocket: ws://localhost:{PORT}/ws/timeline")
    print("[Dashboard] 종료: Ctrl+C")
    webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
