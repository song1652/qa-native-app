"""Browser contracts for mockup-aligned Android/iOS virtual-device settings."""

from __future__ import annotations

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

ANDROID_AVD = {
    "deviceName": "Pixel 8",
    "platformVersion": "16",
    "avd": "Pixel_8_Android16",
    "default": True,
}
SIM_UDID = "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"
IOS_SIMULATOR = {
    "deviceName": "iPhone 16 Plus",
    "platformVersion": "26.5",
    "udid": SIM_UDID,
    "default": True,
}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def env_live_server():
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


@pytest.fixture
def env_page(page, env_live_server):
    page.add_init_script("window.setInterval = function(){ return 0; };")
    page.route(
        "**/api/env/status",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "appium": {"status": "stopped", "drivers": {}},
                "android": {
                    "status": "stopped", "avd": None, "serial": None,
                    "emulators": [ANDROID_AVD], "real_devices": [],
                },
                "ios": {
                    "status": "stopped", "simulator": None, "udid": None,
                    "simulators": [IOS_SIMULATOR], "real_devices": [],
                },
            }),
        ),
    )
    page.route(
        "**/api/env/android/list_system_avds",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True, "avds": [ANDROID_AVD]}),
        ),
    )
    page.route(
        "**/api/env/ios/list_system_simulators",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "ok": True,
                "simulators": [{**IOS_SIMULATOR, "state": "Shutdown"}],
            }),
        ),
    )
    page.goto(env_live_server, wait_until="domcontentloaded")
    page.evaluate(
        "selectView('config', document.querySelector('[data-view=config]'))"
    )
    expect(page.locator("#env-android-emulator-list")).to_contain_text("Pixel 8")
    return page


def test_android_list_has_mockup_row_actions_and_targeted_start(env_page):
    captured = {}

    def start(route):
        captured.update(route.request.post_data_json)
        route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"ok": True, "status": "starting"}),
        )

    env_page.route("**/api/env/android/avd/start", start)

    expect(env_page.get_by_text("Android 16", exact=True)).to_be_visible()
    expect(env_page.get_by_text("기본", exact=True).first).to_be_visible()
    env_page.get_by_role("button", name="Pixel 8 시작").click()
    env_page.wait_for_timeout(100)

    assert captured == {"avd": "Pixel_8_Android16"}


def test_environment_settings_has_design_heading_and_navigation_label(env_page):
    expect(env_page.get_by_role("heading", name="환경 설정", exact=True)).to_be_visible()
    expect(
        env_page.locator('[data-view="config"]', has_text="환경 설정")
    ).to_be_visible()


def test_android_add_modal_discovers_and_autofills(env_page):
    trigger = env_page.get_by_role("button", name="Android 에뮬레이터 추가")
    trigger.click()

    dialog = env_page.get_by_role("dialog", name="Android 에뮬레이터 추가")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_label("시스템에 설치된 AVD")).to_have_value(
        "Pixel_8_Android16"
    )
    expect(dialog.get_by_label("이름")).to_have_value("Pixel 8")
    expect(dialog.get_by_label("Android 버전")).to_have_value("16")
    expect(dialog.get_by_role("button", name="등록")).to_be_visible()
    expect(dialog.locator("option").first).to_have_text(
        "Pixel 8 (Android 16) · 등록됨"
    )


def test_ios_add_modal_autofills_udid_and_submits_contract(env_page):
    captured = {}

    def add(route):
        captured.update(route.request.post_data_json)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True}),
        )

    env_page.route("**/api/env/ios/add", add)
    env_page.get_by_role("button", name="iOS 시뮬레이터 추가").click()

    dialog = env_page.get_by_role("dialog", name="iOS 시뮬레이터 추가")
    expect(dialog.get_by_label("시뮬레이터 선택")).to_have_value(SIM_UDID)
    expect(dialog.get_by_label("기기명")).to_have_value("iPhone 16 Plus")
    expect(dialog.get_by_label("iOS 버전")).to_have_value("26.5")
    expect(dialog.get_by_label("UDID")).to_have_value(SIM_UDID)
    dialog.get_by_role("button", name="등록").click()
    env_page.wait_for_timeout(100)

    assert captured == {
        "mode": "simulator",
        "deviceName": "iPhone 16 Plus",
        "platformVersion": "26.5",
        "udid": SIM_UDID,
    }


def test_ios_row_boot_targets_the_selected_udid(env_page):
    captured = {}

    def start(route):
        captured.update(route.request.post_data_json)
        route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"ok": True, "status": "starting"}),
        )

    env_page.route("**/api/env/ios/simulator/start", start)
    env_page.get_by_role("button", name="iPhone 16 Plus 부팅").click()
    env_page.wait_for_timeout(100)

    assert captured == {"udid": SIM_UDID}


def test_duplicate_android_registration_stays_open_with_korean_guidance(env_page):
    env_page.route(
        "**/api/env/android/add",
        lambda route: route.fulfill(
            status=409,
            content_type="application/json",
            body=json.dumps({
                "ok": False,
                "error": "duplicate_avd",
                "detail": "avd=Pixel_8_Android16 already exists",
            }),
        ),
    )
    env_page.get_by_role("button", name="Android 에뮬레이터 추가").click()
    dialog = env_page.get_by_role("dialog", name="Android 에뮬레이터 추가")
    dialog.get_by_role("button", name="등록").click()

    expect(dialog).to_be_visible()
    expect(dialog.get_by_text("이미 등록된 Android 에뮬레이터입니다.")).to_be_visible()
    expect(dialog.get_by_role("button", name="등록")).to_be_enabled()


def test_modal_escape_closes_and_returns_focus(env_page):
    trigger = env_page.get_by_role("button", name="iOS 시뮬레이터 추가")
    trigger.click()
    dialog = env_page.get_by_role("dialog", name="iOS 시뮬레이터 추가")
    expect(dialog).to_be_visible()

    env_page.keyboard.press("Escape")

    expect(dialog).to_be_hidden()
    expect(trigger).to_be_focused()


def test_ios_add_modal_is_usable_at_320_css_pixels(env_page):
    env_page.set_viewport_size({"width": 320, "height": 800})
    env_page.get_by_role("button", name="iOS 시뮬레이터 추가").click()

    dialog = env_page.get_by_role("dialog", name="iOS 시뮬레이터 추가")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_role("button", name="등록")).to_be_visible()
    assert env_page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
