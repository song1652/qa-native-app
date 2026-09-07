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


def list_tc_folders(platform: str | None = None) -> list[str]:
    """testcases/ 하위 폴더 목록 반환. 빈 폴더는 제외."""
    if not TESTCASES_DIR.exists():
        return []
    if platform in ("android", "ios"):
        platform_dir = TESTCASES_DIR / platform
        return [platform] if platform_dir.is_dir() and any(platform_dir.rglob("tc_*.md")) else []
    return sorted([
        d.name for d in TESTCASES_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".") and list(d.glob("tc_*.md"))
    ])


# ── 프런트엔드 문서 ───────────────────────────────────────────

DASHBOARD_HTML = (HERE / "dashboard.html").read_text(encoding="utf-8")


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
            "/api/import/preview": self._post_import_preview,
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
        from urllib.parse import parse_qs, urlparse
        platform = parse_qs(urlparse(self.path).query).get("platform", [None])[0]
        if platform not in (None, "android", "ios"):
            self._serve_json({"ok": False, "error": "invalid platform"})
            return
        self._serve_json(list_generated(platform))

    def _get_screenshots(self):
        self._serve_json(list_screenshots())

    def _get_tc_folders(self):
        from urllib.parse import parse_qs, urlparse
        platform = parse_qs(urlparse(self.path).query).get("platform", [None])[0]
        if platform not in (None, "android", "ios"):
            self._serve_json({"ok": False, "error": "invalid platform"})
            return
        self._serve_json({"folders": list_tc_folders(platform)})

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
        if step == "generate" and tc_folder:
            extra_args += ["--tc-dir", tc_folder]
        if step == "execute" and tc_folder and tc_folder != platform:
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
        available_folders = set(list_tc_folders(platform))
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
            if step == "generate" and folder:
                extra_args += ["--tc-dir", folder]
            if step == "execute" and folder and folder != platform:
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
        mappings = body.get("mappings", {})
        policy = body.get("policy", "skip-conflict")
        if (not filename or not sheet or not isinstance(platforms, list)
                or not isinstance(mappings, dict)
                or any(not isinstance(value, str) for value in mappings.values())
                or policy not in ("skip-conflict", "overwrite")):
            self._serve_json({"ok": False, "error": "file, sheet, platforms, mappings가 필요합니다"})
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
            created = convert_sheet(
                source, sheet, TESTCASES_DIR, platforms, mappings, policy
            )
            self._serve_json({
                "ok": True,
                "count": len(created),
                "files": [str(path.relative_to(PROJECT_ROOT)) for path in created],
            })
        except Exception as exc:
            self._serve_json({"ok": False, "error": str(exc)})

    def _post_import_preview(self):
        body = _read_body(self)
        filename = str(body.get("file", "")).strip()
        sheets = body.get("sheets", [])
        platforms = body.get("platforms", ["android", "ios"])
        mappings = body.get("mappings", {})
        if (not filename or not isinstance(sheets, list) or not sheets
                or any(not isinstance(sheet, str) for sheet in sheets)
                or not isinstance(platforms, list) or not isinstance(mappings, dict)
                or any(not isinstance(value, str) for value in mappings.values())):
            self._serve_json({"ok": False, "error": "file, sheets, platforms, mappings가 필요합니다"})
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
            from import_excel import preview_sheets
            result = preview_sheets(source, sheets, TESTCASES_DIR, platforms, mappings)
            self._serve_json({"ok": True, **result})
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
    print("[Dashboard] 종료: Ctrl+C")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Dashboard] 서버 종료")


if __name__ == "__main__":
    main()
