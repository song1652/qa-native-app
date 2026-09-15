"""Appium 환경 설정 카드의 사용자 관점 브라우저 계약."""
import json
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect


DASHBOARD = Path(__file__).parents[3] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

ANDROID_DEVICE = {
    "deviceName": "Pixel 7", "platformVersion": "15",
    "avd": "Pixel_7", "default": True,
}
IOS_UDID = "E73939EF-741D-4A72-BEA7-97D31B15719A"
IOS_DEVICE = {
    "deviceName": "iPhone 18 Pro", "platformVersion": "27.0",
    "udid": IOS_UDID, "default": True,
}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def appium_live_server():
    from serve import app

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        pytest.fail("FastAPI dashboard did not start")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=3)


def _appium(status: str, **overrides) -> dict:
    value = {
        "status": status,
        "pid": None,
        "port": 4723,
        "error_msg": None,
        "started_at": None,
        "version": None,
        "drivers": {"uiautomator2": False, "xcuitest": False},
        "active_sessions": 0,
        "uptime_seconds": None,
        "mjpeg_enabled": None,
    }
    value.update(overrides)
    return value


@pytest.fixture
def appium_page(page, appium_live_server):
    # 테스트 중 3초 폴링이 수동으로 주입한 상태를 덮어쓰지 않게 한다.
    page.add_init_script("window.setInterval = function(){ return 0; };")
    page.route(
        "**/api/env/status",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "appium": _appium("stopped"),
                "android": {"status": "stopped", "real_devices": [], "emulators": [ANDROID_DEVICE]},
                "ios": {"status": "stopped", "real_devices": [], "simulators": [IOS_DEVICE]},
            }),
        ),
    )
    page.route(
        "**/api/env/appium/log*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "ok": True,
                "lines": [
                    "[Appium] Welcome to Appium v3.1.2",
                    "[Appium] Appium REST http interface listener started",
                ],
            }),
        ),
    )
    page.route(
        "**/api/check/mjpeg*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": False}),
        ),
    )
    page.goto(appium_live_server, wait_until="domcontentloaded")
    page.evaluate(
        "selectView('config', document.querySelector('[data-view=config]'))"
    )
    page.wait_for_function(
        "document.getElementById('env-appium-badge').textContent.includes('중지됨')"
    )
    return page


def _render(page, appium: dict) -> None:
    page.evaluate("appium => updateEnvAppiumCard(appium)", appium)


def test_stopped_state_has_endpoint_guidance_and_only_start_action(appium_page):
    _render(appium_page, _appium("stopped"))

    expect(appium_page.locator("#env-appium-badge")).to_have_text("중지됨")
    expect(appium_page.locator("#env-appium-endpoint")).to_have_text("localhost:4723")
    expect(appium_page.locator("#env-btn-start")).to_be_visible()
    expect(appium_page.locator("#env-btn-stop")).to_be_hidden()
    expect(appium_page.locator("#env-btn-restart")).to_be_hidden()
    expect(appium_page.locator("#env-btn-refresh")).to_be_hidden()
    expect(appium_page.locator("#env-btn-retry")).to_be_hidden()


def test_starting_state_explains_polling_and_locks_all_actions(appium_page):
    _render(
        appium_page,
        _appium("starting", pid=12845, uptime_seconds=7),
    )

    expect(appium_page.locator("#env-appium-badge")).to_have_text("시작 중")
    expect(appium_page.locator("#env-appium-progress")).to_be_visible()
    expect(appium_page.locator("#env-appium-state-note")).to_contain_text("30초")
    expect(appium_page.locator("#env-appium-state-note")).to_contain_text("3초")
    for button_id in (
        "env-btn-start",
        "env-btn-stop",
        "env-btn-restart",
        "env-btn-refresh",
        "env-btn-retry",
    ):
        expect(appium_page.locator(f"#{button_id}")).to_be_hidden()


def test_managed_state_matches_mockup_information_hierarchy(appium_page):
    _render(
        appium_page,
        _appium(
            "managed",
            pid=12845,
            version="3.1.2",
            drivers={"uiautomator2": True, "xcuitest": True},
            active_sessions=2,
            uptime_seconds=83,
            mjpeg_enabled=True,
        ),
    )

    expect(appium_page.locator("#env-appium-badge")).to_have_text("실행 중")
    expect(appium_page.locator("#txt-appium")).to_have_text("Appium 연결됨")
    expect(appium_page.locator("#env-appium-owner")).to_contain_text("managed")
    expect(appium_page.locator("#env-appium-owner")).to_contain_text("12845")
    expect(appium_page.locator("#env-appium-version")).to_have_text("Appium 3.1.2")
    expect(appium_page.locator("#env-appium-sessions")).to_have_text("2개")
    expect(appium_page.locator("#env-appium-uptime")).to_have_text("00:01:23")
    expect(appium_page.locator('[data-driver="uiautomator2"]')).to_contain_text("UiAutomator2")
    expect(appium_page.locator('[data-driver="xcuitest"]')).to_contain_text("XCUITest")
    expect(appium_page.locator("#env-appium-mjpeg-panel")).to_contain_text("MJPEG")
    expect(appium_page.locator("#env-appium-mjpeg-panel")).to_contain_text("설정됨")
    expect(appium_page.locator("#env-btn-stop")).to_be_visible()
    expect(appium_page.locator("#env-btn-restart")).to_be_visible()
    expect(appium_page.locator("#env-btn-start")).to_be_hidden()
    expect(appium_page.locator("#env-appium-log-section")).to_be_visible()
    expect(appium_page.locator("#env-appium-log-output")).to_contain_text("Welcome to Appium")
    expect(appium_page.locator("#env-appium-log-path")).to_have_text("logs/appium_server.log")


def test_external_state_explains_ownership_and_offers_stop_and_refresh(appium_page):
    _render(
        appium_page,
        _appium(
            "external",
            version="3.1.2",
            drivers={"uiautomator2": True, "xcuitest": False},
        ),
    )

    expect(appium_page.locator("#env-appium-card")).to_have_attribute("data-state", "external")
    expect(appium_page.locator("#env-appium-state-note")).to_contain_text("외부")
    expect(appium_page.locator("#env-appium-state-note")).to_contain_text("종료할 수 있습니다")
    expect(appium_page.locator("#env-btn-refresh")).to_be_visible()
    expect(appium_page.locator("#env-btn-stop")).to_be_visible()
    expect(appium_page.locator("#env-btn-stop")).to_be_enabled()
    expect(appium_page.locator("#env-btn-stop")).to_have_text("■ 중지")
    expect(appium_page.locator("#env-btn-restart")).to_be_hidden()
    expect(appium_page.locator("#env-appium-mjpeg-panel")).to_contain_text("MJPEG 플래그")
    expect(appium_page.locator("#env-appium-driver-help")).to_contain_text(
        "appium driver install xcuitest"
    )
    copy_button = appium_page.locator("#env-appium-driver-help .env-appium-copy")
    expect(copy_button).to_be_visible()
    expect(copy_button).to_have_text("명령 복사")
    copy_button.click()
    expect(copy_button).to_have_text("복사됨")


def test_error_state_shows_one_retry_action_and_log_path(appium_page):
    _render(
        appium_page,
        _appium("error", error_msg="appium: command not found"),
    )

    expect(appium_page.locator("#env-appium-card")).to_have_attribute("data-state", "error")
    expect(appium_page.locator("#env-appium-error")).to_contain_text("command not found")
    expect(appium_page.locator("#env-btn-retry")).to_be_visible()
    expect(appium_page.locator("#env-btn-start")).to_be_hidden()
    expect(appium_page.locator("#env-appium-log-section")).to_be_visible()
    expect(appium_page.locator("#env-appium-log-path")).to_have_text("logs/appium_server.log")


def test_managed_log_is_manual_refresh_and_opens_full_view(appium_page):
    calls = {"log": 0}

    def _log(route):
        calls["log"] += 1
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True, "lines": ["full Appium log"]}),
        )

    appium_page.route("**/api/env/appium/log*", _log)
    managed = _appium("managed", pid=12845, mjpeg_enabled=True)
    _render(appium_page, managed)
    appium_page.wait_for_timeout(100)
    _render(appium_page, managed)
    appium_page.wait_for_timeout(100)

    assert calls["log"] == 1
    expect(appium_page.locator("#env-appium-log-refresh")).to_be_visible()
    expect(appium_page.locator("#env-appium-log-more")).to_have_text("200줄")

    appium_page.locator("#env-appium-log-more").click()
    expect(appium_page.locator("#env-appium-log-modal")).to_be_visible()
    expect(appium_page.locator("#env-appium-log-modal-output")).to_contain_text(
        "full Appium log"
    )
    appium_page.locator("#env-appium-log-modal-close").click()
    expect(appium_page.locator("#env-appium-log-modal")).to_be_hidden()


def test_stop_guard_error_is_explained_without_hiding_the_managed_state(appium_page):
    appium_page.route(
        "**/api/env/appium/stop",
        lambda route: route.fulfill(
            status=403,
            content_type="application/json",
            body=json.dumps({"ok": False, "error": "capture_session_active"}),
        ),
    )
    _render(appium_page, _appium("managed", pid=12845))

    appium_page.locator("#env-btn-stop").click()

    expect(appium_page.locator("#env-appium-error")).to_be_visible()
    expect(appium_page.locator("#env-appium-error")).to_contain_text("Capture 세션")
    expect(appium_page.locator("#env-appium-card")).to_have_attribute("data-state", "managed")


def test_restart_does_not_start_when_stop_is_rejected(appium_page):
    calls = {"start": 0}

    appium_page.route(
        "**/api/env/appium/stop",
        lambda route: route.fulfill(
            status=409,
            content_type="application/json",
            body=json.dumps({"ok": False, "error": "pipeline_running"}),
        ),
    )

    def _start(route):
        calls["start"] += 1
        route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"ok": True, "status": "starting"}),
        )

    appium_page.route("**/api/env/appium/start", _start)
    _render(appium_page, _appium("managed", pid=12845))

    appium_page.locator("#env-btn-restart").click()
    appium_page.wait_for_timeout(1000)

    assert calls["start"] == 0
    expect(appium_page.locator("#env-appium-error")).to_contain_text("파이프라인")


def test_rapid_start_clicks_send_only_one_request(appium_page):
    calls = {"start": 0}

    def _start(route):
        calls["start"] += 1
        time.sleep(0.25)
        route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"ok": True, "status": "starting"}),
        )

    appium_page.route("**/api/env/appium/start", _start)
    _render(appium_page, _appium("stopped"))

    appium_page.evaluate(
        "document.getElementById('env-btn-start').click(); "
        "document.getElementById('env-btn-start').click();"
    )
    appium_page.wait_for_timeout(600)

    assert calls["start"] == 1


def test_external_ownership_allows_programmatic_stop_request(appium_page):
    calls = {"stop": 0}

    def _stop(route):
        calls["stop"] += 1
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True}),
        )

    appium_page.route("**/api/env/appium/stop", _stop)
    _render(appium_page, _appium("external"))

    appium_page.evaluate("envAppiumAction('stop')")
    appium_page.wait_for_timeout(150)

    assert calls["stop"] == 1


def test_android_start_failure_is_shown_inside_android_card(appium_page):
    """Android 시작 실패가 조용히 무시되지 않고 카드 안에 표시된다."""
    appium_page.route(
        "**/api/env/android/avd/start",
        lambda route: route.fulfill(
            status=400,
            content_type="application/json",
            body=json.dumps({
                "ok": False,
                "error": "invalid_avd",
                "detail": "설치된 Android AVD를 찾을 수 없습니다: Missing_AVD",
            }),
        ),
    )

    appium_page.get_by_role("button", name="Pixel 7 시작").click()

    expect(appium_page.locator("#env-android-error")).to_be_visible()
    expect(appium_page.locator("#env-android-error")).to_contain_text("Missing_AVD")


def test_ios_stop_failure_is_shown_inside_ios_card(appium_page):
    """iOS 종료 실패가 조용히 무시되지 않고 카드 안에 표시된다."""
    appium_page.route(
        "**/api/env/ios/simulator/stop",
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body=json.dumps({
                "ok": False,
                "error": "simulator_shutdown_failed",
                "detail": "Shutdown failed",
            }),
        ),
    )
    appium_page.evaluate(
        "updateIosCard({status: 'running', simulator: 'iPhone 18 Pro', "
        "udid: 'E73939EF-741D-4A72-BEA7-97D31B15719A', real_devices: [], "
        "simulators: [{deviceName:'iPhone 18 Pro',platformVersion:'27.0',"
        "udid:'E73939EF-741D-4A72-BEA7-97D31B15719A',default:true}]})"
    )

    appium_page.get_by_role("button", name="iPhone 18 Pro 종료").click()

    expect(appium_page.locator("#env-ios-error")).to_be_visible()
    expect(appium_page.locator("#env-ios-error")).to_contain_text("Shutdown failed")


def test_android_success_refreshes_card_and_rapid_clicks_send_once(appium_page):
    """Android 시작은 중복 요청 없이 성공 상태를 다시 읽어 화면에 반영한다."""
    state = {"android": "stopped", "calls": 0}

    def status(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "appium": _appium("stopped"),
                "android": {"status": state["android"], "avd": "Pixel_7", "real_devices": [], "emulators": [ANDROID_DEVICE]},
                "ios": {"status": "stopped", "real_devices": [], "simulators": [IOS_DEVICE]},
            }),
        )

    def start(route):
        state["calls"] += 1
        time.sleep(0.2)
        state["android"] = "running"
        route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"ok": True, "status": "starting"}),
        )

    appium_page.route("**/api/env/status", status)
    appium_page.route("**/api/env/android/avd/start", start)
    appium_page.evaluate(
        "document.querySelector('[aria-label=\"Pixel 7 시작\"]').click();"
        "document.querySelector('[aria-label=\"Pixel 7 시작\"]').click();"
    )

    appium_page.wait_for_function(
        "document.getElementById('env-android-badge').textContent.includes('실행 중')"
    )
    assert state["calls"] == 1


def test_ios_successful_stop_refreshes_card(appium_page):
    """iOS 종료 성공 뒤 상태 조회 결과가 카드에 반영된다."""
    state = {"ios": "running"}

    def status(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "appium": _appium("stopped"),
                "android": {"status": "stopped", "real_devices": [], "emulators": [ANDROID_DEVICE]},
                "ios": {"status": state["ios"], "simulator": "iPhone 18 Pro", "udid": IOS_UDID, "real_devices": [], "simulators": [IOS_DEVICE]},
            }),
        )

    def stop(route):
        state["ios"] = "stopped"
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True, "status": "stopped"}),
        )

    appium_page.route("**/api/env/status", status)
    appium_page.route("**/api/env/ios/simulator/stop", stop)
    appium_page.evaluate(
        "updateIosCard({status: 'running', simulator: 'iPhone 18 Pro', "
        "udid: 'E73939EF-741D-4A72-BEA7-97D31B15719A', real_devices: [], "
        "simulators: [{deviceName:'iPhone 18 Pro',platformVersion:'27.0',"
        "udid:'E73939EF-741D-4A72-BEA7-97D31B15719A',default:true}]})"
    )
    appium_page.get_by_role("button", name="iPhone 18 Pro 종료").click()

    appium_page.wait_for_function(
        "document.getElementById('env-ios-badge').textContent.includes('중지됨')"
    )


def test_device_names_are_rendered_as_text_not_executable_html(appium_page):
    """설정 파일의 기기 이름이 HTML/이벤트 코드로 실행되지 않는다."""
    malicious = '<img src=x onerror="window.__envXss=true">Phone'
    appium_page.evaluate(
        "name => updateAndroidCard({status: 'stopped', real_devices: [], "
        "emulators: [{deviceName: name, avd: name}]})",
        malicious,
    )
    appium_page.wait_for_timeout(100)

    assert appium_page.evaluate("window.__envXss === true") is False
    expect(appium_page.locator("#env-android-emulator-list")).to_contain_text("Phone")
    assert appium_page.locator("#env-android-emulator-list img").count() == 0
