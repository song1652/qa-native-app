"""Capture Studio Appium launch endpoint regression tests."""

import asyncio
import json
import sys
import threading
from pathlib import Path
from unittest.mock import patch

from tests.dashboard.dashboard_source import load_dashboard_source

DASHBOARD = Path(__file__).parents[2] / "agents" / "dashboard"
HTML = load_dashboard_source()
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


def test_capture_start_unavailable_does_not_write_session_or_artifacts(tmp_path):
    failure = {'ok': False, 'code': 'capture_device_unavailable', 'error': 'Start selected emulator'}
    with (
        patch.object(capture, 'is_pipeline_active', return_value=False),
        patch.object(capture, 'is_capture_active', return_value=False),
        patch.object(capture, 'load_capture_session', return_value={}),
        patch.object(capture, 'resolve_capture_device', return_value=failure),
        patch.object(capture, 'save_capture_session') as save,
        patch.object(capture, 'CAPTURES_DIR', tmp_path),
    ):
        response = _run_async(capture.capture_start_session(_JsonRequest({'platform': 'android', 'target': 'emulator'})))
    assert response.status_code == 409
    save.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_capture_reconnect_rejects_changed_target_without_mutating_session():
    session = {'session_id': 'capture-1', 'platform': 'android', 'target': 'emulator', 'udid': 'emulator-5554'}
    with (
        patch.object(capture, 'is_pipeline_active', return_value=False),
        patch.object(capture, 'load_capture_session', return_value=session),
        patch.object(capture, 'resolve_capture_device') as resolve,
        patch.object(capture, 'save_capture_session') as save,
    ):
        response = _run_async(capture.capture_start_session(_JsonRequest({'session_id': 'capture-1', 'platform': 'android', 'target': 'device', 'udid': 'PHONE'})))
    assert response.status_code == 409
    assert json.loads(response.body)['code'] == 'capture_target_mismatch'
    resolve.assert_not_called()
    save.assert_not_called()


def test_capture_start_persists_exact_identity(tmp_path):
    resolved = {'ok': True, 'udid': 'emulator-5556', 'device_name': 'Selected AVD'}
    with (
        patch.object(capture, 'is_pipeline_active', return_value=False),
        patch.object(capture, 'is_capture_active', return_value=False),
        patch.object(capture, 'load_capture_session', return_value={}),
        patch.object(capture, 'resolve_capture_device', return_value=resolved),
        patch.object(capture, 'save_capture_session') as save,
        patch.object(capture, 'get_capture_driver', return_value=None),
        patch.object(capture, 'CAPTURES_DIR', tmp_path / 'captures'),
        patch.object(capture, 'PROJECT_ROOT', tmp_path),
    ):
        response = _run_async(capture.capture_start_session(_JsonRequest({'platform': 'android', 'target': 'emulator', 'udid': 'emulator-5556'})))
    assert response.status_code == 200
    assert save.call_args.args[0]['udid'] == 'emulator-5556'
    assert save.call_args.args[0]['device_name'] == 'Selected AVD'


def test_capture_stream_unavailable_never_spawns_device_process():
    with (
        patch.object(capture, 'load_capture_session', return_value={'active': True, 'platform': 'android', 'target': 'emulator'}),
        patch.object(capture, 'resolve_capture_device', return_value={'ok': False, 'code': 'capture_device_unavailable', 'error': 'Unavailable'}),
        patch.object(capture._subprocess, 'Popen') as spawn,
    ):
        response = _run_async(capture.capture_stream('android', _Request()))
    assert response.status_code == 409
    spawn.assert_not_called()


def test_capture_android_stream_always_binds_selected_emulator():
    from types import SimpleNamespace
    class DisconnectedRequest:
        async def is_disconnected(self):
            return True
    async def scenario():
        response = await capture.capture_stream('android', DisconnectedRequest())
        async for _ in response.body_iterator:
            pass
    process = SimpleNamespace(stdout=None, kill=lambda: None, wait=lambda **_: None)
    with (
        patch.object(capture, 'load_capture_session', return_value={'active': True, 'platform': 'android', 'target': 'emulator', 'udid': 'emulator-5556'}),
        patch.object(capture, 'resolve_capture_device', return_value={'ok': True, 'udid': 'emulator-5556', 'mode': 'emulator'}),
        patch.object(capture._subprocess, 'Popen', return_value=process) as spawn,
        patch.object(capture, 'iter_jpeg_frames', return_value=iter([])),
    ):
        _run_async(scenario())
    assert spawn.call_args_list[0].args[0][:5] == ['adb', '-s', 'emulator-5556', 'exec-out', 'screenrecord']


def test_delayed_capture_launch_cannot_rebind_superseding_session():
    from unittest.mock import Mock
    session = {'session_id': 'capture-1', 'platform': 'android', 'target': 'emulator', 'udid': 'emulator-5554', 'active': True}
    replacement = {**session, 'session_id': 'capture-2', 'target': 'device', 'udid': 'PHONE'}
    driver = Mock()
    with (
        patch.object(capture, 'is_capture_active', return_value=True),
        patch.object(capture, 'load_capture_session', side_effect=[session, replacement]),
        patch.object(capture, '_do_start_appium_session', return_value={'ok': True, 'udid': 'emulator-5554', 'device_name': 'Old AVD'}),
        patch.object(capture, 'save_capture_session') as save,
        patch.object(capture, 'clear_capture_driver', return_value=driver),
    ):
        response = _run_async(capture.capture_launch(_Request()))
    assert response.status_code == 409
    save.assert_not_called()
    driver.quit.assert_called_once()


def test_new_capture_start_does_not_overwrite_active_session():
    with (
        patch.object(capture, 'is_pipeline_active', return_value=False),
        patch.object(capture, 'is_capture_active', return_value=True),
        patch.object(capture, 'load_capture_session', return_value={'session_id': 'old', 'target': 'emulator'}),
        patch.object(capture, 'resolve_capture_device') as resolve,
        patch.object(capture, 'save_capture_session') as save,
    ):
        response = _run_async(capture.capture_start_session(_JsonRequest({'platform': 'android', 'target': 'device', 'udid': 'PHONE'})))
    assert response.status_code == 409
    assert json.loads(response.body)['code'] == 'capture_session_active'
    resolve.assert_not_called()
    save.assert_not_called()


def test_capture_admission_rechecks_execution_after_device_resolution(tmp_path):
    import shared
    with (
        patch.object(capture, 'is_pipeline_active', return_value=False),
        patch.object(capture, 'is_capture_active', return_value=False),
        patch.object(capture, 'load_capture_session', return_value={}),
        patch.object(capture, 'resolve_capture_device', return_value={'ok': True, 'udid': 'emulator-5556', 'device_name': 'Virtual'}),
        patch.object(shared, 'execution_active_locked', return_value=True),
        patch.object(capture, 'save_capture_session') as save,
        patch.object(capture, 'CAPTURES_DIR', tmp_path / 'captures'),
        patch.object(capture, 'PROJECT_ROOT', tmp_path),
        patch.object(capture, 'get_capture_driver', return_value=None),
    ):
        response = _run_async(capture.capture_start_session(_JsonRequest({'platform': 'android'})))
    assert response.status_code == 409
    save.assert_not_called()


def test_capture_reconnect_cannot_revive_session_replaced_during_resolution():
    original = {'session_id': 'old', 'platform': 'android', 'target': 'emulator', 'udid': 'emulator-5554'}
    with (
        patch.object(capture, 'is_pipeline_active', return_value=False),
        patch.object(capture, 'load_capture_session', side_effect=[original, {'session_id': 'new', 'active': True}]),
        patch.object(capture, 'resolve_capture_device', return_value={'ok': True, 'udid': 'emulator-5554', 'device_name': 'Virtual'}),
        patch.object(capture, 'save_capture_session') as save,
    ):
        response = _run_async(capture.capture_start_session(_JsonRequest({'session_id': 'old', 'platform': 'android'})))
    assert response.status_code == 409
    save.assert_not_called()


def test_pipeline_active_includes_reserved_work_between_processes():
    import shared
    with patch.dict(shared._execution_reservation, {'run': {'step': 'execute'}}), patch.dict(shared._running, {}, clear=True):
        assert dashboard_state.is_pipeline_active()
