"""Capture Studio Appium launch endpoint regression tests."""

import asyncio
import json
import sys
import threading
from pathlib import Path
from unittest.mock import patch


DASHBOARD = Path(__file__).parents[2] / "agents" / "dashboard"
HTML = (DASHBOARD / "dashboard.html").read_text(encoding="utf-8")
sys.path.insert(0, str(DASHBOARD))

from routes import capture  # noqa: E402
from utils import state as dashboard_state  # noqa: E402


class _Request:
    async def json(self):
        return {"session_id": "capture-1"}


class _JsonRequest:
    def __init__(self, body):
        self.body = body

    async def json(self):
        return self.body


def _run_async(coroutine):
    """Run an async endpoint even when Playwright owns the main-thread loop."""
    outcome = {}

    def runner():
        try:
            outcome["value"] = asyncio.run(coroutine)
        except BaseException as exc:  # re-raise the original test failure
            outcome["error"] = exc

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive(), "async endpoint test timed out"
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


def test_capture_launch_rejects_concurrent_appium_session_creation():
    """A browser retry must not create another driver while WDA is starting."""
    entered = threading.Event()
    release = threading.Event()
    call_count = 0
    call_count_lock = threading.Lock()

    def slow_launch(_session):
        nonlocal call_count
        with call_count_lock:
            call_count += 1
            current_call = call_count
        if current_call == 1:
            entered.set()
            release.wait(timeout=2)
        return {"ok": True, "appium_session_id": f"appium-{current_call}"}

    async def scenario():
        first = asyncio.create_task(capture.capture_launch(_Request()))
        assert await asyncio.to_thread(entered.wait, 1)
        second = await capture.capture_launch(_Request())
        release.set()
        first_response = await first
        return first_response, second

    session = {"session_id": "capture-1", "platform": "ios"}
    with (
        patch.object(capture, "is_capture_active", return_value=True),
        patch.object(capture, "load_capture_session", return_value=session),
        patch.object(capture, "_do_start_appium_session", side_effect=slow_launch),
    ):
        first_response, second_response = _run_async(scenario())

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert b"capture_launch_in_progress" in second_response.body
    assert call_count == 1


def test_capture_end_quits_and_clears_the_appium_driver():
    """Ending Capture must release the Appium/WDA session, not only metadata."""
    driver = type("Driver", (), {"quit": lambda self: setattr(self, "quit_called", True)})()
    driver.quit_called = False
    session = {"session_id": "capture-1", "active": True}

    with (
        patch.object(capture, "load_capture_session", return_value=session),
        patch.object(capture, "save_capture_session"),
        patch.object(capture, "clear_capture_driver", return_value=driver) as clear_driver,
    ):
        response = _run_async(capture.capture_end_session(_Request()))

    assert response.status_code == 200
    clear_driver.assert_called_once_with()
    assert driver.quit_called is True


def test_capture_ui_has_a_single_launch_in_progress_guard():
    """Repeated clicks in one browser tab must be ignored while WDA starts."""
    assert "launching: false" in HTML
    assert HTML.count("if(_cs.launching)") >= 3


def _generated_code(tmp_path, platform, actions, *, include_app_id=True):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "devices.json").write_text(
        json.dumps(
            {
                "android": {"emulator": [{"udid": "emulator-5554", "default": True}]},
                "ios": {"simulator": [{"udid": "SIM-1", "default": True}]},
            }
        ),
        encoding="utf-8",
    )
    body = {
        "tc_id": f"tc_{platform}_stable",
        "title": "repeatable test",
        "platform": platform,
        "tc_group": "settings",
        "actions": actions,
    }
    if include_app_id:
        body.update(
            app_pkg="com.android.settings",
            app_activity=".Settings",
            bundle_id="com.apple.Preferences",
        )
    with (
        patch.object(capture, "PROJECT_ROOT", tmp_path),
        patch.object(capture, "load_capture_session", return_value={}),
    ):
        response = _run_async(capture.capture_generate_from_actions(_JsonRequest(body)))
    payload = json.loads(response.body)
    assert payload["ok"] is True
    compile(payload["code"], payload["file"], "exec")
    return payload["code"]


def test_generated_android_test_resets_app_and_supports_list_device_config(tmp_path):
    code = _generated_code(tmp_path, "android", [{"type": "wait", "wait_seconds": 0}])

    assert "CAPTURE_TEMPLATE_VERSION = 2" in code
    assert "def _get_device(platform, mode):" in code
    assert "_reset_to_start(self.driver)" in code
    assert "driver.current_package" in code
    assert "driver.activate_app(APP_ID)" in code
    assert "WebDriverWait" in code


def test_generated_ios_test_resets_app_on_every_setup(tmp_path):
    code = _generated_code(tmp_path, "ios", [{"type": "wait", "wait_seconds": 0}])

    assert "CAPTURE_TEMPLATE_VERSION = 2" in code
    assert "APP_ID = 'com.apple.Preferences'" in code
    assert "driver.terminate_app(APP_ID)" in code
    assert "driver.activate_app(APP_ID)" in code
    assert "_reset_to_start(self.driver)" in code


def test_generated_test_uses_config_app_id_for_reset_when_session_has_no_app_id(tmp_path):
    code = _generated_code(
        tmp_path, "android", [{"type": "wait", "wait_seconds": 0}], include_app_id=False
    )

    assert "APP_ID = _load_json(CONFIG_DIR / 'test_data.json')['app']['android']['package']" in code
    assert "APP_ACTIVITY = _load_json(CONFIG_DIR / 'test_data.json')['app']['android']['activity']" in code


def test_coordinate_tap_generation_never_emits_empty_xpath(tmp_path):
    code = _generated_code(
        tmp_path,
        "android",
        [{"type": "tap", "label": "mirror tap", "device_x": 120, "device_y": 320}],
    )

    assert "mobile: clickGesture" in code
    assert "'x': 120" in code
    assert "'y': 320" in code
    assert "AppiumBy.XPATH', ''" not in code


def test_manual_step_mode_ignores_mirror_action_events():
    assert "function csHandleTimelineEvent(evt)" in HTML
    handler_start = HTML.index("function csHandleTimelineEvent(evt)")
    handler_end = HTML.index("function csConnectWsTimeline()", handler_start)
    handler = HTML[handler_start:handler_end]

    assert "_cs.recording" in handler
    assert "if(!_cs.recording)return" in handler.replace(" ", "")
    assert "csHandleTimelineEvent(evt)" in HTML[handler_end:]


def test_codegen_payload_preserves_mirror_coordinates():
    function_start = HTML.index("function _csActionsForCodeGen()")
    function_end = HTML.index("function csAutoGenerate", function_start)
    function_body = HTML[function_start:function_end]

    assert "device_x:" in function_body
    assert "device_y:" in function_body


def test_generated_listing_marks_scalar_device_schema_as_stale(tmp_path):
    platform_dir = tmp_path / "android" / "settings"
    platform_dir.mkdir(parents=True)
    (platform_dir / "tc_old.py").write_text(
        "caps = devs['android'][PLATFORM_MODE].copy()\n", encoding="utf-8"
    )
    (platform_dir / "tc_current.py").write_text(
        "CAPTURE_TEMPLATE_VERSION = 2\n", encoding="utf-8"
    )

    with patch.object(dashboard_state, "GENERATED_DIR", tmp_path):
        listing = dashboard_state.list_generated("android")

    assert listing[0]["stale_count"] == 1
    assert listing[0]["stale_files"] == ["settings/tc_old.py"]
