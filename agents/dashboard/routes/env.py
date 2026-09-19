"""
routes/env.py — ENV Setup 엔드포인트 (M1 + M2.1 + M3.0 + US-3 full).

GET  /api/env/status                    — Appium/Android/iOS 5값 상태 조회
GET  /api/env/appium/log                — Appium 서버 로그 마지막 N줄 반환
POST /api/env/appium/start              — Appium 프로세스 시작
POST /api/env/appium/stop               — Appium 프로세스 종료 (Capture/파이프라인 가드 포함)
POST /api/env/android/avd/start         — Android AVD 부팅 (Capture 가드, 중복 방지)
POST /api/env/android/avd/stop          — AVD 종료 (Capture 가드 포함)
POST /api/env/android/real/connect      — WiFi ADB 연결 (M3.0)
POST /api/env/android/real/disconnect   — WiFi ADB 해제 (M3.0)
POST /api/env/android/real/pair         — WiFi ADB 페어링 (adb pair, Phase 3)
POST /api/env/ios/simulator/start       — iOS Simulator 부팅 (Capture 가드)
POST /api/env/ios/simulator/stop        — iOS Simulator 종료 (Capture 가드)
POST /api/env/ios/real/wda_build        — WDA 빌드/설치 (Phase 3)
POST /api/env/android/add               — Android 디바이스 추가 (US-3, 중복 409, caps 자동 채움)
POST /api/env/android/remove            — Android 디바이스 삭제 (US-3)
POST /api/env/ios/add                   — iOS 디바이스 추가 (US-3, 중복 409, caps 자동 채움)
POST /api/env/ios/remove                — iOS 디바이스 삭제 (US-3)
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from typing import Optional

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import (  # noqa: E402
    ADB_BIN,
    APPIUM_BIN,
    EMULATOR_BIN,
    PROJECT_ROOT,
    subprocess_env_for,
)
from utils.state import (  # noqa: E402
    is_capture_active,
    is_pipeline_active,
    load_devices_json,
    load_env_session,
    save_devices_json,
    update_env_session_sections,
)
from utils.env_devices import (  # noqa: E402
    configured_android_rows,
    configured_ios_rows,
    normalize_device_list,
    real_device_rows,
)
from routes.env_registry import attach_device_registry_routes  # noqa: E402
from utils.env_processes import (  # noqa: E402
    command_detail as _command_detail,
    wait_for_process_and_port_exit as _wait_for_appium_exit,
)
from utils.system import (  # noqa: E402
    check_android_real_devices,
    check_ios_real_devices,
    detect_android_runtime,
    detect_appium_status,
    detect_ios_runtime,
    get_android_avd_name,
    get_default_device,
    list_system_avds,
    list_system_simulators,
)

router = APIRouter()
attach_device_registry_routes(router, sys.modules[__name__])

# Appium 로그 파일 핸들 (GC 방지용 모듈 레벨 보관)
_appium_log_fh = None


def _list_installed_avds() -> list[str]:
    """현재 머신에 실제로 설치된 Android AVD 이름을 반환한다."""
    result = subprocess.run(
        [EMULATOR_BIN, "-list-avds"],
        capture_output=True,
        text=True,
        timeout=10,
        env=subprocess_env_for(EMULATOR_BIN),
    )
    if isinstance(result.returncode, int) and result.returncode != 0:
        raise RuntimeError(_command_detail(result))
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _get_wifi_serial() -> "str | None":
    """devices.json android.real_device[].wifi_ip에서 wifi serial 반환 (ip:5555).

    Returns:
        "ip:5555" 형태 문자열, 또는 wifi_ip 미설정 시 None.
    """
    dev = get_default_device("android", "real_device") or {}
    ip = dev.get("wifi_ip", "")
    return f"{ip}:5555" if ip else None


def _load_real_devices() -> "tuple[list, list]":
    """config/devices.json 에서 android/ios real_device 목록을 반환.

    Returns:
        (android_real_devices, ios_real_devices) — 각각 dict 목록.
        파일 읽기 실패 시 ([], []).
    """
    import json as _json

    devices_path = PROJECT_ROOT / "config" / "devices.json"
    try:
        data = _json.loads(devices_path.read_text(encoding="utf-8"))
    except Exception:
        return [], []

    android = normalize_device_list(data.get("android", {}).get("real_device", []))
    ios = normalize_device_list(data.get("ios", {}).get("real_device", []))
    return android, ios


@router.get("/api/env/android/list_system_avds")
def get_system_avds():
    """Return installed AVD metadata for the Android add modal."""
    try:
        return {"ok": True, "avds": list_system_avds()}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "discovery_failed",
                "message": str(exc),
            },
        )


@router.get("/api/env/ios/list_system_simulators")
def get_system_simulators():
    """Return available simulator metadata for the iOS add modal."""
    try:
        return {"ok": True, "simulators": list_system_simulators()}
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "discovery_failed",
                "message": str(exc),
            },
        )


@router.get("/api/env/android/avds")
def get_configured_android_avds():
    """Return configured Android rows joined to the controlled runtime."""
    configured = load_devices_json().get("android", {}).get("emulator", [])
    runtime = detect_android_runtime(load_env_session().get("android", {}))
    return {"ok": True, "avds": configured_android_rows(configured, runtime)}


@router.get("/api/env/ios/simulators")
def get_configured_ios_simulators():
    """Return configured iOS rows joined to the controlled runtime."""
    configured = load_devices_json().get("ios", {}).get("simulator", [])
    runtime = detect_ios_runtime(load_env_session().get("ios", {}))
    return {"ok": True, "simulators": configured_ios_rows(configured, runtime)}


# ── GET /api/env/status ───────────────────────────────────────────

@router.get("/api/env/status")
def get_env_status():
    """Appium·Android·iOS 현재 상태를 반환한다."""
    session = load_env_session()
    appium_info = detect_appium_status()

    stored_android = session.get(
        "android", {"status": "stopped", "avd": None, "started_at": None}
    )
    stored_ios = session.get(
        "ios", {"status": "stopped", "simulator": None, "started_at": None}
    )
    runtime_android = detect_android_runtime(stored_android)
    runtime_ios = detect_ios_runtime(stored_ios)
    stored_appium = session.get("appium", {})
    runtime_appium = {
        **stored_appium,
        **{
            key: appium_info.get(key)
            for key in ("status", "pid", "port", "error_msg", "started_at")
        },
    }
    if (
        runtime_appium != stored_appium
        or runtime_android != stored_android
        or runtime_ios != stored_ios
    ):
        session = update_env_session_sections(
            {
                "appium": runtime_appium,
                "android": runtime_android,
                "ios": runtime_ios,
            },
            expected={
                "appium": stored_appium,
                "android": stored_android,
                "ios": stored_ios,
            },
        )
        runtime_android = session.get("android", runtime_android)
        runtime_ios = session.get("ios", runtime_ios)
        applied_appium = session.get("appium", runtime_appium)
        appium_info = {
            **appium_info,
            **{
                key: applied_appium.get(key)
                for key in ("status", "pid", "port", "error_msg", "started_at")
            },
        }

    # 실기기 연결 상태 조회 (M3.0)
    android_devs, ios_devs = _load_real_devices()

    android_serials = [d.get("udid", "") for d in android_devs]
    ios_udids = [d.get("udid", "") for d in ios_devs]

    android_connected = check_android_real_devices(android_serials)
    ios_connected = check_ios_real_devices(ios_udids)

    android_real_list, ios_real_list = real_device_rows(
        android_devs,
        ios_devs,
        android_connected,
        ios_connected,
    )

    android_section = dict(runtime_android)
    android_section["real_devices"] = android_real_list

    ios_section = dict(runtime_ios)
    ios_section["real_devices"] = ios_real_list

    # US-3: devices.json 에뮬레이터/시뮬레이터 목록 포함
    devices_data = load_devices_json()
    emulators = normalize_device_list(devices_data.get("android", {}).get("emulator", []))
    android_section["emulators"] = emulators

    simulators = normalize_device_list(devices_data.get("ios", {}).get("simulator", []))
    ios_section["simulators"] = simulators

    return JSONResponse({
        "appium": appium_info,
        "android": android_section,
        "ios": ios_section,
    })


# ── GET /api/env/appium/log ───────────────────────────────────────

@router.get("/api/env/appium/log")
def get_appium_log(lines: int = 200):
    """Appium 서버 로그 마지막 N줄 반환."""
    log_path = PROJECT_ROOT / "logs" / "appium_server.log"
    if not log_path.exists():
        return JSONResponse({"ok": True, "lines": []})
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        all_lines = text.splitlines()
        return JSONResponse({"ok": True, "lines": all_lines[-lines:]})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ── POST /api/env/appium/start ────────────────────────────────────

@router.post("/api/env/appium/start")
def post_appium_start():
    """Appium 서버를 시작한다.

    이미 managed 또는 external 상태이면 409 already_running.
    """
    global _appium_log_fh

    session = load_env_session()
    appium = session.get("appium", {})
    current_status = appium.get("status", "stopped")

    if current_status in ("starting", "managed", "external"):
        return JSONResponse({"ok": False, "error": "already_running"}, status_code=409)

    stale_pid = appium.get("pid") if current_status == "error" else None
    if stale_pid is not None:
        try:
            os.kill(stale_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError as exc:
            return JSONResponse(
                {"ok": False, "error": "stale_process_cleanup_failed", "detail": str(exc)},
                status_code=500,
            )
        if not _wait_for_appium_exit(stale_pid, int(appium.get("port", 4723))):
            return JSONResponse(
                {
                    "ok": False,
                    "error": "stale_process_cleanup_timeout",
                    "detail": "기존 Appium이 아직 종료되지 않았습니다. 잠시 후 다시 시도해 주세요.",
                },
                status_code=409,
            )

    port = appium.get("port", 4723)
    cmd = [
        APPIUM_BIN,
        "--address", "127.0.0.1",
        "--port", str(port),
        "--allow-insecure=uiautomator2:adb_screen_streaming",
    ]
    try:
        log_path = PROJECT_ROOT / "logs" / "appium_server.log"
        log_path.parent.mkdir(exist_ok=True)
        log_fh = open(log_path, "a", encoding="utf-8")  # noqa: WPS515
        _appium_log_fh = log_fh  # GC 방지: 프로세스가 계속 쓰므로 닫지 않음
        proc = subprocess.Popen(
            cmd,
            stdout=log_fh,
            stderr=log_fh,
            env=subprocess_env_for(APPIUM_BIN),
        )
        new_appium = {
            **appium,
            "status": "starting",
            "pid": proc.pid,
            "error_msg": None,
            "started_at": datetime.now().isoformat(),
        }
        update_env_session_sections({"appium": new_appium})
        return JSONResponse(
            {"ok": True, "pid": proc.pid, "port": port, "status": "starting"},
            status_code=202,
        )
    except Exception as exc:
        new_appium = {
            **appium,
            "status": "error",
            "pid": None,
            "error_msg": str(exc),
            "started_at": None,
        }
        update_env_session_sections({"appium": new_appium})
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ── POST /api/env/appium/stop ─────────────────────────────────────

@router.post("/api/env/appium/stop")
def post_appium_stop():
    """Appium 서버를 종료한다.

    가드:
    - Capture Studio 세션 활성 → 403 capture_session_active
    - 파이프라인 실행 중       → 409 pipeline_running

    external 상태에서는 포트 기반으로 PID를 탐색해 종료한다.
    """
    if is_capture_active():
        return JSONResponse(
            {"ok": False, "error": "capture_session_active"}, status_code=403
        )
    if is_pipeline_active():
        return JSONResponse(
            {"ok": False, "error": "pipeline_running"}, status_code=409
        )

    session = load_env_session()
    appium = session.get("appium", {})
    appium_status = appium.get("status", "stopped")
    port = int(appium.get("port", 4723))

    if appium_status == "external":
        # 포트를 점유한 프로세스 PID를 찾아 종료
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=5,
            )
            pids = [int(p) for p in result.stdout.strip().split() if p.strip().isdigit()]
        except Exception:
            pids = []

        if not pids:
            # 포트가 이미 비어 있음 → stopped 처리
            update_env_session_sections(
                {"appium": {**appium, "status": "stopped", "pid": None, "error_msg": None}}
            )
            return JSONResponse({"ok": True, "status": "stopped"})

        for ext_pid in pids:
            try:
                os.kill(ext_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception as exc:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

        if not _wait_for_appium_exit(pids[0], port):
            new_appium = {
                **appium,
                "status": "error",
                "error_msg": "외부 Appium 프로세스가 5초 안에 종료되지 않았습니다.",
            }
            update_env_session_sections({"appium": new_appium})
            return JSONResponse(
                {
                    "ok": False,
                    "error": "appium_stop_timeout",
                    "detail": new_appium["error_msg"],
                },
                status_code=504,
            )

        update_env_session_sections(
            {"appium": {**appium, "status": "stopped", "pid": None, "error_msg": None}}
        )
        return JSONResponse({"ok": True, "status": "stopped"})

    # managed (or unknown) — PID 기반 종료
    pid = appium.get("pid")

    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # 이미 종료된 프로세스
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
        if not _wait_for_appium_exit(pid, port):
            new_appium = {
                **appium,
                "status": "error",
                "error_msg": "Appium 프로세스 또는 포트가 5초 안에 종료되지 않았습니다.",
            }
            update_env_session_sections({"appium": new_appium})
            return JSONResponse(
                {
                    "ok": False,
                    "error": "appium_stop_timeout",
                    "detail": new_appium["error_msg"],
                },
                status_code=504,
            )

    new_appium = {
        **appium,
        "status": "stopped",
        "pid": None,
        "error_msg": None,
    }
    update_env_session_sections({"appium": new_appium})
    return JSONResponse({"ok": True, "status": "stopped"})


# ── POST /api/env/android/avd/start ──────────────────────────────

@router.post("/api/env/android/avd/start")
def post_avd_start(body: Optional[dict] = Body(default=None)):
    """Android AVD(에뮬레이터)를 시작한다.

    가드:
    - Android Capture 세션 활성   → 403 capture_session_active
    - 이미 starting/running 상태  → 409 already_running
    """
    if body is None:
        body = {}

    if is_capture_active("android"):
        return JSONResponse(
            {"ok": False, "error": "capture_session_active"}, status_code=403
        )

    session = load_env_session()
    android = session.get("android", {})
    current_status = android.get("status", "stopped")

    if current_status in ("starting", "running"):
        return JSONResponse({"ok": False, "error": "already_running"}, status_code=409)

    # AVD 이름: body 우선, 없으면 devices.json default
    avd_name: str | None = body.get("avd") if body else None
    if not avd_name:
        default_dev = get_default_device("android", "emulator")
        avd_name = (default_dev or {}).get("avd", "")

    if not avd_name:
        return JSONResponse({"ok": False, "error": "no_avd_configured"}, status_code=422)

    try:
        installed_avds = _list_installed_avds()
    except FileNotFoundError as exc:
        return JSONResponse(
            {"ok": False, "error": "emulator_not_found", "detail": str(exc)},
            status_code=500,
        )
    except (subprocess.SubprocessError, RuntimeError) as exc:
        return JSONResponse(
            {"ok": False, "error": "emulator_list_failed", "detail": str(exc)},
            status_code=500,
        )

    if avd_name not in installed_avds:
        return JSONResponse(
            {
                "ok": False,
                "error": "invalid_avd",
                "detail": f"설치된 Android AVD를 찾을 수 없습니다: {avd_name}",
            },
            status_code=400,
        )

    try:
        log_path = PROJECT_ROOT / "logs" / "android_avd.log"
        log_path.parent.mkdir(exist_ok=True)
        log_fh = open(log_path, "a", encoding="utf-8")  # noqa: WPS515
        subprocess.Popen(
            [EMULATOR_BIN, "-avd", avd_name, "-no-snapshot-load"],
            stdout=log_fh,
            stderr=log_fh,
            env=subprocess_env_for(EMULATOR_BIN),
        )
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    new_android = {
        **android,
        "status": "starting",
        "avd": avd_name,
        "error_msg": None,
        "started_at": datetime.now().isoformat(),
    }
    update_env_session_sections({"android": new_android})
    return JSONResponse(
        {"ok": True, "avd": avd_name, "status": "starting"},
        status_code=202,
    )


# ── POST /api/env/android/avd/stop ───────────────────────────────

@router.post("/api/env/android/avd/stop")
def post_avd_stop(body: Optional[dict] = Body(default=None)):
    """AVD(에뮬레이터)를 종료한다.

    가드:
    - Capture Studio 세션 활성 → 403 capture_session_active
    """
    if is_capture_active("android"):
        return JSONResponse(
            {"ok": False, "error": "capture_session_active"}, status_code=403
        )

    session = load_env_session()
    android = session.get("android", {})
    requested_avd = ((body or {}).get("avd") or "").strip()
    running_avd = (android.get("avd") or "").strip()
    if requested_avd and running_avd and requested_avd != running_avd:
        return JSONResponse(
            {"ok": False, "error": "different_avd_running"}, status_code=409
        )
    serial = android.get("serial")
    target_avd = requested_avd or running_avd
    if not serial or not target_avd:
        return JSONResponse({"ok": False, "error": "not_running"}, status_code=404)
    actual_avd = get_android_avd_name(serial)
    if actual_avd != target_avd:
        return JSONResponse(
            {
                "ok": False,
                "error": "emulator_identity_mismatch",
                "detail": f"{serial} is {actual_avd or 'unknown'}, not {target_avd}",
            },
            status_code=409,
        )
    command = [ADB_BIN, "-s", serial, "emu", "kill"]

    # adb emu kill로 에뮬레이터 종료
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as exc:
        return JSONResponse(
            {"ok": False, "error": "adb_not_found", "detail": str(exc)},
            status_code=500,
        )
    except subprocess.SubprocessError as exc:
        return JSONResponse(
            {"ok": False, "error": "emulator_shutdown_failed", "detail": str(exc)},
            status_code=500,
        )

    if isinstance(result.returncode, int) and result.returncode != 0:
        return JSONResponse(
            {
                "ok": False,
                "error": "emulator_shutdown_failed",
                "detail": _command_detail(result),
            },
            status_code=500,
        )

    new_android = {
        **session.get("android", {}),
        "status": "stopped",
        "avd": None,
        "serial": None,
        "error_msg": None,
        "started_at": None,
    }
    update_env_session_sections({"android": new_android})
    return JSONResponse({"ok": True, "status": "stopped"})


# ── POST /api/env/android/real/connect ───────────────────────────

@router.post("/api/env/android/real/connect")
def post_android_real_connect(body: Optional[dict] = Body(default=None)):
    """WiFi ADB로 Android 실기기를 연결한다.

    가드:
    - Android Capture 세션 활성 → 403 capture_session_active
    body.serial 있으면 해당 serial 사용.
    없으면 devices.json android.real_device[].wifi_ip:5555 사용.
    성공/실패 모두 200, ok 필드로 구분.
    """
    if is_capture_active("android"):
        return JSONResponse(
            {"ok": False, "error": "capture_session_active"}, status_code=403
        )

    if body is None:
        body = {}

    serial: str | None = (body.get("serial") or "").strip() or None
    if not serial:
        serial = _get_wifi_serial()

    if not serial:
        return JSONResponse({"ok": False, "error": "no_wifi_ip_configured"})

    try:
        result = subprocess.run(
            [ADB_BIN, "connect", serial],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = (result.stdout or result.stderr or "").strip()
        if isinstance(result.returncode, int) and result.returncode != 0:
            return JSONResponse({"ok": False, "error": output or "adb connect failed"})
        return JSONResponse({"ok": True, "serial": serial, "output": output})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)})


# ── POST /api/env/android/real/disconnect ────────────────────────

@router.post("/api/env/android/real/disconnect")
def post_android_real_disconnect(body: Optional[dict] = Body(default=None)):
    """WiFi ADB 연결을 해제한다.

    가드:
    - Android Capture 세션 활성 → 403 capture_session_active
    body.serial 있으면 해당 serial 사용.
    없으면 devices.json android.real_device[].wifi_ip:5555 사용.
    성공/실패 모두 200, ok 필드로 구분.
    """
    if is_capture_active("android"):
        return JSONResponse(
            {"ok": False, "error": "capture_session_active"}, status_code=403
        )

    if body is None:
        body = {}

    serial: str | None = (body.get("serial") or "").strip() or None
    if not serial:
        serial = _get_wifi_serial()

    if not serial:
        return JSONResponse({"ok": False, "error": "no_wifi_ip_configured"})

    try:
        result = subprocess.run(
            [ADB_BIN, "disconnect", serial],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = (result.stdout or result.stderr or "").strip()
        if isinstance(result.returncode, int) and result.returncode != 0:
            return JSONResponse({"ok": False, "error": output or "adb disconnect failed"})
        return JSONResponse({"ok": True, "serial": serial, "output": output})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)})


# ── POST /api/env/ios/simulator/start ────────────────────────────

@router.post("/api/env/ios/simulator/start")
def post_simulator_start(body: Optional[dict] = Body(default=None)):
    """iOS Simulator를 부팅한다.

    가드:
    - iOS Capture 세션 활성 → 403 capture_session_active
    """
    if body is None:
        body = {}

    if is_capture_active("ios"):
        return JSONResponse(
            {"ok": False, "error": "capture_session_active"}, status_code=403
        )

    requested_udid = (body.get("udid") or "").strip().upper()
    selected_device = None
    if requested_udid:
        configured = load_devices_json().get("ios", {}).get("simulator", [])
        if isinstance(configured, dict):
            configured = [configured]
        selected_device = next(
            (
                device
                for device in configured
                if (device.get("udid") or "").upper() == requested_udid
            ),
            None,
        )
        if selected_device is None:
            return JSONResponse(
                {"ok": False, "error": "invalid_udid"}, status_code=400
            )

    # UDID is canonical; keep the old simulator-name input for compatibility.
    sim_name: str | None = body.get("simulator") if body else None
    if selected_device:
        sim_name = selected_device.get("deviceName", "")
    elif not sim_name:
        selected_device = get_default_device("ios", "simulator") or {}
        sim_name = selected_device.get("deviceName", "")

    if not sim_name:
        return JSONResponse({"ok": False, "error": "no_simulator_configured"}, status_code=422)

    command_target = requested_udid or (selected_device or {}).get("udid") or sim_name
    session = load_env_session()
    current_ios = detect_ios_runtime(session.get("ios", {}))
    if current_ios.get("status") in ("starting", "running") or current_ios.get("_command_pending"):
        return JSONResponse(
            {
                "ok": False,
                "error": "already_running",
                "udid": current_ios.get("udid"),
            },
            status_code=409,
        )
    command_started_at = datetime.now().isoformat()
    resolved_udid = requested_udid or (selected_device or {}).get("udid")

    # `xcrun simctl boot`를 비동기(Popen)로 실행해 즉시 202를 반환한다.
    # 폴링(`detect_ios_runtime`)이 `simctl list`의 Booted 상태를 감지해
    # starting → running 전환을 처리한다. Android avd/start와 동일한 패턴.
    try:
        subprocess.Popen(
            ["xcrun", "simctl", "boot", command_target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return JSONResponse(
            {"ok": False, "error": "simulator_boot_failed", "detail": str(exc)},
            status_code=500,
        )

    update_env_session_sections({
        "ios": {
            **session.get("ios", {}),
            "status": "starting",
            "simulator": sim_name,
            "udid": resolved_udid,
            "error_msg": None,
            "started_at": command_started_at,
            "_command_pending": False,
            "_command_started_at": None,
        }
    })
    return JSONResponse(
        {
            "ok": True,
            "simulator": sim_name,
            "udid": resolved_udid,
            "status": "starting",
        },
        status_code=202,
    )


# ── POST /api/env/ios/simulator/stop ─────────────────────────────

@router.post("/api/env/ios/simulator/stop")
def post_simulator_stop(body: Optional[dict] = Body(default=None)):
    """iOS Simulator를 종료한다.

    가드:
    - Capture Studio 세션 활성 → 403 capture_session_active
    """
    if is_capture_active("ios"):
        return JSONResponse(
            {"ok": False, "error": "capture_session_active"}, status_code=403
        )

    session = load_env_session()
    ios = session.get("ios", {})
    requested_udid = ((body or {}).get("udid") or "").strip().upper()
    running_udid = (ios.get("udid") or "").strip().upper()
    if requested_udid and running_udid and requested_udid != running_udid:
        return JSONResponse(
            {"ok": False, "error": "different_simulator_running"},
            status_code=409,
        )
    command_target = requested_udid or running_udid
    if not command_target:
        return JSONResponse(
            {"ok": False, "error": "not_running"}, status_code=404
        )
    configured = load_devices_json().get("ios", {}).get("simulator", [])
    if isinstance(configured, dict):
        configured = [configured]
    configured_udids = {
        (device.get("udid") or "").strip().upper() for device in configured
    }
    if command_target not in configured_udids:
        return JSONResponse(
            {"ok": False, "error": "invalid_udid"}, status_code=400
        )

    command_started_at = datetime.now().isoformat()
    update_env_session_sections({"ios": {
        **ios,
        "_command_pending": True,
        "_command_started_at": command_started_at,
    }})
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "shutdown", command_target],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        session = load_env_session()
        update_env_session_sections({"ios": {
            **session.get("ios", {}),
            "error_msg": str(exc),
            "_command_pending": False,
        }})
        return JSONResponse(
            {"ok": False, "error": "simulator_shutdown_failed", "detail": str(exc)},
            status_code=500,
        )

    if isinstance(result.returncode, int) and result.returncode != 0:
        detail = _command_detail(result)
        if "No devices are booted" not in detail:
            session = load_env_session()
            update_env_session_sections({"ios": {
                **session.get("ios", {}),
                "error_msg": detail,
                "_command_pending": False,
            }})
            return JSONResponse(
                {
                    "ok": False,
                    "error": "simulator_shutdown_failed",
                    "detail": detail,
                },
                status_code=500,
            )

    new_ios = {
        **session.get("ios", {}),
        "status": "stopped",
        "simulator": None,
        "udid": None,
        "error_msg": None,
        "started_at": None,
        "_command_pending": False,
        "_command_started_at": None,
    }
    update_env_session_sections({"ios": new_ios})
    return JSONResponse({"ok": True, "status": "stopped"})


# ── Phase 3: POST /api/env/android/real/pair ─────────────────────

@router.post("/api/env/android/real/pair")
def post_android_real_pair(body: Optional[dict] = Body(default=None)):
    """Android WiFi ADB 페어링 (adb pair).

    Android 11+ 무선 디버깅: 페어링 코드 입력 한 번 후 connect 가능해진다.

    body:
        ip: str   — 페어링 IP (기기 화면의 "페어링 코드" 항목에 표시)
        port: str — 페어링 포트 (기기 화면의 6자리 포트)
        code: str — 6자리 페어링 코드
    """
    if is_capture_active("android"):
        return JSONResponse({"ok": False, "error": "capture_session_active"}, status_code=403)

    if body is None:
        body = {}
    ip = (body.get("ip") or "").strip()
    port = str(body.get("port") or "").strip()
    code = str(body.get("code") or "").strip()

    if not ip:
        return JSONResponse({"ok": False, "error": "ip is required"}, status_code=400)
    if not port:
        return JSONResponse({"ok": False, "error": "port is required"}, status_code=400)
    if not code:
        return JSONResponse({"ok": False, "error": "code is required"}, status_code=400)

    try:
        result = subprocess.run(
            [ADB_BIN, "pair", f"{ip}:{port}", code],
            capture_output=True, text=True, timeout=30,
        )
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode != 0 or "failed" in stdout.lower() or "error" in stdout.lower():
            return JSONResponse(
                {"ok": False, "error": "pair_failed", "detail": stderr or stdout},
                status_code=500,
            )
        return JSONResponse({"ok": True, "detail": stdout})
    except FileNotFoundError:
        return JSONResponse({"ok": False, "error": "adb_not_found"}, status_code=500)
    except subprocess.TimeoutExpired:
        return JSONResponse({"ok": False, "error": "timeout"}, status_code=500)


# ── Phase 3: POST /api/env/ios/real/wda_build ────────────────────

@router.post("/api/env/ios/real/wda_build")
def post_ios_real_wda_build(body: Optional[dict] = Body(default=None)):
    """iOS 실기기 WebDriverAgent 빌드 및 설치.

    WDA는 실기기 Appium 세션에 필수다. 시뮬레이터에는 불필요.

    body:
        udid: str     — 실기기 UDID
        team_id: str  — Apple Developer Team ID (10자리)
    """
    if is_capture_active("ios"):
        return JSONResponse({"ok": False, "error": "capture_session_active"}, status_code=403)

    if body is None:
        body = {}
    udid = (body.get("udid") or "").strip()
    team_id = (body.get("team_id") or "").strip()

    if not udid:
        return JSONResponse({"ok": False, "error": "udid is required"}, status_code=400)
    if not team_id:
        return JSONResponse({"ok": False, "error": "team_id is required"}, status_code=400)

    # WDA 소스 위치 탐색: Appium이 설치한 경로
    wda_candidates = [
        Path.home() / ".appium" / "node_modules" / "appium-xcuitest-driver" / "node_modules" / "appium-webdriveragent",
        Path.home() / ".appium" / "node_modules" / "appium-xcuitest-driver" / "WebDriverAgent",
        Path("/usr/local/lib/node_modules/appium/node_modules/appium-xcuitest-driver/node_modules/appium-webdriveragent"),
    ]
    wda_dir = next((p for p in wda_candidates if p.exists()), None)
    if wda_dir is None:
        return JSONResponse(
            {"ok": False, "error": "wda_not_found", "detail": "WebDriverAgent 소스를 찾을 수 없습니다. appium driver install xcuitest 후 재시도하세요."},
            status_code=500,
        )

    proj = wda_dir / "WebDriverAgent.xcodeproj"
    if not proj.exists():
        return JSONResponse(
            {"ok": False, "error": "wda_xcodeproj_not_found", "detail": str(wda_dir)},
            status_code=500,
        )

    cmd = [
        "xcodebuild",
        "-project", str(proj),
        "-scheme", "WebDriverAgentRunner",
        "-destination", f"id={udid}",
        "DEVELOPMENT_TEAM=" + team_id,
        "test",
    ]

    log_path = PROJECT_ROOT / "logs" / "wda_build.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(log_path, "w", encoding="utf-8") as lf:
            proc = subprocess.Popen(cmd, stdout=lf, stderr=lf, cwd=str(wda_dir))
        return JSONResponse({
            "ok": True,
            "pid": proc.pid,
            "log": str(log_path),
            "detail": "WDA 빌드가 백그라운드에서 시작됐습니다. logs/wda_build.log에서 진행 상황을 확인하세요.",
        })
    except FileNotFoundError:
        return JSONResponse({"ok": False, "error": "xcodebuild_not_found"}, status_code=500)
