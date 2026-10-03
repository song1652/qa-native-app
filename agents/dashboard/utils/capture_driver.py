"""Appium driver adapter used by Capture Studio routes."""

from __future__ import annotations

import subprocess as _subprocess
import json
import sys
import time as _time
from datetime import datetime

try:
    from shared import (
        CAPTURES_DIR,
        PROJECT_ROOT,
        clear_capture_driver,
        get_capture_driver as _get_capture_driver,
    )
    from utils.system import get_default_device
    from utils.state import load_capture_session
except ModuleNotFoundError:
    from agents.dashboard.shared import (
        CAPTURES_DIR,
        PROJECT_ROOT,
        clear_capture_driver,
        get_capture_driver as _get_capture_driver,
    )
    from agents.dashboard.utils.system import get_default_device
    from agents.dashboard.utils.state import load_capture_session


CAPTURE_LAUNCH_TIMEOUTS = {"android": 120, "ios": 400}
CAPTURE_COMMAND_TIMEOUT = 8


def _remote_driver(appium_wd, options, platform):
    # Bound transport independently of the HTTP endpoint. Never repeat writes.
    from appium.webdriver.client_config import AppiumClientConfig
    config = AppiumClientConfig(
        remote_server_addr="http://localhost:4723",
        timeout=390 if platform == "ios" else 90,
        init_args_for_pool_manager={"init_args_for_pool_manager": {"retries": 0}},
    )
    driver = appium_wd.Remote("http://localhost:4723", options=options, client_config=config)
    config.timeout = CAPTURE_COMMAND_TIMEOUT
    return driver


def _launch_cancelled(session):
    event = session.get("_launch_cancelled")
    return ((event is not None and event.is_set())
            or _time.monotonic() >= session.get("_launch_deadline", float("inf")))


def get_capture_driver():
    """Reject a driver whose identity differs from the saved Capture target."""
    driver = _get_capture_driver()
    if driver is None or getattr(driver, "_capture_disconnected", False) is True:
        return None
    session = load_capture_session()
    udid = session.get("udid")
    capabilities = getattr(driver, "capabilities", {}) or {}
    actual = capabilities.get("appium:udid") or capabilities.get("udid")
    binding = getattr(driver, "_capture_binding", None)
    expected = (session.get("platform"), session.get("target", "emulator"), udid)
    if not udid or (actual and actual != udid) or (binding and binding != expected):
        return None
    if session.get("platform") == "android" and udid.startswith("emulator-") != (session.get("target", "emulator") == "emulator"):
        return None
    if session.get("platform") == "ios" and binding != expected:
        return None
    return driver if actual == udid or binding == expected else None


def _resolve_ios_device_name(platform: str, device_name: str) -> str:
    """iOS 세션 device_name 보정: 비어있거나 'iPhone Simulator'이면 devices.json 기본값 사용."""
    if platform != "ios":
        return device_name or ""
    if device_name and device_name.lower() not in ("iphone simulator", ""):
        return device_name
    default = get_default_device("ios", "simulator")
    if default:
        return default.get("deviceName", "iPhone Simulator")
    return "iPhone Simulator"


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
        return "Appium 서버에 연결할 수 없습니다. 터미널에서 'appium --address 127.0.0.1 --port 4723'을 먼저 실행하세요."
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


def resolve_capture_device(session: dict) -> dict:
    """Resolve a connected device of the requested kind, never an Appium default."""
    platform = session.get("platform", "android")
    target = session.get("target", "emulator")
    virtual = target in ("emulator", "simulator")
    if target not in ("emulator", "device", "real_device", "simulator") or (platform == "android" and target == "simulator"):
        return {"ok": False, "code": "invalid_capture_target", "error": "실행 대상을 에뮬레이터/시뮬레이터 또는 실기기로 선택하세요."}
    mode = ("emulator" if platform == "android" else "simulator") if virtual else "real_device"
    default = get_default_device(platform, mode) or {}
    explicit = str(session.get("udid") or "")
    udid = explicit or str(default.get("udid") or default.get("serial") or "")
    name = session.get("device_name") or default.get("deviceName") or ""
    kind = ("Android 에뮬레이터" if platform == "android" else "iOS 시뮬레이터") if virtual else ("Android 실기기" if platform == "android" else "iOS 실기기")
    unavailable = {"ok": False, "code": "capture_device_unavailable", "error": f"선택한 {kind}가 연결되어 있지 않습니다. 환경 설정에서 해당 기기를 시작하거나 연결한 뒤 다시 확인하세요. 다른 실행 대상을 사용하려면 직접 선택하세요."}
    mismatch = {"ok": False, "code": "capture_target_mismatch", "error": f"선택한 기기가 {kind} 실행 대상과 일치하지 않습니다. 실행 대상과 기기를 다시 선택하세요."}
    try:
        if platform == "android":
            if udid and udid.startswith("emulator-") != virtual:
                return mismatch
            output = _subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
            serials = [parts[0] for line in output.stdout.splitlines() if len(parts := line.split()) >= 2 and parts[1] == "device"]
            candidates = [serial for serial in serials if serial.startswith("emulator-") == virtual]
            if udid:
                if udid not in candidates:
                    return unavailable
            else:
                avd = session.get("avd") or default.get("avd")
                if virtual and avd:
                    candidates = [serial for serial in candidates if _subprocess.run(["adb", "-s", serial, "emu", "avd", "name"], capture_output=True, text=True, timeout=5).stdout.splitlines()[0:1] == [avd]]
                udid = next(iter(candidates), "")
        else:
            output = _subprocess.run(["xcrun", "simctl", "list", "devices", "available", "--json"], capture_output=True, text=True, timeout=8)
            simulators = [device for group in json.loads(output.stdout or "{}").get("devices", {}).values() for device in group if device.get("isAvailable", True)]
            if virtual:
                if not explicit and session.get("device_name") and session["device_name"] != "iPhone Simulator":
                    selected = next((device for device in simulators if device.get("name") == session["device_name"]), None)
                else:
                    selected = next((device for device in simulators if device.get("udid") == udid), None) if udid else next((device for device in simulators if device.get("state") == "Booted"), None)
                if not selected or selected.get("state") != "Booted":
                    return unavailable
                udid, name = selected["udid"], selected["name"]
            else:
                if any(device.get("udid") == udid for device in simulators):
                    return mismatch
                output = _subprocess.run(["xcrun", "devicectl", "list", "devices", "--quiet", "--json-output", "-"], capture_output=True, text=True, timeout=8)
                candidates = []
                for device in json.loads(output.stdout or "{}").get("result", {}).get("devices", []):
                    properties = device.get("properties", {})
                    hardware = properties.get("hardware") or device.get("hardwareProperties", {})
                    connection = properties.get("connection") or device.get("connectionProperties", {})
                    if hardware.get("reality") == "physical" and connection.get("state", connection.get("tunnelState")) == "connected":
                        candidates.append((hardware.get("udid"), properties.get("state", device.get("deviceProperties", {})).get("name", "")))
                selected = next((item for item in candidates if item[0] == udid), None) if udid else next(iter(candidates), None)
                if not selected:
                    return unavailable
                udid, name = selected
    except (OSError, ValueError, _subprocess.TimeoutExpired):
        return unavailable
    if not udid:
        return unavailable
    return {"ok": True, "udid": udid, "device_name": name or udid, "mode": mode, "device": default}


def _do_start_android_session(session: dict) -> dict:
    """Android Emulator — UiAutomator2 + MJPEG. blocking, executor에서 실행."""
    resolved = resolve_capture_device({**session, "platform": "android"})
    if not resolved["ok"]:
        return resolved
    try:
        appium_wd, RawOptions = _get_appium_import()
    except ImportError as exc:
        return {"ok": False, "error": f"appium 라이브러리 없음: {exc}"}

    _dev = resolved["device"]
    _udid = resolved["udid"]

    opts = RawOptions()
    opts.set_capability("platformName", "Android")
    opts.set_capability("deviceName", resolved["device_name"])
    opts.set_capability("automationName", "UiAutomator2")
    opts.set_capability("udid", _udid)
    opts.set_capability("appPackage", session.get("app_package", ""))
    opts.set_capability("appActivity", session.get("app_activity", ""))
    opts.set_capability("noReset", True)
    opts.set_capability("forceAppLaunch", True)
    opts.set_capability("autoLaunch", True)
    opts.set_capability("newCommandTimeout", 300)
    _mjpeg_port = _dev.get("mjpegServerPort", 8093)
    _mjpeg_scale = _dev.get("mjpegScalingFactor", 50)
    _mjpeg_quality = _dev.get("mjpegServerScreenshotQuality", 50)
    opts.set_capability("mjpegServerPort", session.get("mjpeg_port", _mjpeg_port))
    opts.set_capability("mjpegScalingFactor", _mjpeg_scale)
    opts.set_capability("mjpegServerScreenshotQuality", _mjpeg_quality)

    if _launch_cancelled(session):
        return {"ok": False, "code": "capture_launch_timeout"}
    old_driver = clear_capture_driver()
    if old_driver is not None:
        try:
            old_driver.quit()
        except Exception:
            pass

    if _launch_cancelled(session):
        return {"ok": False, "code": "capture_launch_timeout"}
    try:
        driver = _remote_driver(appium_wd, opts, "android")
    except Exception as exc:
        return {"ok": False, "error": _friendly_appium_error(exc)}

    driver._capture_binding = ("android", session.get("target", "emulator"), _udid)
    # The route publishes only after checking the still-current session.
    session["_launch_driver"] = driver
    if _launch_cancelled(session):
        return {"ok": False, "_driver": driver}

    # UiAutomator2 MJPEG 포트 포워딩 — Android 8093, iOS 9100으로 분리되어 충돌 없음
    _actual_mjpeg_port = session.get("mjpeg_port", _mjpeg_port)
    _fwd_cmd = ["adb"]
    if _udid:
        _fwd_cmd += ["-s", _udid]
    _fwd_cmd += ["forward", f"tcp:{_actual_mjpeg_port}", "tcp:7810"]
    _subprocess.run(_fwd_cmd, capture_output=True, timeout=5)

    _time.sleep(2)
    try:
        snap_id = _take_hierarchy_snapshot(session["session_id"], driver, "native")
    except Exception:
        snap_id = None

    _display_name = resolved["device_name"]
    return {
        "ok":                True,
        "_driver":           driver,
        "appium_session_id": driver.session_id,
        "initial_snapshot_id": snap_id,
        "screenshot_mode":   "mjpeg",
        "mjpeg_port":        _actual_mjpeg_port,
        "mjpeg_url":         f"http://localhost:{_actual_mjpeg_port}",
        "device_name":       _display_name,
        "udid":              _udid,
    }


_IOS_MJPEG_PORT = 9100  # WDA 내장 MJPEG 서버 포트 (Android 8093과 분리)


def _do_start_ios_session(session: dict) -> dict:
    """iOS Simulator — XCUITest + WDA MJPEG 스트리밍. blocking, executor에서 실행."""
    resolved = resolve_capture_device({**session, "platform": "ios"})
    if not resolved["ok"]:
        return resolved
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

    mjpeg_port = session.get("mjpeg_port", _IOS_MJPEG_PORT)

    _ios_udid = resolved["udid"]
    _ios_device_name = resolved["device_name"]

    opts.set_capability("platformName", "iOS")
    opts.set_capability("automationName", "XCUITest")
    opts.set_capability("deviceName", _ios_device_name)
    opts.set_capability("udid", _ios_udid)
    opts.set_capability("bundleId", bundle_id)
    opts.set_capability("noReset", True)
    opts.set_capability("forceAppLaunch", True)
    opts.set_capability("newCommandTimeout", 300)
    # WDA 첫 빌드(build-for-testing)는 60초를 초과할 수 있음 → 180초로 확장
    opts.set_capability("wdaLaunchTimeout", 180000)
    # WDA 내장 MJPEG 서버 활성화 — 시뮬레이터에서 localhost:{port}로 직접 접근 가능
    opts.set_capability("mjpegServerPort", mjpeg_port)
    opts.set_capability("mjpegScalingFactor", 35)           # 35%로 축소 → 프레임 크기 감소
    opts.set_capability("mjpegServerScreenshotQuality", 40) # JPEG 품질
    opts.set_capability("mjpegServerFramerate", 20)         # 목표 20fps

    if _launch_cancelled(session):
        return {"ok": False, "code": "capture_launch_timeout"}
    old_driver = clear_capture_driver()
    if old_driver is not None:
        try:
            old_driver.quit()
        except Exception:
            pass

    if _launch_cancelled(session):
        return {"ok": False, "code": "capture_launch_timeout"}
    try:
        driver = _remote_driver(appium_wd, opts, "ios")
    except Exception as exc:
        return {"ok": False, "error": _friendly_appium_error(exc)}

    driver._capture_binding = ("ios", session.get("target", "emulator"), _ios_udid)
    # The route publishes only after checking the still-current session.
    session["_launch_driver"] = driver
    if _launch_cancelled(session):
        return {"ok": False, "_driver": driver}

    # WDA 안정화 대기: 기존 세션 종료 → 새 세션 초기화 전환 기간 동안
    # get_screenshot_as_base64()가 일시적으로 실패할 수 있음.
    # launch 반환 전에 스크린샷이 실제로 동작하는지 확인(최대 10초 재시도).
    _screenshot_ready = False
    for _attempt in range(10):
        if _launch_cancelled(session):
            break
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

    snap_id = None
    for _snap_attempt in range(3):
        if _launch_cancelled(session):
            break
        try:
            snap_id = _take_hierarchy_snapshot(session["session_id"], driver, "native")
            break
        except Exception:
            if _snap_attempt < 2:
                _time.sleep(2)

    return {
        "ok":                True,
        "_driver":           driver,
        "appium_session_id": driver.session_id,
        "initial_snapshot_id": snap_id,
        "screenshot_mode":   "mjpeg",
        "mjpeg_port":        mjpeg_port,
        "mjpeg_url":         f"http://localhost:{mjpeg_port}",
        "screenshot_ready":  _screenshot_ready,
        "udid":              _ios_udid,
        "device_name":       _ios_device_name,
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

IOS_MJPEG_PORT = _IOS_MJPEG_PORT
resolve_ios_device_name = _resolve_ios_device_name
take_hierarchy_snapshot = _take_hierarchy_snapshot
friendly_appium_error = _friendly_appium_error
start_appium_session = _do_start_appium_session
appium_tap = _do_appium_tap
appium_back = _do_appium_back
