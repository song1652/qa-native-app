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
    save_running_pids,
)
from utils.state import (  # noqa: E402
    is_capture_active,
    list_tc_folders,
    read_state,
    save_state,
)
from utils.artifact_retention import load_retention_limits, purge_old_runs  # noqa: E402
from ws import broadcast_timeline_sync  # noqa: E402

router = APIRouter()


@router.get("/api/devices")
async def get_devices(platform: str = "android"):
    """연결된 디바이스 목록 반환 (devices.json + adb/xcrun 실시간 상태)."""
    import json as _json
    devices_path = PROJECT_ROOT / "config" / "devices.json"
    try:
        cfg = _json.loads(devices_path.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}

    result: list[dict] = []

    if platform == "android":
        # adb로 연결된 serial 목록
        try:
            r = subprocess.run([ADB_BIN, "devices"], capture_output=True, text=True)
            connected_serials: set[str] = set()
            for ln in r.stdout.splitlines()[1:]:
                parts = ln.split()
                if len(parts) >= 2 and parts[1] == "device":
                    connected_serials.add(parts[0])
        except Exception:
            connected_serials = set()

        # 에뮬레이터
        for dev in cfg.get("android", {}).get("emulator", []):
            serial = next((s for s in connected_serials if s.startswith("emulator-")), "")
            result.append({
                "mode": "emulator",
                "deviceName": dev.get("deviceName", "Android Emulator"),
                "udid": serial,
                "platformVersion": dev.get("platformVersion", ""),
                "connected": bool(serial),
                "default": dev.get("default", False),
            })

        # 실기기
        for dev in cfg.get("android", {}).get("real_device", []):
            udid = dev.get("udid", "")
            connected = udid in connected_serials if udid else bool(
                next((s for s in connected_serials if not s.startswith("emulator-")), "")
            )
            result.append({
                "mode": "real_device",
                "deviceName": dev.get("deviceName", ""),
                "udid": udid,
                "platformVersion": dev.get("platformVersion", ""),
                "connected": connected,
                "default": dev.get("default", False),
            })

    elif platform == "ios":
        # 부팅된 시뮬레이터 UDID
        try:
            r = subprocess.run(["xcrun", "simctl", "list", "devices", "booted", "--json"],
                               capture_output=True, text=True)
            import json as _j
            booted = set()
            for devs in _j.loads(r.stdout).get("devices", {}).values():
                for d in devs:
                    if d.get("state") == "Booted":
                        booted.add(d["udid"])
        except Exception:
            booted = set()

        for dev in cfg.get("ios", {}).get("simulator", []):
            uid = dev.get("udid", "")
            result.append({
                "mode": "simulator",
                "deviceName": dev.get("deviceName", ""),
                "udid": uid,
                "platformVersion": dev.get("platformVersion", ""),
                "connected": uid in booted,
                "default": dev.get("default", False),
            })
        for dev in cfg.get("ios", {}).get("real_device", []):
            result.append({
                "mode": "real_device",
                "deviceName": dev.get("deviceName", ""),
                "udid": dev.get("udid", ""),
                "platformVersion": dev.get("platformVersion", ""),
                "connected": False,
                "default": dev.get("default", False),
            })

    return JSONResponse({"ok": True, "devices": result})


def _gen_run_id(platform: str) -> str:
    """PRD §3-2: run_{platform}_{YYYYMMDD}_{HHMMSS}_{mmm}."""
    from datetime import datetime
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    return f"run_{platform}_{stamp}"


def _build_run_env(
    run_id: str,
    platform: str,
    obs_keep: str = "",
    device_mode: str = "",
    device_udid: str = "",
) -> dict[str, str]:
    """Build child-only execution environment without mutating the server."""
    env = os.environ.copy()
    env["QA_RUN_ID"] = run_id
    env["QA_PLATFORM"] = platform
    env["QA_OBS_KEEP"] = (
        obs_keep if obs_keep in {"on_failure", "always", "never"} else "on_failure"
    )
    if device_mode:
        env["DEVICE_MODE"] = device_mode
    else:
        env.pop("DEVICE_MODE", None)
    if device_udid:
        env["DEVICE_UDID"] = device_udid
    else:
        env.pop("DEVICE_UDID", None)
    return env


def _device_execute_args(platform: str, device_mode: str, device_udid: str) -> list[str]:
    args: list[str] = []
    mode = device_mode or ("simulator" if platform == "ios" else "emulator")
    if mode:
        args += ["--mode", mode]
    if device_udid:
        args += ["--udid", device_udid]
    return args


def _quick_run_execute_args(
    platform: str, *, test_folder: str, test_file: str, heal: bool
) -> list[str]:
    """Build quick-run args; skipping healing also means exactly one attempt."""
    args = [str(PROJECT_ROOT / "scripts/05_execute.py"), "--platform", platform]
    if test_folder:
        args += ["--tc-dir", test_folder]
    else:
        args += ["--test-file", test_file]
    if not heal:
        args.append("--no-rerun")
    return args


def _read_run_summary(run_id: str) -> dict:
    import json
    artifact_dir = PROJECT_ROOT / "state" / "runs" / run_id / "artifacts"
    manifest_path = artifact_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        manifest = {"entries": []}
    latest = []
    for entry in manifest.get("entries", []):
        attempts = entry.get("attempts")
        latest.append(attempts[-1] if isinstance(attempts, list) and attempts else entry)
    size_bytes = 0
    if artifact_dir.exists():
        for path in artifact_dir.rglob("*"):
            if path.is_file():
                try:
                    size_bytes += path.stat().st_size
                except OSError:
                    pass
    return {
        "failed": sum(1 for item in latest if item.get("outcome") in {"failed", "error"}),
        "with_video": sum(1 for item in latest if item.get("video")),
        "with_syslog": sum(1 for item in latest if item.get("syslog")),
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2),
    }


def _broadcast_run_summary(run_id: str, ok: bool) -> None:
    broadcast_timeline_sync({
        "type": "obs_run_summary", "source": "pipeline",
        "run_id": run_id, "ok": ok, **_read_run_summary(run_id),
    })


def _purge_old_runs() -> None:
    """run 보존 정리 — pipeline.py에서 run_id 발급 직후 1회 호출."""
    try:
        ret = load_retention_limits(PROJECT_ROOT / "config" / "observability.json")
        purge_old_runs(
            PROJECT_ROOT / "state" / "runs",
            max_runs=int(ret["max_runs"]),
            max_total_mb=ret["max_total_mb"],
        )
    except Exception:
        pass


@router.post("/api/run")
async def post_run(request: Request):
    body = await request.json()
    platform     = body.get("platform", "android")
    step         = body.get("step", "execute")
    tc_folder    = body.get("tc_folder", "").strip()
    device_mode  = body.get("mode", "").strip()   # emulator | real_device | simulator
    device_udid  = body.get("device_udid", "").strip()
    obs_keep     = body.get("obs_keep", "").strip()

    if platform not in ("android", "ios"):
        return JSONResponse({"ok": False, "error": "invalid platform"}, status_code=400)
    if step not in SCRIPT_MAP:
        return JSONResponse({"ok": False, "error": "invalid step"}, status_code=400)
    if tc_folder and (".." in tc_folder or "/" in tc_folder):
        return JSONResponse({"ok": False, "error": "invalid tc_folder"}, status_code=400)
    if is_capture_active(platform):
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

    # F-8: run-scoped env를 자식 프로세스에만 전달한다.
    if step == "execute":
        run_id = _gen_run_id(platform)
        run_env = _build_run_env(run_id, platform, obs_keep, device_mode, device_udid)
        _purge_old_runs()
        try:
            state = read_state(); state["obs_last_run_id"] = run_id; save_state(state)
        except Exception:
            pass
        broadcast_timeline_sync({
            "type": "obs_run_start", "source": "pipeline",
            "run_id": run_id,
            "keep": run_env["QA_OBS_KEEP"],
        })
    else:
        run_id = None
        run_env = None

    script_rel, extra_args_tmpl, log_name = SCRIPT_MAP[step]
    extra_args = [a.replace("{platform}", platform) for a in extra_args_tmpl]
    if step in ("analyze", "generate"):
        _mode = device_mode or ("simulator" if platform == "ios" else "emulator")
        extra_args += ["--mode", _mode]
        if step == "generate" and device_udid:
            extra_args += ["--device-udid", device_udid]
    if step == "generate" and tc_folder:
        extra_args += ["--tc-dir", tc_folder]
    if step == "execute" and tc_folder and tc_folder != platform:
        extra_args += ["--tc-dir", tc_folder]
    if step == "execute":
        extra_args += _device_execute_args(platform, device_mode, device_udid)
    if step == "analyze" and device_udid:
        extra_args += ["--udid", device_udid]
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
            env=run_env,
            **extra_popen,
        )

    with _process_lock:
        _running[step] = proc
        save_running_pids()

    broadcast_timeline_sync({
        "type": "pipeline_stage_start", "source": "pipeline",
        "platform": platform, "stage": step, "log": log_name,
    })

    def _wait_and_notify(p, s, plat, lname, rid):
        p.wait()
        with _process_lock:
            if _running.get(s) is p:
                del _running[s]
            save_running_pids()
        broadcast_timeline_sync({
            "type": "pipeline_stage_complete", "source": "pipeline",
            "platform": plat, "stage": s,
            "ok": p.returncode == 0, "returncode": p.returncode,
        })
        if rid:
            _broadcast_run_summary(rid, p.returncode == 0)

    threading.Thread(
        target=_wait_and_notify,
        args=(proc, step, platform, log_name, run_id),
        daemon=True,
    ).start()
    return JSONResponse({"ok": True, "pid": proc.pid, "log": log_name})


@router.post("/api/run_all")
async def post_run_all(request: Request):
    body = await request.json()
    platform     = body.get("platform", "android")
    tc_folders   = body.get("tc_folders")
    device_mode  = body.get("mode", "").strip()
    device_udid  = body.get("device_udid", "").strip()
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
    if is_capture_active(platform):
        return JSONResponse(
            {"ok": False, "error": "Capture Studio 세션이 실행 중입니다. 먼저 Capture Studio를 종료하세요."},
            status_code=409,
        )

    obs_keep = body.get("obs_keep", "").strip()

    state = read_state()
    state["platform"] = platform
    state.pop("last_fail_video", None)
    save_state(state)

    MAX_HEAL = 3
    PIPELINE  = ["analyze", "generate", "lint", "execute"]

    def _spawn(step, folder="", extra=None, log_suffix="", env=None):
        script_rel, extra_args_tmpl, log_name = SCRIPT_MAP[step]
        extra_args = [a.replace("{platform}", platform) for a in extra_args_tmpl]
        if step in ("analyze", "generate"):
            _mode = device_mode or ("simulator" if platform == "ios" else "emulator")
            extra_args += ["--mode", _mode]
            if step == "generate" and device_udid:
                extra_args += ["--device-udid", device_udid]
        if step == "analyze" and device_udid:
            extra_args += ["--udid", device_udid]
        if step == "generate" and folder:
            extra_args += ["--tc-dir", folder]
        if step == "execute" and folder and folder != platform:
            extra_args += ["--tc-dir", folder]
        if step == "execute":
            extra_args += _device_execute_args(platform, device_mode, device_udid)
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
                env=env,
                **extra_popen,
            )
        with _process_lock:
            _running[step] = proc
            save_running_pids()
        broadcast_timeline_sync({
            "type": "pipeline_stage_start", "source": "pipeline",
            "platform": platform, "stage": step, "log": lname,
        })
        proc.wait()
        with _process_lock:
            if _running.get(step) is proc:
                del _running[step]
            save_running_pids()
        broadcast_timeline_sync({
            "type": "pipeline_stage_complete", "source": "pipeline",
            "platform": platform, "stage": step,
            "ok": proc.returncode == 0, "returncode": proc.returncode,
        })
        return proc.returncode, lname

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
        run_id = None
        run_env = None

        def _execute_with_obs(log_suffix="", extra=None):
            """Execute with one logical run_id and a child-only environment."""
            nonlocal run_id, run_env
            if run_id is None:
                run_id = _gen_run_id(platform)
                run_env = _build_run_env(
                    run_id, platform, obs_keep, device_mode, device_udid
                )
                _purge_old_runs()
                try:
                    _st = read_state(); _st["obs_last_run_id"] = run_id; save_state(_st)
                except Exception:
                    pass
                broadcast_timeline_sync({
                    "type": "obs_run_start", "source": "pipeline",
                    "run_id": run_id,
                    "keep": run_env["QA_OBS_KEEP"],
                })
            rc, lname = _spawn(
                "execute", folder=folder, log_suffix=log_suffix, extra=extra,
                env=run_env,
            )
            _broadcast_run_summary(run_id, rc == 0)
            return rc, lname

        for step in PIPELINE:
            if step == "execute":
                rc, _ = _execute_with_obs()
            else:
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
                _execute_with_obs(log_suffix=f"_record{heal_round}")
                _report_final_failure()
                break
            else:
                _spawn("heal", folder=folder, log_suffix=f"_{heal_round}")
                _execute_with_obs(log_suffix=f"_{heal_round}")
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
    device_mode = body.get("mode", "").strip()
    device_udid = body.get("device_udid", "").strip()
    obs_keep    = body.get("obs_keep", "").strip()

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

    def spawn(args, mode="a", env=None):
        popen_opts = {"preexec_fn": os.setsid} if sys.platform != "win32" else {}
        with open(log_path, mode, encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                [PYTHON_BIN, "-u"] + args,
                cwd=str(PROJECT_ROOT),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                **popen_opts,
            )
        with _process_lock:
            _running[run_key] = proc
            save_running_pids()
        proc.wait()
        with _process_lock:
            if _running.get(run_key) is proc:
                del _running[run_key]
            save_running_pids()
        return proc.returncode

    def run():
        run_id = _gen_run_id(platform)
        run_env = _build_run_env(
            run_id, platform, obs_keep, device_mode, device_udid
        )
        _purge_old_runs()
        try:
            _st = read_state(); _st["obs_last_run_id"] = run_id; save_state(_st)
        except Exception:
            pass
        broadcast_timeline_sync({
            "type": "obs_run_start", "source": "pipeline",
            "run_id": run_id, "keep": run_env["QA_OBS_KEEP"],
        })
        execute_args = _quick_run_execute_args(
            platform,
            test_folder=run_target if test_folder else "",
            test_file=run_target if not test_folder else "",
            heal=heal,
        )
        execute_args += _device_execute_args(platform, device_mode, device_udid)

        def _run_execute_with_obs(mode="w"):
            """Execute with the logical run's immutable child environment."""
            return spawn(execute_args, mode, env=run_env)

        rc = _run_execute_with_obs("w")
        if rc != 0 and heal:
            heal_args = [str(PROJECT_ROOT / "scripts/06_heal.py"), "--platform", platform]
            spawn(heal_args)
            rc = _run_execute_with_obs("a")
        _broadcast_run_summary(run_id, rc == 0)
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
        save_running_pids()
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
