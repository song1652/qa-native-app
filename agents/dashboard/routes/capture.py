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
import time as _time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import (  # noqa: E402
    CAPTURES_DIR,
    PROJECT_ROOT,
    TESTCASES_DIR,
    clear_capture_driver,
    get_capture_driver,
    set_capture_driver,
)
from utils.state import (  # noqa: E402
    is_capture_active,
    is_pipeline_active,
    load_capture_session,
    load_json,
    save_capture_session,
)
from ws import broadcast_timeline_sync  # noqa: E402

router = APIRouter()


# ── Appium 드라이버 헬퍼 ──────────────────────────────────────

def _get_appium_import():
    """appium webdriver + ArgOptions 임포트 (venv 우선)."""
    venv_site = PROJECT_ROOT / ".venv" / "lib"
    if venv_site.exists():
        for p in sorted(venv_site.iterdir()):
            site = p / "site-packages"
            if site.exists() and str(site) not in sys.path:
                sys.path.insert(0, str(site))
    from appium import webdriver as _aw
    from selenium.webdriver.common.options import ArgOptions as _ao

    class _RawOptions(_ao):
        @property
        def default_capabilities(self):
            return {}

    return _aw, _RawOptions


def _take_hierarchy_snapshot(session_id: str, driver, context: str = "native") -> str:
    """page_source를 캡처해 disk에 저장하고 snapshot_id 반환."""
    xml    = driver.page_source
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    snap_id = f"hierarchy_{ts}"
    subdir = CAPTURES_DIR / session_id / context
    subdir.mkdir(parents=True, exist_ok=True)
    (subdir / f"{snap_id}.xml").write_text(xml, encoding="utf-8")
    return snap_id


def _friendly_appium_error(exc: Exception) -> str:
    """Appium/Selenium 예외를 비개발자가 이해할 수 있는 메시지로 변환."""
    raw = str(exc)
    low = raw.lower()
    # 연결 거부 — Appium 서버 미기동
    if "connection refused" in low or "econnrefused" in low:
        return "Appium 서버에 연결할 수 없습니다. 터미널에서 'appium --address 0.0.0.0 --port 4723'을 먼저 실행하세요."
    # 에뮬레이터/시뮬레이터 없음
    if "no device" in low or "no emulator" in low or "device not found" in low:
        return "연결된 디바이스를 찾을 수 없습니다. 에뮬레이터/시뮬레이터가 실행 중인지 확인하세요."
    # App Activity 오류
    if "activity" in low and ("not found" in low or "unable to find" in low or "does not exist" in low):
        return "App Activity를 찾을 수 없습니다. 대소문자를 확인하세요 (예: .MainActivity 또는 com.example.app.MainActivity)."
    # App Package 오류
    if "package" in low and ("not found" in low or "unable to find" in low or "no installed" in low):
        return "App Package를 찾을 수 없습니다. 앱이 디바이스에 설치되어 있는지 확인하세요."
    # WDA / XCUITest
    if "webdriveragent" in low or "wda" in low:
        return "WebDriverAgent(WDA) 초기화에 실패했습니다. Appium을 재시작한 후 다시 시도하세요."
    if "xcuitest" in low and ("driver" in low or "not installed" in low):
        return "XCUITest 드라이버가 설치되어 있지 않습니다. 터미널에서 'appium driver install xcuitest'를 실행하세요."
    # 번들 ID 오류
    if "bundleid" in low or "bundle id" in low or ("bundle" in low and "not found" in low):
        return "Bundle ID를 찾을 수 없습니다. 시뮬레이터에 앱이 설치되어 있는지 확인하세요."
    # 타임아웃
    if "timeout" in low or "timed out" in low:
        return "앱 실행 대기 시간이 초과되었습니다. Appium 서버와 디바이스 상태를 확인하고 다시 시도하세요."
    # UiAutomator2 드라이버 없음
    if "uiautomator2" in low and ("not installed" in low or "driver" in low):
        return "UiAutomator2 드라이버가 설치되어 있지 않습니다. 터미널에서 'appium driver install uiautomator2'를 실행하세요."
    # 기본: 첫 줄만 추출
    first_line = raw.split("\n")[0].replace("Message: ", "").strip()
    return first_line[:200] if first_line else "알 수 없는 오류가 발생했습니다."


def _do_start_android_session(session: dict) -> dict:
    """Android Emulator — UiAutomator2 + MJPEG. blocking, executor에서 실행."""
    try:
        appium_wd, RawOptions = _get_appium_import()
    except ImportError as exc:
        return {"ok": False, "error": f"appium 라이브러리 없음: {exc}"}

    opts = RawOptions()
    opts.set_capability("platformName", "Android")
    opts.set_capability("deviceName", "Android Emulator")
    opts.set_capability("automationName", "UiAutomator2")
    opts.set_capability("appPackage", session.get("app_package", ""))
    opts.set_capability("appActivity", session.get("app_activity", ""))
    opts.set_capability("noReset", True)
    opts.set_capability("forceAppLaunch", True)
    opts.set_capability("autoLaunch", True)
    opts.set_capability("newCommandTimeout", 300)
    opts.set_capability("mjpegServerPort", session.get("mjpeg_port", 8093))
    opts.set_capability("mjpegScalingFactor", 75)
    opts.set_capability("mjpegServerScreenshotQuality", 70)

    old_driver = clear_capture_driver()
    if old_driver is not None:
        try:
            old_driver.quit()
        except Exception:
            pass

    try:
        driver = appium_wd.Remote("http://localhost:4723", options=opts)
    except Exception as exc:
        return {"ok": False, "error": _friendly_appium_error(exc)}

    set_capture_driver(driver)
    _time.sleep(2)
    try:
        snap_id = _take_hierarchy_snapshot(session["session_id"], driver, "native")
    except Exception:
        snap_id = None

    return {
        "ok":                True,
        "appium_session_id": driver.session_id,
        "initial_snapshot_id": snap_id,
        "screenshot_mode":   "mjpeg",
    }


def _do_start_ios_session(session: dict) -> dict:
    """iOS Simulator — XCUITest. MJPEG 없음, screenshot polling 방식. blocking, executor에서 실행."""
    try:
        appium_wd, _ = _get_appium_import()
    except ImportError as exc:
        return {"ok": False, "error": f"appium 라이브러리 없음: {exc}"}

    try:
        from appium.options.ios.xcuitest.base import XCUITestOptions
        opts = XCUITestOptions()
    except ImportError:
        # fallback: RawOptions
        _, RawOptions = _get_appium_import()
        opts = RawOptions()

    bundle_id = session.get("bundle_id", "")
    if not bundle_id:
        return {"ok": False, "error": "iOS 세션에는 bundle_id가 필요합니다"}

    opts.set_capability("platformName", "iOS")
    opts.set_capability("automationName", "XCUITest")
    opts.set_capability("deviceName", session.get("device_name", "iPhone Simulator"))
    opts.set_capability("bundleId", bundle_id)
    opts.set_capability("noReset", True)
    opts.set_capability("forceAppLaunch", True)
    opts.set_capability("newCommandTimeout", 300)
    # WDA 첫 빌드(build-for-testing)는 60초를 초과할 수 있음 → 180초로 확장
    opts.set_capability("webDriverAgentStartupTimeout", 180000)

    old_driver = clear_capture_driver()
    if old_driver is not None:
        try:
            old_driver.quit()
        except Exception:
            pass

    try:
        driver = appium_wd.Remote("http://localhost:4723", options=opts)
    except Exception as exc:
        return {"ok": False, "error": _friendly_appium_error(exc)}

    set_capture_driver(driver)

    # WDA 안정화 대기: 기존 세션 종료 → 새 세션 초기화 전환 기간 동안
    # get_screenshot_as_base64()가 일시적으로 실패할 수 있음.
    # launch 반환 전에 스크린샷이 실제로 동작하는지 확인(최대 10초 재시도).
    _screenshot_ready = False
    for _attempt in range(10):
        _time.sleep(1)
        try:
            driver.get_screenshot_as_base64()
            _screenshot_ready = True
            break
        except Exception:
            pass
    if not _screenshot_ready:
        # 스크린샷 미준비 상태라도 세션은 유지 (hierarchy는 동작 가능)
        _time.sleep(1)

    try:
        snap_id = _take_hierarchy_snapshot(session["session_id"], driver, "native")
    except Exception:
        snap_id = None

    return {
        "ok":                True,
        "appium_session_id": driver.session_id,
        "initial_snapshot_id": snap_id,
        "screenshot_mode":   "poll",
        "screenshot_ready":  _screenshot_ready,
    }


def _do_start_appium_session(session: dict) -> dict:
    """플랫폼에 따라 Android/iOS 세션 시작 함수로 분기."""
    if session.get("platform") == "ios":
        return _do_start_ios_session(session)
    return _do_start_android_session(session)


def _do_appium_tap(device_x: int, device_y: int, session_id: str) -> bool:
    driver = get_capture_driver()
    if driver is None:
        return False
    try:
        driver.tap([(device_x, device_y)])
        return True
    except Exception:
        return False


def _do_appium_back(session_id: str) -> bool:
    driver = get_capture_driver()
    if driver is None:
        return False
    try:
        driver.back()
        return True
    except Exception:
        return False


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
        save_capture_session({
            **existing,
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

    import uuid
    new_session_id = str(uuid.uuid4())
    mjpeg_port     = body.get("mjpeg_port", 8093)

    # iOS는 MJPEG 미지원 → polling 방식
    screenshot_mode = "poll" if platform == "ios" else "mjpeg"

    session_data = {
        "session_id":        new_session_id,
        "platform":          platform,
        "target":            body.get("target", "emulator"),
        "app_package":       body.get("app_package", ""),
        "app_activity":      body.get("app_activity", ""),
        "bundle_id":         body.get("bundle_id", ""),
        "device_name":       body.get("device_name", "iPhone Simulator"),
        "tc_group":          body.get("tc_group", ""),
        "mjpeg_port":        mjpeg_port,
        "screenshot_mode":   screenshot_mode,
        "active":            True,
        "started_at":        datetime.now().isoformat(),
        "last_activity_at":  datetime.now().isoformat(),
        "actions":           [],
    }
    save_capture_session(session_data)

    session_dir = CAPTURES_DIR / new_session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "native").mkdir(exist_ok=True)
    (session_dir / "webview").mkdir(exist_ok=True)
    session_dir.joinpath("session.json").write_text(
        json.dumps(session_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    session_dir.joinpath("actions.json").write_text("[]", encoding="utf-8")

    resp: dict = {
        "ok":               True,
        "session_id":       new_session_id,
        "reconnected":      False,
        "screenshot_mode":  screenshot_mode,
        "session_dir":      str(session_dir.relative_to(PROJECT_ROOT)),
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
        "timestamp":   datetime.now().isoformat(),
    }

    session_dir  = CAPTURES_DIR / session["session_id"]
    actions_path = session_dir / "actions.json"
    actions = json.loads(actions_path.read_text(encoding="utf-8")) if actions_path.exists() else []
    actions.append(action)
    actions_path.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")

    save_capture_session({**session, "last_activity_at": datetime.now().isoformat(), "actions": actions})
    broadcast_timeline_sync({"type": "action_added", "action": action})

    loop = asyncio.get_event_loop()
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
        "timestamp":     datetime.now().isoformat(),
    }

    session_dir  = CAPTURES_DIR / session["session_id"]
    actions_path = session_dir / "actions.json"
    actions = json.loads(actions_path.read_text(encoding="utf-8")) if actions_path.exists() else []
    actions.append(action)
    actions_path.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")

    save_capture_session({**session, "last_activity_at": datetime.now().isoformat(), "actions": actions})
    broadcast_timeline_sync({"type": "action_added", "action": action})
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
    body    = await request.json()
    session = load_capture_session()

    tc_id    = str(body.get("tc_id", "tc_001")).strip()
    title    = str(body.get("title", "자동 생성 TC")).strip()
    platform = body.get("platform", session.get("platform", "android"))
    tc_group = str(body.get("tc_group", session.get("tc_group", "default"))).strip()
    actions  = body.get("actions", [])
    app_pkg   = str(session.get("app_package", body.get("app_pkg", ""))).strip()
    app_act   = str(session.get("app_activity", body.get("app_activity", ""))).strip()
    bundle_id = str(session.get("bundle_id", body.get("bundle_id", ""))).strip()

    if not tc_id or platform not in ("android", "ios"):
        return JSONResponse(
            {"ok": False, "error": "tc_id와 platform이 필요합니다"}, status_code=400
        )

    slug       = tc_id.replace("-", "_")
    class_name = "".join(w.capitalize() for w in slug.split("_") if w)
    parents    = "../" * 4  # tests/generated/{platform}/{group}/tc.py → ROOT

    lines = [
        f'"""',
        f'{slug}.py — {platform.capitalize()} | {title}',
        f'자동 생성: Capture Studio ({datetime.now().strftime("%Y-%m-%d %H:%M")})',
        f'"""',
        f"import json, subprocess, shutil, os",
        f"import time as _time",
        f"from pathlib import Path",
        f"from appium import webdriver",
        (
            f"from appium.options.android.uiautomator2.base import UiAutomator2Options"
            if platform == "android"
            else f"from appium.options.ios.xcuitest.base import XCUITestOptions"
        ),
        f"from appium.webdriver.common.appiumby import AppiumBy",
        f"",
        f'CONFIG_DIR = (Path(__file__).resolve().parent / "{parents.rstrip("/")}" / "config").resolve()',
        f'APPIUM_URL  = "http://localhost:4723"',
        f'PLATFORM_MODE = "{"emulator" if platform == "android" else "simulator"}"',
        f"",
        f"def _load_json(p): return json.loads(Path(p).read_text(encoding='utf-8'))",
        f"",
        f"def _build_driver():",
        f"    devs = _load_json(CONFIG_DIR / 'devices.json')",
        f"    caps = devs['{platform}'][PLATFORM_MODE].copy()",
        f"    caps['platformName'] = '{'Android' if platform == 'android' else 'iOS'}'",
        f"    caps.pop('app', None)  # 설치된 앱 사용",
    ]
    if platform == "android":
        lines += [
            (
                f"    caps['appPackage'] = {app_pkg!r}"
                if app_pkg
                else f"    caps['appPackage'] = _load_json(CONFIG_DIR / 'test_data.json')['app']['android']['package']"
            ),
            (
                f"    caps['appActivity'] = {app_act!r}"
                if app_act
                else f"    caps['appActivity'] = _load_json(CONFIG_DIR / 'test_data.json')['app']['android']['activity']"
            ),
            f"    opts = UiAutomator2Options().load_capabilities(caps)",
        ]
    else:
        lines += [
            (
                f"    caps['bundleId'] = {bundle_id!r}"
                if bundle_id
                else f"    caps['bundleId'] = _load_json(CONFIG_DIR / 'test_data.json')['app']['ios']['bundle_id']"
            ),
            f"    opts = XCUITestOptions().load_capabilities(caps)",
        ]
    lines += [
        f"    return webdriver.Remote(APPIUM_URL, options=opts)",
        f"",
        f"",
        f"class Test{class_name}:",
        f'    """Capture Studio — {title}"""',
        f"",
        f"    def setup_method(self):",
        f"        self.driver = _build_driver()",
        f"",
        f"    def teardown_method(self):",
        f"        if hasattr(self, 'driver') and self.driver:",
        f"            self.driver.quit()",
        f"",
        f"    def _el(self, strategy, value):",
        f"        by_map = {{",
        f"            'id': AppiumBy.ID, 'xpath': AppiumBy.XPATH,",
        f"            'accessibility id': AppiumBy.ACCESSIBILITY_ID,",
        f"            'class name': AppiumBy.CLASS_NAME,",
        f"            'AppiumBy.ID': AppiumBy.ID, 'AppiumBy.XPATH': AppiumBy.XPATH,",
        f"            'AppiumBy.ACCESSIBILITY_ID': AppiumBy.ACCESSIBILITY_ID,",
        f"            'AppiumBy.CLASS_NAME': AppiumBy.CLASS_NAME,",
        f"        }}",
        f"        return self.driver.find_element(by_map.get(strategy, AppiumBy.XPATH), value)",
        f"",
        *(
            [
                f"    def _ios_tap(self, label):",
                f"        \"\"\"iOS: 화면 밖 요소는 mobile:scroll로 자동 스크롤 후 탭.\"\"\"",
                f"        from selenium.common.exceptions import NoSuchElementException",
                f"        try:",
                f"            self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, label).click()",
                f"        except NoSuchElementException:",
                f"            self.driver.execute_script('mobile: scroll',",
                f"                {{'direction': 'down', 'predicateString': f'label == \"{{label}}\"'}})",
                f"            _time.sleep(0.5)",
                f"            self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, label).click()",
                f"",
            ]
            if platform == "ios"
            else []
        ),
        f"    def test_{slug}(self):",
        f'        """단계별 동작 및 검증"""',
    ]

    by_map_str = {
        "id":               "AppiumBy.ID",
        "xpath":            "AppiumBy.XPATH",
        "accessibility id": "AppiumBy.ACCESSIBILITY_ID",
        "accessibility-id": "AppiumBy.ACCESSIBILITY_ID",
        "class name":       "AppiumBy.CLASS_NAME",
        "class":            "AppiumBy.CLASS_NAME",
        "resource-id":      "AppiumBy.ID",
    }

    def _by(strategy: str) -> str:
        return by_map_str.get(strategy.lower().strip(), "AppiumBy.XPATH")

    for i, act in enumerate(actions, 1):
        atype    = act.get("type") or act.get("action", "")
        label    = act.get("label", f"el_{i}")
        strategy = act.get("locator_strategy", act.get("strategy", "xpath"))
        value    = act.get("locator_value", act.get("value", ""))
        if strategy.lower().strip() == "text" and value and not value.startswith("/"):
            strategy = "xpath"
            value    = f"//*[@text='{value}']"
        lines.append(f"        # Step {i}: {label}")

        if atype in ("tap", "click"):
            # iOS + accessibility-id → _ios_tap() (화면 밖 자동 스크롤 지원)
            if platform == "ios" and strategy.lower().strip() in ("accessibility-id", "accessibility id"):
                lines.append(f"        self._ios_tap({value!r})")
            else:
                lines.append(f"        self._el({_by(strategy)!r}, {value!r}).click()")
            lines.append(f"        _time.sleep(1.5)  # 화면 전환 대기")

        elif atype == "input":
            input_val = act.get("input_value", act.get("assertion_value", ""))
            lines.append(f"        el = self._el({_by(strategy)!r}, {value!r})")
            lines.append(f"        el.clear()")
            lines.append(f"        el.send_keys({input_val!r})")

        elif atype == "assertion":
            a_type = act.get("assertion_type", "element_present")
            a_val  = act.get("assertion_value", "")
            if a_type == "text_visible":
                if value:
                    lines.append(f"        el = self._el({_by(strategy)!r}, {value!r})")
                    lines.append(f'        assert {a_val!r} in el.text, f"텍스트 {{el.text!r}}에 {a_val!r} 없음"')
                else:
                    # page_source는 raw XML → & 는 &amp; 로 인코딩됨
                    # 5초 재시도 루프 + XPath fallback으로 타이밍 문제·화면 전환 지연 처리
                    import html as _html_mod
                    escaped_val = _html_mod.escape(a_val, quote=False)
                    lines.append(f"        _found_text = False")
                    lines.append(f"        for _retry_i in range(5):")
                    lines.append(f"            _src = self.driver.page_source")
                    if escaped_val != a_val:
                        lines.append(f"            if {a_val!r} in _src or {escaped_val!r} in _src:")
                    else:
                        lines.append(f"            if {a_val!r} in _src:")
                    lines.append(f"                _found_text = True; break")
                    lines.append(f"            _time.sleep(1.0)")
                    # XPath fallback: XPath는 XML 인코딩을 올바르게 처리하므로 &amp; 문제 없음
                    lines.append(f"        if not _found_text:")
                    lines.append(f"            from selenium.common.exceptions import NoSuchElementException")
                    lines.append(f"            try:")
                    lines.append(f"                _fb_el = self.driver.find_element(")
                    lines.append(f"                    AppiumBy.XPATH, \"//*[@text={repr(a_val)}]\")")
                    lines.append(f"                _found_text = _fb_el is not None")
                    lines.append(f"            except NoSuchElementException:")
                    lines.append(f"                pass")
                    lines.append(f"        assert _found_text, f\"페이지 소스·XPath에서 {a_val!r} 없음\"")
            elif a_type == "element_present":
                lines.append(f"        assert self._el({_by(strategy)!r}, {value!r}).is_displayed()")
            elif a_type == "element_absent":
                lines.append(f"        from selenium.common.exceptions import NoSuchElementException")
                lines.append(f"        try:")
                lines.append(f"            self._el({_by(strategy)!r}, {value!r})")
                lines.append(f"            assert False, '요소가 존재해서 안 됩니다: {value}'")
                lines.append(f"        except NoSuchElementException:")
                lines.append(f"            pass")

        elif atype in ("back", "scroll_down", "scroll_up"):
            if atype == "back":
                lines.append(f"        self.driver.back()")
                lines.append(f"        _time.sleep(1.0)  # 화면 복귀 대기")
            elif atype == "scroll_down":
                # driver.swipe()는 Android·iOS 양쪽에서 동작
                # (mobile: scrollGesture는 elementId 없이 호출 시 InvalidArgumentException 발생)
                lines.append(f"        _sz = self.driver.get_window_size()")
                lines.append(f"        self.driver.swipe(_sz['width']//2, int(_sz['height']*0.7),")
                lines.append(f"                          _sz['width']//2, int(_sz['height']*0.3), 400)")
                lines.append(f"        _time.sleep(0.8)  # 스크롤 완료 대기")
            else:
                lines.append(f"        _sz = self.driver.get_window_size()")
                lines.append(f"        self.driver.swipe(_sz['width']//2, int(_sz['height']*0.3),")
                lines.append(f"                          _sz['width']//2, int(_sz['height']*0.7), 400)")
                lines.append(f"        _time.sleep(0.8)  # 스크롤 완료 대기")

        elif atype == "wait":
            secs = float(act.get("wait_seconds", 1))
            lines.append(f"        import time; time.sleep({secs})")

        else:
            lines.append(f"        pass  # TODO: {atype}")

    lines.append("")
    code = "\n".join(lines)

    out_dir  = PROJECT_ROOT / "tests" / "generated" / platform / tc_group
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.py"
    out_path.write_text(code, encoding="utf-8")

    return JSONResponse({
        "ok":    True,
        "file":  str(out_path.relative_to(PROJECT_ROOT)),
        "code":  code,
        "lines": len(lines),
    })


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
    return JSONResponse({"ok": True, "message": "Capture 세션 종료됨"})


@router.get("/capture/page_source_hash")
async def capture_page_source_hash():
    """page_source 앞부분 MD5 해시 반환 — 화면 전환 감지용 경량 엔드포인트."""
    import hashlib
    driver = get_capture_driver()
    if driver is None:
        return JSONResponse({"ok": False, "hash": None})
    loop = asyncio.get_event_loop()
    try:
        src = await loop.run_in_executor(None, lambda: driver.page_source)
        h = hashlib.md5(src[:8192].encode("utf-8", errors="ignore")).hexdigest()[:8]
        return JSONResponse({"ok": True, "hash": h})
    except Exception as exc:
        return JSONResponse({"ok": False, "hash": None, "error": str(exc)})


@router.get("/capture/screenshot")
async def capture_screenshot():
    """현재 화면 스크린샷을 base64로 반환 (iOS polling 방식 미러링용).

    Android MJPEG 사용 불가 시 fallback으로도 동작합니다.
    """
    driver = get_capture_driver()
    if driver is None:
        return JSONResponse({"ok": False, "error": "Appium 세션 없음"}, status_code=409)
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, driver.get_screenshot_as_base64)
        return JSONResponse({
            "ok":   True,
            "data": data,
            "ts":   datetime.now().isoformat(),
        })
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.get("/capture/driver_alive")
async def capture_driver_alive():
    """_capture_driver 인스턴스가 살아있는지 확인.

    get_window_size()는 표준 WebDriver 명령으로 Android·iOS 양쪽에서 동작합니다.
    current_context / current_package 는 플랫폼별 차이가 있어 사용하지 않습니다.
    """
    driver = get_capture_driver()
    alive  = driver is not None
    if alive:
        try:
            _ = driver.get_window_size()  # 표준 WebDriver — Android·iOS 공통
        except Exception:
            set_capture_driver(None)
            alive = False
    return JSONResponse({"alive": alive})


@router.get("/capture/session")
async def capture_get_session():
    """현재 Capture 세션 상태 반환."""
    session = load_capture_session()
    active  = is_capture_active()
    return JSONResponse({
        "ok":      True,
        "active":  active,
        "session": session if active else {},
    })


@router.post("/capture/launch")
async def capture_launch(request: Request):
    """Appium 세션 시작 및 앱 실행 (blocking ~10–30s)."""
    body       = await request.json()
    session_id = body.get("session_id", "")
    session    = load_capture_session()
    if not is_capture_active() or session.get("session_id") != session_id:
        return JSONResponse({"ok": False, "error": "Capture 세션 없음 또는 불일치"}, status_code=400)

    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _do_start_appium_session, session)
    return JSONResponse(result, status_code=200 if result["ok"] else 500)


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
        return JSONResponse({"ok": False, "error": "Appium 세션 없음"}, status_code=409)

    # hierarchy 조회도 활동으로 간주 → last_activity_at 갱신 (30분 만료 방지)
    save_capture_session({**session, "last_activity_at": datetime.now().isoformat()})

    loop = asyncio.get_event_loop()
    try:
        snap_id = await loop.run_in_executor(
            None, _take_hierarchy_snapshot, session_id, driver, context
        )
        return JSONResponse({"ok": True, "snapshot_id": snap_id, "context": context})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


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
        "timestamp":  datetime.now().isoformat(),
        "target_ref": None,
    }
    session.setdefault("actions", []).append(action)
    session["last_activity_at"] = datetime.now().isoformat()
    save_capture_session(session)

    broadcast_timeline_sync({**action, "type": "action"})

    loop = asyncio.get_event_loop()
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
    action_type = "scroll_down" if direction != "up" else "scroll_up"

    action = {
        "index":      len(session.get("actions", [])) + 1,
        "action":     action_type,
        "context":    body.get("context", "native"),
        "timestamp":  datetime.now().isoformat(),
        "target_ref": None,
    }
    session.setdefault("actions", []).append(action)
    session["last_activity_at"] = datetime.now().isoformat()
    save_capture_session(session)
    broadcast_timeline_sync({**action, "type": "action"})

    def _do_scroll() -> bool:
        driver = get_capture_driver()
        if driver is None:
            return False
        try:
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

    loop = asyncio.get_event_loop()
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
        "timestamp":  datetime.now().isoformat(),
        "target_ref": None,
    }
    session.setdefault("actions", []).append(action)
    session["last_activity_at"] = datetime.now().isoformat()
    save_capture_session(session)

    broadcast_timeline_sync({**action, "type": "action"})
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
        tree = ET.parse(xml_files[0])
        root = tree.getroot()
    except Exception as exc:
        return JSONResponse({"ok": False, "error": f"XML 파싱 오류: {exc}"}, status_code=500)

    # 플랫폼별 XML 속성 매핑
    # Android: content-desc (accessibility), resource-id, text
    # iOS: name (accessibilityIdentifier), label (visible text), value
    platform = session.get("platform", "android")
    if platform == "ios":
        attr_map = {
            "accessibility-id": "name",    # iOS accessibilityIdentifier → XML name
            "accessibility id": "name",
            "name":             "name",
            "label":            "label",   # iOS visible label
            "value":            "value",
            "text":             "label",   # iOS에서 text는 label로 매핑
        }
    else:
        attr_map = {
            "resource-id":      "resource-id",
            "accessibility-id": "content-desc",
            "accessibility id": "content-desc",
            "text":             "text",
        }

    count: int = 0
    matched_bounds: list[str] = []

    def _elem_bounds(elem: ET.Element) -> str:
        """Android bounds 문자열 또는 iOS x/y/width/height → bounds 문자열."""
        b = elem.get("bounds", "")
        if b:
            return b
        # iOS: x, y, width, height → "[x1,y1][x2,y2]" 형식 생성
        x = elem.get("x"); y = elem.get("y")
        w = elem.get("width"); h = elem.get("height")
        if x is not None and y is not None and w is not None and h is not None:
            try:
                x2 = int(float(x)) + int(float(w))
                y2 = int(float(y)) + int(float(h))
                return f"[{int(float(x))},{int(float(y))}][{x2},{y2}]"
            except (ValueError, TypeError):
                pass
        return ""

    if strategy in attr_map:
        xml_attr = attr_map[strategy]
        for elem in root.iter():
            if elem.get(xml_attr) == value:
                count += 1
                b = _elem_bounds(elem)
                if b:
                    matched_bounds.append(b)
    elif strategy == "xpath":
        try:
            matches        = root.findall(value)
            count          = len(matches)
            matched_bounds = [_elem_bounds(m) for m in matches if _elem_bounds(m)]
        except Exception as exc:
            return JSONResponse({"ok": False, "error": f"XPath 오류: {exc}"}, status_code=400)
    else:
        return JSONResponse(
            {"ok": False, "error": f"지원하지 않는 strategy: {strategy}"}, status_code=400
        )

    unique     = count == 1
    confidence = "high" if unique else ("medium" if count <= 3 else "low")
    return JSONResponse({
        "ok":             True,
        "strategy":       strategy,
        "value":          value,
        "match_count":    count,
        "unique":         unique,
        "confidence":     confidence,
        "matched_bounds": matched_bounds[:5],
    })
