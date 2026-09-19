"""Appium driver adapter used by Capture Studio routes."""

from __future__ import annotations

import subprocess as _subprocess
import sys
import time as _time
from datetime import datetime
from pathlib import Path

try:
    from shared import (
        CAPTURES_DIR,
        PROJECT_ROOT,
        clear_capture_driver,
        get_capture_driver,
        set_capture_driver,
    )
    from utils.system import get_default_device
except ModuleNotFoundError:
    from agents.dashboard.shared import (
        CAPTURES_DIR,
        PROJECT_ROOT,
        clear_capture_driver,
        get_capture_driver,
        set_capture_driver,
    )
    from agents.dashboard.utils.system import get_default_device


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


def _do_start_android_session(session: dict) -> dict:
    """Android Emulator — UiAutomator2 + MJPEG. blocking, executor에서 실행."""
    try:
        appium_wd, RawOptions = _get_appium_import()
    except ImportError as exc:
        return {"ok": False, "error": f"appium 라이브러리 없음: {exc}"}

    _target = session.get("target", "emulator")
    # 프론트엔드 "device" → devices.json 키 "real_device" 정규화
    _dev_key = "emulator" if _target == "emulator" else "real_device"
    _dev = get_default_device("android", _dev_key) or {}

    # target에 따라 ADB serial 결정
    _udid = session.get("udid") or _dev.get("udid") or ""
    if not _udid:
        # adb devices에서 자동 탐지
        _adb_out = _subprocess.run(["adb", "devices"], capture_output=True, text=True).stdout
        _serials = [
            line.split()[0] for line in _adb_out.splitlines()
            if line.endswith("\tdevice")
        ]
        if _target == "emulator":
            _udid = next((s for s in _serials if s.startswith("emulator-")), "")
        else:
            _udid = next((s for s in _serials if not s.startswith("emulator-")), "")

    opts = RawOptions()
    opts.set_capability("platformName", "Android")
    opts.set_capability("deviceName", _dev.get("deviceName", "Android Emulator"))
    opts.set_capability("automationName", "UiAutomator2")
    if _udid:
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

    # UiAutomator2 MJPEG 포트 포워딩 — Android 8093, iOS 9100으로 분리되어 충돌 없음
    _actual_mjpeg_port = session.get("mjpeg_port", _mjpeg_port)
    _fwd_cmd = ["adb"]
    if _udid:
        _fwd_cmd += ["-s", _udid]
    _fwd_cmd += ["forward", f"tcp:{_actual_mjpeg_port}", "tcp:7810"]
    _subprocess.run(_fwd_cmd, capture_output=True)

    _time.sleep(2)
    try:
        snap_id = _take_hierarchy_snapshot(session["session_id"], driver, "native")
    except Exception:
        snap_id = None

    _display_name = _dev.get("deviceName") or (_udid if _udid else "Android Emulator")
    return {
        "ok":                True,
        "appium_session_id": driver.session_id,
        "initial_snapshot_id": snap_id,
        "screenshot_mode":   "mjpeg",
        "mjpeg_port":        _actual_mjpeg_port,
        "mjpeg_url":         f"http://localhost:{_actual_mjpeg_port}",
        "device_name":       _display_name,
    }


_IOS_MJPEG_PORT = 9100  # WDA 내장 MJPEG 서버 포트 (Android 8093과 분리)


def _do_start_ios_session(session: dict) -> dict:
    """iOS Simulator — XCUITest + WDA MJPEG 스트리밍. blocking, executor에서 실행."""
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

    _ios_target = session.get("target", "emulator")
    _ios_dev_key = "simulator" if _ios_target == "emulator" else "real_device"
    _ios_dev = get_default_device("ios", _ios_dev_key) or {}

    # udid 결정: session > devices.json > devicectl 자동 탐지
    _ios_udid = session.get("udid") or _ios_dev.get("udid") or ""
    _ios_device_name = session.get("device_name") or _ios_dev.get("deviceName") or "iPhone Simulator"

    if not _ios_udid and _ios_target != "emulator":
        # 실기기: devicectl로 연결된 실기기 UDID 탐지
        _dc_out = _subprocess.run(
            ["xcrun", "devicectl", "list", "devices", "--quiet"],
            capture_output=True, text=True
        ).stdout
        for _line in _dc_out.splitlines():
            if "simulated" not in _line.lower() and len(_line.split()) >= 3:
                _parts = _line.split()
                for _p in _parts:
                    if len(_p) == 36 and _p.count("-") == 4:
                        _ios_udid = _p.rstrip("(UDID)")
                        break
                if _ios_udid:
                    break

    opts.set_capability("platformName", "iOS")
    opts.set_capability("automationName", "XCUITest")
    opts.set_capability("deviceName", _ios_device_name)
    if _ios_udid:
        opts.set_capability("udid", _ios_udid)
    opts.set_capability("bundleId", bundle_id)
    opts.set_capability("noReset", True)
    opts.set_capability("forceAppLaunch", True)
    opts.set_capability("newCommandTimeout", 300)
    # WDA 첫 빌드(build-for-testing)는 60초를 초과할 수 있음 → 180초로 확장
    opts.set_capability("webDriverAgentStartupTimeout", 180000)
    # WDA 내장 MJPEG 서버 활성화 — 시뮬레이터에서 localhost:{port}로 직접 접근 가능
    opts.set_capability("mjpegServerPort", mjpeg_port)
    opts.set_capability("mjpegScalingFactor", 35)           # 35%로 축소 → 프레임 크기 감소
    opts.set_capability("mjpegServerScreenshotQuality", 40) # JPEG 품질
    opts.set_capability("mjpegServerFramerate", 20)         # 목표 20fps

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

    snap_id = None
    for _snap_attempt in range(3):
        try:
            snap_id = _take_hierarchy_snapshot(session["session_id"], driver, "native")
            break
        except Exception:
            if _snap_attempt < 2:
                _time.sleep(2)

    return {
        "ok":                True,
        "appium_session_id": driver.session_id,
        "initial_snapshot_id": snap_id,
        "screenshot_mode":   "mjpeg",
        "mjpeg_port":        mjpeg_port,
        "mjpeg_url":         f"http://localhost:{mjpeg_port}",
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

IOS_MJPEG_PORT = _IOS_MJPEG_PORT
resolve_ios_device_name = _resolve_ios_device_name
take_hierarchy_snapshot = _take_hierarchy_snapshot
friendly_appium_error = _friendly_appium_error
start_appium_session = _do_start_appium_session
appium_tap = _do_appium_tap
appium_back = _do_appium_back
