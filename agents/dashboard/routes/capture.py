"""
routes/capture.py — Capture Studio 전용 엔드포인트.

/capture/session, /capture/tap, /capture/input, /capture/hierarchy,
/capture/save, /capture/generate, /capture/generate_from_actions,
/capture/generated_code, /capture/end, /capture/driver_alive,
/capture/session (GET), /capture/launch, /capture/snapshot,
/capture/back, /capture/context_switch, /capture/validate_locator
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time as _time
from datetime import datetime
from pathlib import Path

import os as _os
import subprocess as _subprocess

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import shared  # noqa: E402
from shared import (  # noqa: E402
    CAPTURES_DIR,
    PROJECT_ROOT,
    TESTCASES_DIR,
    clear_capture_driver,
    set_capture_driver,
)
from utils.state import (  # noqa: E402
    is_capture_active,
    is_pipeline_active,
    load_capture_session,
    load_json,
    save_capture_session,
)
from utils.capture_codegen import (  # noqa: E402
    CaptureCodegenValidationError,
    generate_test_from_actions,
)
from utils.capture_streaming import iter_jpeg_frames  # noqa: E402
from utils.capture_validation import (  # noqa: E402
    CaptureLocatorValidationError,
    validate_locator_xml,
)
from utils.capture_driver import (  # noqa: E402
    IOS_MJPEG_PORT as _IOS_MJPEG_PORT,
    CAPTURE_LAUNCH_TIMEOUTS,
    capture_error,
    save_hierarchy_snapshot as _save_hierarchy_snapshot,
    appium_back as _do_appium_back,
    appium_tap as _do_appium_tap,
    resolve_capture_device,
    get_capture_driver,
    start_appium_session as _do_start_appium_session,
)
from ws import broadcast_timeline_sync  # noqa: E402

router = APIRouter()


# A WebDriverAgent instance is shared by every Capture request.  Starting two
# sessions for the same simulator concurrently makes both Appium requests race
# for WDA's port and can leave WDA running without a session.
_capture_launch_lock = threading.Lock()
_capture_launch_tasks = set()
CAPTURE_LIVENESS_TIMEOUT = 10
CAPTURE_READ_TIMEOUT = 18
CAPTURE_READ_RETRY_DELAY = 0.25


_CAPTURE_IDENTITY_KEYS = ("session_id", "platform", "target", "udid")


class CaptureReadError(Exception):
    def __init__(self, payload):
        self.payload = payload
        super().__init__(payload["error"])


def _same_capture_session(first, second):
    return second.get("active") and all(first.get(key) == second.get(key) for key in _CAPTURE_IDENTITY_KEYS)


def _record_connection_issue(session, driver, recovery):
    """Preserve concurrent actions and one durable notification per incident."""
    with shared._process_lock:
        current = load_capture_session()
        if not _same_capture_session(session, current) or shared.get_capture_driver() is not driver:
            return
        if not current.get("connection_issue_at"):
            save_capture_session({**current, "connection_issue_at": datetime.now().isoformat(),
                                  "connection_recovery": recovery})


def _capture_launch_failure(result, session):
    if "recovery" not in result:
        reason = {
            "capture_device_unavailable": "device unavailable",
            "capture_launch_timeout": TimeoutError("launch deadline expired"),
            "capture_target_mismatch": "invalid configuration",
            "capture_session_changed": "invalid session id",
        }.get(result.get("code"), result.get("error", ""))
        result = {**capture_error(reason), **result}
    _record_connection_issue(session, shared.get_capture_driver(), result["recovery"])
    return result


async def _capture_read(driver, operation):
    """Retry completed transient reads once, bound to the original session."""
    session = load_capture_session()
    deadline = _time.monotonic() + CAPTURE_READ_TIMEOUT
    for attempts in (1, 2):
        if not _same_capture_session(session, load_capture_session()) or get_capture_driver() is not driver:
            payload = capture_error("invalid session id", attempts=attempts - 1, code="capture_session_changed")
            raise CaptureReadError(payload)
        task = asyncio.create_task(asyncio.to_thread(operation))
        try:
            value = await asyncio.wait_for(task, max(0, deadline - _time.monotonic()))
        except Exception as exc:
            if not _same_capture_session(session, load_capture_session()) or get_capture_driver() is not driver:
                raise CaptureReadError(capture_error("invalid session id", attempts=attempts, code="capture_session_changed")) from exc
            # A cancelled executor wait may still be running: never start another.
            outer_timeout = isinstance(exc, asyncio.TimeoutError) and task.cancelled()
            payload = capture_error(exc if not outer_timeout else TimeoutError("read timed out"),
                                    attempts=attempts, read=True)
            if outer_timeout:
                payload["recovery"]["retryable"] = False
                payload["recovery"]["read_retryable"] = False
            if (not outer_timeout and attempts == 1 and payload["recovery"]["retryable"]
                    and _time.monotonic() + CAPTURE_READ_RETRY_DELAY < deadline):
                await asyncio.sleep(CAPTURE_READ_RETRY_DELAY)
                continue
            if payload["reconnect_required"]:
                _record_connection_issue(session, driver, payload["recovery"])
                driver._capture_disconnected = True
            raise CaptureReadError(payload) from exc
        if not _same_capture_session(session, load_capture_session()) or get_capture_driver() is not driver:
            raise CaptureReadError(capture_error("invalid session id", attempts=attempts, code="capture_session_changed"))
        return value, attempts


# ── Appium 드라이버 헬퍼 ──────────────────────────────────────

# ── 엔드포인트 ────────────────────────────────────────────────

@router.post("/capture/session")
async def capture_start_session(request: Request):
    """Capture Studio 세션 시작 또는 기존 세션 재연결."""
    body     = await request.json()
    platform = body.get("platform", "android")

    if platform not in ("android", "ios"):
        return JSONResponse({"ok": False, "error": "invalid platform"}, status_code=400)
    if is_pipeline_active():
        return JSONResponse(
            {"ok": False, "error": "파이프라인이 실행 중입니다. 완료 후 Capture Studio를 시작하세요."},
            status_code=409,
        )

    session_id = body.get("session_id", "")
    existing   = load_capture_session()

    if session_id and existing.get("session_id") == session_id:
        if any(body.get(key) and body[key] != existing.get(key) for key in ("platform", "target", "udid")):
            return JSONResponse({"ok": False, "code": "capture_target_mismatch", "error": "기존 Capture 세션은 선택했던 기기에 연결되어 있습니다. 세션을 종료한 뒤 새 실행 대상을 선택하세요."}, status_code=409)
        resolved = await asyncio.to_thread(resolve_capture_device, existing)
        if not resolved["ok"]:
            return JSONResponse(resolved, status_code=409)
        # Device resolution awaits I/O; admission must be checked again atomically.
        with shared._process_lock:
            if shared.execution_active_locked():
                return JSONResponse({"ok": False, "error": "실행 중입니다. 완료 후 Capture Studio를 시작하세요."}, status_code=409)
            current = load_capture_session()
            if current != existing:
                return JSONResponse({"ok": False, "code": "capture_session_changed", "error": "기기 확인 중 Capture 세션이 변경되었습니다. 현재 세션을 확인한 뒤 다시 시도하세요."}, status_code=409)
            save_capture_session({
                **current,
                "udid": resolved["udid"],
                "device_name": resolved["device_name"],
                "active": True,
                "last_activity_at": datetime.now().isoformat(),
            })
        mode = existing.get("screenshot_mode", "mjpeg")
        reconnect_resp: dict = {
            "ok":              True,
            "session_id":      session_id,
            "reconnected":     True,
            "screenshot_mode": mode,
        }
        if mode == "mjpeg":
            reconnect_resp["mjpeg_url"] = f"http://localhost:{existing.get('mjpeg_port', 8093)}"
        return JSONResponse(reconnect_resp)

    if is_capture_active():
        return JSONResponse({"ok": False, "code": "capture_session_active", "error": "기존 Capture 세션을 종료한 뒤 새 실행 대상으로 시작하세요."}, status_code=409)
    resolved = await asyncio.to_thread(resolve_capture_device, body)
    if not resolved["ok"]:
        return JSONResponse(resolved, status_code=400 if resolved.get("code") == "invalid_capture_target" else 409)
    import uuid
    new_session_id = str(uuid.uuid4())
    # iOS: WDA 내장 MJPEG 포트 9100 / Android: 8093 (body 값 우선)
    mjpeg_port = body.get("mjpeg_port", _IOS_MJPEG_PORT if platform == "ios" else 8093)
    screenshot_mode = "mjpeg"  # iOS·Android 모두 MJPEG 사용

    session_data = {
        "session_id":        new_session_id,
        "platform":          platform,
        "target":            body.get("target", "emulator"),
        "app_package":       body.get("app_package", ""),
        "app_activity":      body.get("app_activity", ""),
        "bundle_id":         body.get("bundle_id", ""),
        "device_name":       resolved["device_name"],
        "udid":              resolved["udid"],
        "avd":               body.get("avd", ""),
        "tc_group":          body.get("tc_group", ""),
        "mjpeg_port":        mjpeg_port,
        "screenshot_mode":   screenshot_mode,
        "active":            True,
        "started_at":        datetime.now().isoformat(),
        "last_activity_at":  datetime.now().isoformat(),
        "actions":           [],
    }
    with shared._process_lock:
        if shared.execution_active_locked():
            return JSONResponse({"ok": False, "error": "실행 중입니다. 완료 후 Capture Studio를 시작하세요."}, status_code=409)
        if is_capture_active():
            return JSONResponse({"ok": False, "code": "capture_session_active", "error": "기존 Capture 세션을 종료한 뒤 새 실행 대상으로 시작하세요."}, status_code=409)
        save_capture_session(session_data)

    session_dir = CAPTURES_DIR / new_session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "native").mkdir(exist_ok=True)
    (session_dir / "webview").mkdir(exist_ok=True)
    session_dir.joinpath("session.json").write_text(
        json.dumps(session_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    session_dir.joinpath("actions.json").write_text("[]", encoding="utf-8")

    try:
        _driver = get_capture_driver()
        _size = await asyncio.wait_for(asyncio.to_thread(_driver.get_window_size), CAPTURE_LIVENESS_TIMEOUT) if _driver else {}
        device_width  = _size.get("width",  1080)
        device_height = _size.get("height", 1920)
    except Exception:
        device_width  = 1080
        device_height = 1920

    resp: dict = {
        "ok":               True,
        "session_id":       new_session_id,
        "reconnected":      False,
        "screenshot_mode":  screenshot_mode,
        "session_dir":      str(session_dir.relative_to(PROJECT_ROOT)),
        "device_width":     device_width,
        "device_height":    device_height,
    }
    if screenshot_mode == "mjpeg":
        resp["mjpeg_url"] = f"http://localhost:{mjpeg_port}"
    return JSONResponse(resp)


@router.post("/capture/tap")
async def capture_tap(request: Request):
    """요소 탭 실행 및 Action Timeline 기록."""
    body    = await request.json()
    session = load_capture_session()
    if not session.get("active"):
        return JSONResponse({"ok": False, "error": "활성 Capture 세션이 없습니다"}, status_code=409)

    img_width     = body.get("img_width", 360)
    display_width = body.get("display_width", 1080)
    scale         = display_width / img_width if img_width > 0 else 1.0
    device_x      = int(body.get("x", 0) * scale)
    device_y      = int(body.get("y", 0) * scale)

    action_index = len(session.get("actions", [])) + 1
    action = {
        "index":       action_index,
        "action":      "tap",
        "surface":     "native",
        "context":     body.get("context", "NATIVE_APP"),
        "screen":      session.get("current_screen", ""),
        "target_ref":  "",
        "snapshot_id": f"{action_index:04d}",
        "locator":     {},
        "device_x":    device_x,
        "device_y":    device_y,
        "source":      "user",
        "timestamp":   datetime.now().isoformat(),
    }

    # session["actions"]를 단일 소스로 사용 (actions.json은 참조용 덤프)
    # 이전 구현에서 actions.json을 읽어 덮어쓰면 back/scroll/context_switch 액션이 유실됨
    actions = list(session.get("actions", []))
    actions.append(action)

    session_dir  = CAPTURES_DIR / session["session_id"]
    actions_path = session_dir / "actions.json"
    actions_path.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")

    save_capture_session({**session, "last_activity_at": datetime.now().isoformat(), "actions": actions})
    broadcast_timeline_sync({
        "type": "action_added", "action": action, "source": "user",
        "platform": session.get("platform", ""),
        "summary": f"({device_x},{device_y})", "ok": True,
    })

    loop = asyncio.get_running_loop()
    tap_ok = await loop.run_in_executor(None, _do_appium_tap, device_x, device_y, session["session_id"])
    if not tap_ok:
        return JSONResponse({
            "ok": False,
            "error": "Appium 탭 실패 — 드라이버 연결을 확인하거나 '🔄 세션 재연결' 버튼을 눌러주세요",
            "action": action,
        })

    return JSONResponse({"ok": True, "action": action})


@router.post("/capture/input")
async def capture_input(request: Request):
    """Input 실행 및 기록."""
    body    = await request.json()
    session = load_capture_session()
    if not session.get("active"):
        return JSONResponse({"ok": False, "error": "활성 Capture 세션이 없습니다"}, status_code=409)

    is_secret    = bool(body.get("is_secret", False))
    raw_value    = str(body.get("value", ""))
    stored_value = "***" if is_secret else raw_value

    action_index = len(session.get("actions", [])) + 1
    action = {
        "index":         action_index,
        "action":        "input",
        "surface":       "native",
        "context":       body.get("context", "NATIVE_APP"),
        "screen":        session.get("current_screen", ""),
        "target_ref":    body.get("target_ref", ""),
        "snapshot_id":   f"{action_index:04d}",
        "locator":       {},
        "input_key":     body.get("input_key", f"input_{action_index}"),
        "is_secret":     is_secret,
        "value_preview": stored_value,
        "source":        "user",
        "timestamp":     datetime.now().isoformat(),
    }

    # session["actions"]를 단일 소스로 사용 (actions.json은 참조용 덤프)
    actions = list(session.get("actions", []))
    actions.append(action)

    session_dir  = CAPTURES_DIR / session["session_id"]
    actions_path = session_dir / "actions.json"
    actions_path.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")

    save_capture_session({**session, "last_activity_at": datetime.now().isoformat(), "actions": actions})
    broadcast_timeline_sync({
        "type": "action_added", "action": action, "source": "user",
        "platform": session.get("platform", ""),
        "summary": stored_value, "ok": True,
    })
    return JSONResponse({"ok": True, "action": action})


@router.get("/capture/hierarchy")
async def capture_hierarchy(session_id: str = "", context: str = "native"):
    """마지막 저장된 hierarchy를 반환."""
    session = load_capture_session()
    if not session.get("active"):
        return JSONResponse({"ok": False, "error": "활성 Capture 세션이 없습니다"}, status_code=409)

    session_dir = CAPTURES_DIR / session.get("session_id", "")
    subdir      = session_dir / ("webview" if context == "webview" else "native")
    if not subdir.exists():
        return JSONResponse({"ok": True, "hierarchy": None, "snapshot_count": 0})

    xml_files = sorted(subdir.glob("*.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not xml_files:
        return JSONResponse({"ok": True, "hierarchy": None, "snapshot_count": 0})

    latest = xml_files[0]
    return JSONResponse({
        "ok":             True,
        "snapshot_id":    latest.stem,
        "hierarchy":      latest.read_text(encoding="utf-8", errors="replace"),
        "snapshot_count": len(xml_files),
        "context":        context,
    })


@router.post("/capture/save")
async def capture_save(request: Request):
    """Capture 세션 결과를 TC Markdown, screens.json, locators.json에 저장."""
    body    = await request.json()
    session = load_capture_session()

    tc_id             = str(body.get("tc_id", "tc_001")).strip()
    title             = str(body.get("title", "")).strip()
    platform          = body.get("platform", session.get("platform", "android"))
    tc_group          = str(body.get("tc_group", session.get("tc_group", "default"))).strip()
    steps             = body.get("steps", [])
    expected          = body.get("expected", [])
    approved_locators = body.get("approved_locators", {})
    overwrite         = bool(body.get("overwrite", False))

    if not tc_id or not title or platform not in ("android", "ios"):
        return JSONResponse(
            {"ok": False, "error": "tc_id, title, platform이 필요합니다"}, status_code=400
        )

    has_missing_expected = any(not e for e in expected) if expected else len(steps) > 0
    quality_tag = "low-quality" if has_missing_expected else ""

    tc_dir  = TESTCASES_DIR / platform / tc_group
    tc_dir.mkdir(parents=True, exist_ok=True)
    tc_path = tc_dir / f"{tc_id}.md"

    if tc_path.exists() and not overwrite:
        return JSONResponse({
            "ok":      False,
            "error":   f"파일이 이미 존재합니다: {tc_path.relative_to(PROJECT_ROOT)}",
            "conflict": True,
        }, status_code=409)

    steps_md    = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) if steps else "_(steps 없음)_"
    expected_md = (
        "\n".join(
            f"{i+1}. {e}" if e else f"{i+1}. _(기대 결과 미입력)_"
            for i, e in enumerate(expected)
        )
        if expected
        else "_(기대 결과 없음)_"
    )
    quality_line = "\n> ⚠️ 품질 낮음: 기대 결과가 누락된 step이 있습니다.\n" if quality_tag else ""

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

    saved_locators: list[str] = []
    if approved_locators:
        locators_path = PROJECT_ROOT / "config" / "locators.json"
        locators = load_json(locators_path) or {}
        for key, locator_data in approved_locators.items():
            locators[key] = locator_data
            saved_locators.append(key)
        locators_path.write_text(json.dumps(locators, ensure_ascii=False, indent=2), encoding="utf-8")

    screens_path = PROJECT_ROOT / "config" / "screens.json"
    try:
        screens = load_json(screens_path) or {}
        if tc_group not in screens:
            app_package = session.get("app_package", "")
            screens[tc_group] = {
                "name":  tc_group,
                "entry": {"action": "launch", "app": app_package},
            }
            screens_path.write_text(json.dumps(screens, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    if session.get("active"):
        save_capture_session({
            **session,
            "active":     False,
            "end_reason": "saved",
            "ended_at":   datetime.now().isoformat(),
        })

    return JSONResponse({
        "ok":             True,
        "tc_file":        str(tc_path.relative_to(PROJECT_ROOT)),
        "saved_locators": saved_locators,
        "quality_tag":    quality_tag,
        "next_actions":   ["generate", "run", "open_tc"],
    })


@router.post("/capture/generate")
async def capture_generate(request: Request):
    """저장된 TC를 기반으로 02_generate.py를 실행하여 pytest 코드 생성."""
    body     = await request.json()
    platform = body.get("platform", "android")
    if platform not in ("android", "ios"):
        return JSONResponse(
            {"ok": False, "error": "platform은 android 또는 ios여야 합니다"}, status_code=400
        )
    import sys as _sys
    script_path = PROJECT_ROOT / "scripts" / "02_generate.py"
    try:
        proc = await asyncio.create_subprocess_exec(
            _sys.executable, str(script_path),
            "--platform", platform, "--strict-locators",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        output = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        return JSONResponse({
            "ok":         proc.returncode == 0,
            "output":     output,
            "returncode": proc.returncode,
        })
    except asyncio.TimeoutError:
        return JSONResponse({"ok": False, "output": "타임아웃 (120초)", "returncode": -1})
    except Exception as e:
        return JSONResponse({"ok": False, "output": str(e), "returncode": -1})


@router.post("/capture/generate_from_actions")
async def capture_generate_from_actions(request: Request):
    """actions 배열을 받아 Appium pytest 코드를 자동 생성."""
    body = await request.json()
    session = load_capture_session()
    try:
        payload = generate_test_from_actions(body, session, PROJECT_ROOT)
    except CaptureCodegenValidationError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return JSONResponse(payload)


@router.get("/capture/generated_code")
async def capture_generated_code(platform: str = "android"):
    """가장 최근 생성된 테스트 파일 내용 반환."""
    gen_dir = PROJECT_ROOT / "tests" / "generated" / platform
    if not gen_dir.exists():
        return JSONResponse({"ok": False, "error": f"생성된 코드 없음: {gen_dir}"})
    py_files = sorted(gen_dir.rglob("*.py"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not py_files:
        return JSONResponse({"ok": False, "error": "생성된 .py 파일 없음"})
    latest = py_files[0]
    return JSONResponse({
        "ok":   True,
        "file": str(latest.relative_to(PROJECT_ROOT)),
        "code": latest.read_text(encoding="utf-8"),
    })


@router.post("/capture/end")
async def capture_end_session(request: Request):
    """Capture 세션 명시적 종료 (저장 없이)."""
    body       = await request.json()
    session    = load_capture_session()
    session_id = body.get("session_id", session.get("session_id", ""))
    if session.get("session_id") != session_id:
        return JSONResponse(
            {"ok": False, "error": "session_id가 일치하지 않습니다"}, status_code=400
        )
    save_capture_session({
        **session,
        "active":     False,
        "end_reason": "user_ended",
        "ended_at":   datetime.now().isoformat(),
    })

    driver = clear_capture_driver()
    if driver is not None:
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, driver.quit)
        except Exception:
            # Metadata is already inactive; a dead Appium connection must not
            # prevent the user from ending the Capture session.
            pass
    return JSONResponse({"ok": True, "message": "Capture 세션 종료됨"})


@router.post("/capture/clear_actions")
async def capture_clear_actions(request: Request):
    """Action Timeline 초기화 — session['actions']와 actions.json을 모두 비웁니다."""
    body       = await request.json()
    session    = load_capture_session()
    session_id = body.get("session_id", session.get("session_id", ""))
    if session.get("session_id") != session_id:
        return JSONResponse(
            {"ok": False, "error": "session_id가 일치하지 않습니다"}, status_code=400
        )
    cleared_count = len(session.get("actions", []))
    session["actions"] = []
    save_capture_session(session)
    # actions.json 파일도 동기화
    actions_path = CAPTURES_DIR / session_id / "actions.json"
    if actions_path.parent.exists():
        actions_path.write_text(json.dumps([], ensure_ascii=False), encoding="utf-8")
    return JSONResponse({"ok": True, "cleared": cleared_count})


@router.get("/capture/page_source_hash")
async def capture_page_source_hash():
    """Read the current screen hash with one bounded transient retry."""
    import hashlib
    driver = get_capture_driver()
    if driver is None:
        return JSONResponse({**capture_error("invalid session id"), "hash": None})
    try:
        src, attempts = await _capture_read(driver, lambda: driver.page_source)
        digest = hashlib.md5(src[:8192].encode("utf-8", errors="ignore")).hexdigest()[:8]
        return JSONResponse({"ok": True, "hash": digest, "attempts": attempts})
    except CaptureReadError as exc:
        return JSONResponse({**exc.payload, "hash": None})


@router.get("/capture/screenshot")
async def capture_screenshot():
    driver = get_capture_driver()
    if driver is None:
        return JSONResponse(capture_error("invalid session id"), status_code=409)
    try:
        data, attempts = await _capture_read(driver, driver.get_screenshot_as_base64)
        return JSONResponse({"ok": True, "data": data, "attempts": attempts,
                             "ts": datetime.now().isoformat()})
    except CaptureReadError as exc:
        return JSONResponse(exc.payload, status_code=500)


@router.get("/capture/driver_alive")
async def capture_driver_alive():
    driver = get_capture_driver()
    if driver is None:
        return JSONResponse({**capture_error("invalid session id"), "alive": False})
    try:
        _, attempts = await _capture_read(driver, driver.get_window_size)
        return JSONResponse({"alive": True, "reconnect_required": False, "attempts": attempts})
    except CaptureReadError as exc:
        return JSONResponse({**exc.payload, "alive": False})


@router.get("/capture/session")
async def capture_get_session():
    """현재 Capture 세션 상태 반환."""
    session = load_capture_session()
    active  = is_capture_active()
    return JSONResponse({
        "ok":      True,
        "active":  active,
        "reconnect_required": active and get_capture_driver() is None,
        "launch_in_progress": _capture_launch_lock.locked(),
        "session": session if active else {},
    })


@router.post("/capture/launch")
async def capture_launch(request: Request):
    """Launch with a bounded response and retain ownership until worker cleanup."""
    body       = await request.json()
    session_id = body.get("session_id", "")
    session    = load_capture_session()
    if not is_capture_active() or session.get("session_id") != session_id:
        return JSONResponse({"ok": False, "error": "Capture 세션 없음 또는 불일치"}, status_code=400)

    if not _capture_launch_lock.acquire(blocking=False):
        return JSONResponse({
            "ok": False,
            "error": "iOS/Android 앱 실행이 이미 진행 중입니다. 잠시 기다려 주세요.",
            "code": "capture_launch_in_progress",
        }, status_code=409)

    cancelled = threading.Event()
    deadline = _time.monotonic() + CAPTURE_LAUNCH_TIMEOUTS[session.get("platform", "android")]
    worker_session = {**session, "_launch_cancelled": cancelled, "_launch_deadline": deadline}
    with shared._process_lock:
        if shared.execution_active_locked():
            _capture_launch_lock.release()
            return JSONResponse({"ok": False, "code": "capture_execution_conflict", "error": "실행 중입니다. 완료 후 Capture 세션을 재연결하세요."}, status_code=409)
        current = load_capture_session()
        if not current.get("active") or any(current.get(key) != session.get(key) for key in ("session_id", "platform", "target", "udid")):
            _capture_launch_lock.release()
            return JSONResponse({"ok": False, "code": "capture_session_changed", "error": "Capture 세션이 변경되었습니다. 현재 세션을 확인한 뒤 다시 시도하세요."}, status_code=409)
        shared._capture_launch_active = True

    async def finish_launch():
        driver = None
        published = False
        try:
            result = await asyncio.to_thread(_do_start_appium_session, worker_session)
            driver = result.pop("_driver", None) or worker_session.get("_launch_driver")
            if cancelled.is_set() or _time.monotonic() >= deadline:
                return _capture_launch_failure({"ok": False, "code": "capture_launch_timeout", "reconnect_required": True, "error": "앱 실행 제한 시간이 지났습니다. 작성 내용은 유지됩니다. 같은 기기로 세션 재연결을 눌러주세요."}, session)
            if result.get("ok") and result.get("udid"):
                with shared._process_lock:
                    updated = load_capture_session()
                    if not updated.get("active") or any(updated.get(key) != session.get(key) for key in ("session_id", "platform", "target", "udid")):
                        return {"ok": False, "code": "capture_target_mismatch", "error": "Capture 세션이 변경되어 이전 앱 실행을 취소했습니다. 실행 대상을 다시 확인하세요."}
                    updated.pop("connection_issue_at", None)
                    updated.pop("connection_recovery", None)
                    save_capture_session({**updated, "device_name": result["device_name"], "udid": result["udid"]})
                    if driver is not None:
                        set_capture_driver(driver)
                        published = True
            return result if result.get("ok") else _capture_launch_failure(result, session)
        except Exception as exc:
            return _capture_launch_failure(capture_error(exc), session)
        finally:
            driver = driver or worker_session.get("_launch_driver")
            if driver is not None and not published:
                try:
                    await asyncio.to_thread(driver.quit)
                except Exception:
                    pass
            with shared._process_lock:
                shared._capture_launch_active = False
                _capture_launch_lock.release()

    # Shield keeps ownership until the real thread and late-driver cleanup end.
    task = asyncio.create_task(finish_launch())
    _capture_launch_tasks.add(task)
    task.add_done_callback(_capture_launch_tasks.discard)
    try:
        result = await asyncio.wait_for(asyncio.shield(task), CAPTURE_LAUNCH_TIMEOUTS[session.get("platform", "android")])
        status = 200 if result["ok"] else (504 if result.get("code") == "capture_launch_timeout" else 409 if result.get("code", "").startswith("capture_") else 500)
        return JSONResponse(result, status_code=status)
    except asyncio.TimeoutError:
        cancelled.set()
        failure = _capture_launch_failure({"ok": False, "code": "capture_launch_timeout", "reconnect_required": True,
                             "error": "앱 실행 제한 시간이 지났습니다. 작성 내용은 유지됩니다. 이전 연결 정리가 끝난 뒤 같은 기기로 세션 재연결을 누르세요."}, session)
        return JSONResponse(failure, status_code=504)
    except asyncio.CancelledError:
        cancelled.set()
        raise


@router.post("/capture/snapshot")
async def capture_snapshot(request: Request):
    """현재 화면 hierarchy 스냅샷 캡처."""
    body       = await request.json()
    session_id = body.get("session_id", "")
    context    = body.get("context", "native")
    session    = load_capture_session()
    if not is_capture_active() or session.get("session_id") != session_id:
        return JSONResponse({"ok": False, "error": "세션 없음"}, status_code=400)

    driver = get_capture_driver()
    if driver is None:
        return JSONResponse(capture_error("invalid session id"), status_code=409)

    # Reload under the shared lock so concurrent draft/incident updates survive.
    with shared._process_lock:
        current = load_capture_session()
        if not _same_capture_session(session, current) or get_capture_driver() is not driver:
            return JSONResponse(capture_error("invalid session id", code="capture_session_changed"), status_code=409)
        save_capture_session({**current, "last_activity_at": datetime.now().isoformat()})

    try:
        xml, attempts = await _capture_read(driver, lambda: driver.page_source)
    except CaptureReadError as exc:
        return JSONResponse(exc.payload, status_code=500)
    try:
        # No await between target validation and persisting the successful read.
        snap_id = _save_hierarchy_snapshot(session_id, xml, context)
        return JSONResponse({"ok": True, "snapshot_id": snap_id, "context": context, "attempts": attempts})
    except OSError:
        return JSONResponse(capture_error({"error": "invalid configuration: Capture snapshot file write failed", "error_type": "configuration"}, attempts=attempts), status_code=500)


@router.post("/capture/back")
async def capture_back(request: Request):
    """디바이스 Back 버튼 이벤트 기록."""
    body       = await request.json()
    session    = load_capture_session()
    session_id = body.get("session_id", "")
    if not is_capture_active() or session.get("session_id") != session_id:
        return JSONResponse({"ok": False, "error": "세션 없음 또는 불일치"}, status_code=400)

    action = {
        "index":      len(session.get("actions", [])) + 1,
        "action":     "back",
        "context":    body.get("context", "native"),
        "source":     "user",
        "timestamp":  datetime.now().isoformat(),
        "target_ref": None,
    }
    actions = list(session.get("actions", []))
    actions.append(action)
    session["actions"] = actions
    session["last_activity_at"] = datetime.now().isoformat()
    save_capture_session(session)
    # actions.json 동기화
    actions_path = CAPTURES_DIR / session_id / "actions.json"
    if actions_path.parent.exists():
        actions_path.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")

    broadcast_timeline_sync({
        **action, "type": "action", "source": "user",
        "platform": session.get("platform", ""),
        "summary": "back", "ok": True,
    })

    loop = asyncio.get_running_loop()
    back_ok = await loop.run_in_executor(None, _do_appium_back, session_id)
    if not back_ok:
        return JSONResponse({
            "ok": False,
            "error": "Back 실행 실패 — 드라이버 연결을 확인하거나 '🔄 세션 재연결' 버튼을 눌러주세요",
            "action": action,
        })

    return JSONResponse({"ok": True, "action": action})


@router.post("/capture/scroll")
async def capture_scroll(request: Request):
    """실제 디바이스 스크롤 실행 + Action Timeline 기록.

    direction: 'down'(기본) | 'up'
    blocking: True — 스크롤 완료 후 응답 (E2E 스크립트에서 hierarchy 재수집 용)
    """
    body       = await request.json()
    session    = load_capture_session()
    session_id = body.get("session_id", "")
    if not is_capture_active() or session.get("session_id") != session_id:
        return JSONResponse({"ok": False, "error": "세션 없음 또는 불일치"}, status_code=400)

    direction = body.get("direction", "down")
    start_x   = body.get("start_x")
    start_y   = body.get("start_y")
    end_x     = body.get("end_x")
    end_y     = body.get("end_y")

    # 좌표 기반일 때 action_type 결정 (direction 문자열은 fallback)
    if start_x is not None and end_x is not None:
        action_type = "scroll_down" if (end_y or 0) < (start_y or 0) else "scroll_up"
    else:
        action_type = "scroll_down" if direction != "up" else "scroll_up"

    action = {
        "index":      len(session.get("actions", [])) + 1,
        "action":     action_type,
        "context":    body.get("context", "native"),
        "source":     "user",
        "timestamp":  datetime.now().isoformat(),
        "target_ref": None,
    }
    actions = list(session.get("actions", []))
    actions.append(action)
    session["actions"] = actions
    session["last_activity_at"] = datetime.now().isoformat()
    save_capture_session(session)
    # actions.json 동기화
    actions_path = CAPTURES_DIR / session_id / "actions.json"
    if actions_path.parent.exists():
        actions_path.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")
    broadcast_timeline_sync({
        **action, "type": "action", "source": "user",
        "platform": session.get("platform", ""),
        "summary": direction, "ok": True,
    })

    def _do_scroll() -> bool:
        driver = get_capture_driver()
        if driver is None:
            return False
        try:
            if start_x is not None and end_x is not None:
                # 좌표 기반 스와이프
                driver.swipe(start_x, start_y, end_x, end_y, duration=300)
            else:
                sz = driver.get_window_size()
                w, h = sz["width"], sz["height"]
                if direction == "up":
                    driver.swipe(w // 2, int(h * 0.3), w // 2, int(h * 0.7), 600)
                else:
                    driver.swipe(w // 2, int(h * 0.7), w // 2, int(h * 0.3), 600)
            _time.sleep(0.8)  # 스크롤 애니메이션 대기
            return True
        except Exception:
            return False

    loop = asyncio.get_running_loop()
    ok_scroll = await loop.run_in_executor(None, _do_scroll)
    return JSONResponse({"ok": ok_scroll, "action": action, "direction": direction})


@router.post("/capture/context_switch")
async def capture_context_switch(request: Request):
    """WebView ↔ Native 컨텍스트 전환 기록."""
    body       = await request.json()
    session    = load_capture_session()
    session_id = body.get("session_id", "")
    if not is_capture_active() or session.get("session_id") != session_id:
        return JSONResponse({"ok": False, "error": "세션 없음 또는 불일치"}, status_code=400)

    target_ctx = body.get("to_context", "native")
    action = {
        "index":      len(session.get("actions", [])) + 1,
        "action":     "context_switch",
        "context":    body.get("from_context", "native"),
        "to_context": target_ctx,
        "source":     "user",
        "timestamp":  datetime.now().isoformat(),
        "target_ref": None,
    }
    actions = list(session.get("actions", []))
    actions.append(action)
    session["actions"] = actions
    session["last_activity_at"] = datetime.now().isoformat()
    save_capture_session(session)
    # actions.json 동기화
    actions_path = CAPTURES_DIR / session_id / "actions.json"
    if actions_path.parent.exists():
        actions_path.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")

    broadcast_timeline_sync({
        **action, "type": "action", "source": "user",
        "platform": session.get("platform", ""),
        "summary": f"{body.get('from_context','native')} -> {target_ctx}", "ok": True,
    })
    return JSONResponse({"ok": True, "action": action, "switched_to": target_ctx})


@router.post("/capture/validate_locator")
async def capture_validate_locator(request: Request):
    """Locator 후보 단일성 검증 (XML-only, Appium 연결 불필요)."""
    body       = await request.json()
    session    = load_capture_session()
    session_id = body.get("session_id", "")
    if not is_capture_active() or session.get("session_id") != session_id:
        return JSONResponse({"ok": False, "error": "세션 없음 또는 불일치"}, status_code=400)

    strategy = body.get("strategy", "")
    value    = body.get("value", "")
    context  = body.get("context", "native")

    caps_dir  = CAPTURES_DIR / session_id / context
    xml_files = sorted(caps_dir.glob("hierarchy_*.xml"), reverse=True) if caps_dir.exists() else []
    if not xml_files:
        return JSONResponse(
            {"ok": False, "error": "hierarchy 없음 — Hierarchy 새로고침 후 재시도"}, status_code=404
        )

    try:
        result = validate_locator_xml(
            xml_files[0].read_text(encoding="utf-8", errors="replace"),
            session.get("platform", "android"),
            strategy,
            value,
        )
    except CaptureLocatorValidationError as exc:
        return JSONResponse(
            {"ok": False, "error": exc.message},
            status_code=exc.status_code,
        )
    return JSONResponse({"ok": True, **result})


@router.get("/capture/stream/{platform}")
async def capture_stream(platform: str, request: Request):
    """ffmpeg 기반 고속 MJPEG 스트리밍 — Android(adb screenrecord) / iOS(AVFoundation)."""
    session = load_capture_session()
    if not session.get("active") or session.get("platform") != platform:
        return JSONResponse({"ok": False, "code": "capture_target_mismatch", "error": "활성 Capture 세션의 실행 대상과 일치하지 않습니다."}, status_code=409)
    resolved = await asyncio.to_thread(resolve_capture_device, session)
    if not resolved["ok"]:
        return JSONResponse(resolved, status_code=409)
    if platform == "ios" and resolved["mode"] == "real_device":
        return JSONResponse({"ok": False, "error": "iOS 실기기는 WDA MJPEG 스트림을 사용하세요."}, status_code=409)

    async def generate():
        procs: list = []
        try:
            if platform == "android":
                adb_cmd = ["adb", "-s", resolved["udid"]]
                adb_cmd += ["exec-out", "screenrecord", "--output-format=h264", "--bit-rate=2M", "-"]

                adb_proc = _subprocess.Popen(
                    adb_cmd,
                    stdout=_subprocess.PIPE, stderr=_subprocess.DEVNULL
                )
                ffmpeg_proc = _subprocess.Popen(
                    ["ffmpeg", "-probesize", "5M",
                     "-i", "pipe:0",
                     "-f", "image2pipe", "-vcodec", "mjpeg",
                     "-r", "20", "-q:v", "5",
                     "-vf", "scale=400:-2",
                     "pipe:1"],
                    stdin=adb_proc.stdout,
                    stdout=_subprocess.PIPE, stderr=_subprocess.DEVNULL
                )
                procs = [adb_proc, ffmpeg_proc]
                stdout = ffmpeg_proc.stdout

            else:  # ios — simctl screenshot 폴링 (시뮬레이터 화면만 캡처)
                import tempfile as _tempfile
                boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                tmp = _tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                tmp.close()
                try:
                    while True:
                        if await request.is_disconnected():
                            break
                        loop = asyncio.get_event_loop()
                        ret = await loop.run_in_executor(
                            None,
                            lambda: _subprocess.run(
                                ["xcrun", "simctl", "io", resolved["udid"], "screenshot",
                                 "--type", "jpeg", tmp.name],
                                capture_output=True
                            ).returncode
                        )
                        if ret != 0:
                            await asyncio.sleep(0.5)
                            continue
                        with open(tmp.name, "rb") as f:
                            frame_data = f.read()
                        if frame_data:
                            yield boundary + frame_data + b"\r\n"
                finally:
                    try:
                        _os.unlink(tmp.name)
                    except Exception:
                        pass
                return

            loop = asyncio.get_event_loop()
            boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
            frame_iter = iter_jpeg_frames(stdout)
            while True:
                if await request.is_disconnected():
                    break
                frame = await loop.run_in_executor(None, next, frame_iter, None)
                if frame is None:
                    break
                yield boundary + frame + b"\r\n"
        finally:
            for p in procs:
                try:
                    p.kill()
                    p.wait(timeout=2)
                except Exception:
                    pass

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache"},
    )
