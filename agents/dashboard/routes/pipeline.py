"""
routes/pipeline.py — 파이프라인 실행 엔드포인트.

/api/run, /api/run_all, /api/run_test, /api/reports/delete,
/api/cancel, /api/run_log, /api/reset
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import (  # noqa: E402
    ADB_BIN,
    GENERATED_DIR,
    LOGS_DIR,
    PROJECT_ROOT,
    PYTHON_BIN,
    REPORTS_DIR,
    SCRIPT_MAP,
    _process_lock,
    _running,
    _test_runs,
)
from utils.state import (  # noqa: E402
    is_capture_active,
    list_tc_folders,
    read_state,
    save_state,
)

router = APIRouter()


@router.post("/api/run")
async def post_run(request: Request):
    body = await request.json()
    platform  = body.get("platform", "android")
    step      = body.get("step", "execute")
    tc_folder = body.get("tc_folder", "").strip()

    if platform not in ("android", "ios"):
        return JSONResponse({"ok": False, "error": "invalid platform"}, status_code=400)
    if step not in SCRIPT_MAP:
        return JSONResponse({"ok": False, "error": "invalid step"}, status_code=400)
    if tc_folder and (".." in tc_folder or "/" in tc_folder):
        return JSONResponse({"ok": False, "error": "invalid tc_folder"}, status_code=400)
    if is_capture_active():
        return JSONResponse(
            {"ok": False, "error": "Capture Studio 세션이 실행 중입니다. 먼저 Capture Studio를 종료하세요."},
            status_code=409,
        )

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

    log_path   = LOGS_DIR / log_name
    extra_popen: dict = {}
    if sys.platform != "win32":
        extra_popen["preexec_fn"] = os.setsid
    with open(log_path, "w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            [PYTHON_BIN, "-u", str(script)] + extra_args,
            cwd=str(PROJECT_ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            **extra_popen,
        )

    with _process_lock:
        _running[step] = proc

    threading.Thread(target=lambda p: p.wait(), args=(proc,), daemon=True).start()
    return JSONResponse({"ok": True, "pid": proc.pid, "log": log_name})


@router.post("/api/run_all")
async def post_run_all(request: Request):
    body = await request.json()
    platform   = body.get("platform", "android")
    tc_folders = body.get("tc_folders")
    if not isinstance(tc_folders, list):
        legacy_folder = body.get("tc_folder", "").strip()
        tc_folders = [legacy_folder] if legacy_folder else [""]
    tc_folders = [str(f).strip() for f in tc_folders]

    if platform not in ("android", "ios"):
        return JSONResponse({"ok": False, "error": "invalid platform"}, status_code=400)
    available_folders = set(list_tc_folders(platform))
    for tc_folder in tc_folders:
        if tc_folder and (".." in tc_folder or "/" in tc_folder or tc_folder not in available_folders):
            return JSONResponse({"ok": False, "error": f"invalid tc_folder: {tc_folder}"}, status_code=400)
    if is_capture_active():
        return JSONResponse(
            {"ok": False, "error": "Capture Studio 세션이 실행 중입니다. 먼저 Capture Studio를 종료하세요."},
            status_code=409,
        )

    state = read_state()
    state["platform"] = platform
    state.pop("last_fail_video", None)
    save_state(state)

    MAX_HEAL = 3
    PIPELINE  = ["analyze", "generate", "lint", "execute"]

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
        lname  = log_name.replace(".txt", f"{log_suffix}.txt") if log_suffix else log_name
        log_path = LOGS_DIR / lname
        extra_popen: dict = {}
        if sys.platform != "win32":
            extra_popen["preexec_fn"] = os.setsid
        with open(log_path, "w", encoding="utf-8") as lf:
            proc = subprocess.Popen(
                [PYTHON_BIN, "-u", str(script)] + extra_args,
                cwd=str(PROJECT_ROOT),
                stdout=lf,
                stderr=subprocess.STDOUT,
                **extra_popen,
            )
        with _process_lock:
            _running[step] = proc
        proc.wait()
        return proc.returncode, lname

    def _record_video(suffix: str):
        ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
        vid_dir = PROJECT_ROOT / "reports" / "recordings"
        vid_dir.mkdir(parents=True, exist_ok=True)
        vid_path = vid_dir / f"fail_{platform}_{suffix}_{ts}.mp4"
        if platform == "ios":
            rec_proc = subprocess.Popen(
                ["xcrun", "simctl", "io", "booted", "recordVideo", "--codec=h264", str(vid_path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return rec_proc, vid_path, None
        else:
            device_id = ""
            r = subprocess.run([ADB_BIN, "devices"], capture_output=True, text=True)
            for ln in r.stdout.splitlines()[1:]:
                if ln.strip() and "offline" not in ln:
                    device_id = ln.split()[0]
                    break
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
            return rec_proc, vid_path, device_id

    def _stop_video(rec_info):
        import time as _time
        rec_proc, vid_path, device_id = rec_info
        rec_proc.terminate()
        _time.sleep(2)
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
        execute_ok = (
            read_state().get("execute_results", {})
            .get("summary", {}).get("failed", 0) == 0
        )
        for heal_round in range(1, MAX_HEAL + 1):
            if execute_ok:
                break
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
                _spawn("heal", folder=folder, log_suffix=f"_{heal_round}")
                _spawn("execute", folder=folder, log_suffix=f"_{heal_round}")
                execute_ok = (
                    read_state().get("execute_results", {})
                    .get("summary", {}).get("failed", 0) == 0
                )

    def _run_selected_folders():
        import time as _time
        for idx, folder in enumerate(tc_folders):
            if idx > 0:
                # 이전 Appium/UiAutomator2 세션이 완전히 종료된 후 다음 세션 시작
                _time.sleep(12)
            _run_pipeline(folder)

    threading.Thread(target=_run_selected_folders, daemon=True).start()
    return JSONResponse({
        "ok": True,
        "folders": tc_folders,
        "mode": "serial",
        "steps": PIPELINE + ["heal(x3)", "record"],
    })


@router.post("/api/run_test")
async def post_run_test(request: Request):
    body        = await request.json()
    platform    = body.get("platform", "android")
    test_file   = str(body.get("test_file", "")).strip()
    test_folder = str(body.get("test_folder", "")).strip()
    heal        = bool(body.get("heal", True))

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
        run_key    = f"folder:{platform}:{test_folder}"
        log_name   = "run_test_" + platform + "_" + test_folder.replace("/", "_") + ".txt"
    else:
        if ".." in test_file or test_file.startswith("/"):
            return JSONResponse({"ok": False, "error": "invalid test file or platform"}, status_code=400)
        candidate = (root / test_file).resolve()
        if candidate.suffix != ".py" or not candidate.is_file() or not candidate.is_relative_to(root):
            return JSONResponse({"ok": False, "error": "생성된 테스트 파일을 찾을 수 없습니다"}, status_code=404)
        run_target = test_file
        run_key    = f"test:{platform}:{test_file}"
        log_name   = "run_test_" + platform + "_" + test_file.replace("/", "_").replace(".py", "") + ".txt"

    log_path = LOGS_DIR / log_name
    with _process_lock:
        old = _running.get(run_key)
        if old and old.poll() is None:
            return JSONResponse({"ok": False, "error": "해당 테스트가 이미 실행 중입니다"}, status_code=409)
        _test_runs[log_name] = {"key": run_key, "done": False, "returncode": None}

    def spawn(args, mode="a"):
        popen_opts = {"preexec_fn": os.setsid} if sys.platform != "win32" else {}
        with open(log_path, mode, encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                [PYTHON_BIN, "-u"] + args,
                cwd=str(PROJECT_ROOT),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                **popen_opts,
            )
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


@router.post("/api/reports/delete")
async def post_reports_delete(request: Request):
    body  = await request.json()
    names = body.get("names", [])
    if not isinstance(names, list) or not names:
        return JSONResponse({"ok": False, "error": "삭제할 리포트를 선택하세요"}, status_code=400)
    deleted, missing, failed = [], [], []
    base = REPORTS_DIR.resolve()
    for raw_name in names:
        name   = str(raw_name)
        target = (base / name).resolve()
        if target.suffix != ".html" or not target.is_relative_to(base):
            failed.append({"name": name, "error": "invalid report path"})
            continue
        if not target.is_file():
            missing.append(name)
            continue
        try:
            target.unlink()
            deleted.append(name)
        except OSError as exc:
            failed.append({"name": name, "error": str(exc)})
    return JSONResponse({"ok": not failed, "deleted": deleted, "missing": missing, "failed": failed})


@router.post("/api/cancel")
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


@router.post("/api/run_log")
async def post_run_log(request: Request):
    body     = await request.json()
    log_name = body.get("log", "run_execute.txt")
    if ".." in log_name or "/" in log_name:
        return JSONResponse({"ok": False}, status_code=400)

    log_path = LOGS_DIR / log_name
    content  = ""
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8", errors="replace")

    step = log_name.replace("run_", "").replace(".txt", "")
    with _process_lock:
        test_meta = _test_runs.get(log_name)
        proc      = _running.get(test_meta["key"]) if test_meta else _running.get(step)
    done      = test_meta["done"] if test_meta else (proc is None or proc.poll() is not None)
    exit_code = (
        test_meta["returncode"]
        if test_meta
        else (proc.returncode if (proc and proc.poll() is not None) else None)
    )

    response: dict = {"ok": True, "log": content, "done": done, "exit_code": exit_code}
    if done:
        execute_results = read_state().get("execute_results", {})
        response["result"] = {
            "passed": execute_results.get("passed", []),
            "errors": execute_results.get("errors", []),
            "summary": execute_results.get("summary", {}),
        }
    return JSONResponse(response)


@router.post("/api/reset")
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
