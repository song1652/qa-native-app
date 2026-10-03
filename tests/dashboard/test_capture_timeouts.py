"""Capture deadlines and stale worker regression tests; all I/O is mocked."""
import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agents" / "dashboard"))
from routes import capture


def run_async(coroutine):
    result = {}
    def run():
        try:
            result["value"] = asyncio.run(coroutine)
        except BaseException as exc:
            result["error"] = exc
    worker = threading.Thread(target=run)
    worker.start()
    worker.join(5)
    assert not worker.is_alive()
    if "error" in result:
        raise result["error"]
    return result["value"]


class Request:
    async def json(self):
        return {'session_id': 'draft'}


def test_launch_timeout_keeps_lock_until_late_driver_is_disposed():
    release = threading.Event()
    driver = SimpleNamespace(quit=Mock())
    session = {'session_id': 'draft', 'platform': 'android', 'active': True, 'udid': 'emulator-1'}
    def launch(_):
        release.wait(2)
        return {'ok': True, '_driver': driver, 'udid': 'emulator-1', 'device_name': 'Original'}
    async def scenario():
        try:
            response = await capture.capture_launch(Request())
            assert response.status_code == 504
            assert json.loads(response.body)['code'] == 'capture_launch_timeout'
            assert capture._capture_launch_lock.locked()
            assert (await capture.capture_launch(Request())).status_code == 409
        finally:
            release.set()
            for _ in range(100):
                if not capture._capture_launch_lock.locked():
                    break
                await asyncio.sleep(.005)
    with (
        patch.object(capture, 'CAPTURE_LAUNCH_TIMEOUTS', {'android': .02}, create=True),
        patch.object(capture, 'is_capture_active', return_value=True),
        patch.object(capture, 'load_capture_session', return_value=session),
        patch.object(capture, '_do_start_appium_session', side_effect=launch),
        patch.object(capture, 'set_capture_driver') as publish,
        patch.object(capture, 'save_capture_session') as save,
    ):
        run_async(scenario())
    publish.assert_not_called()
    assert save.call_args.args[0]["connection_issue_at"]
    assert save.call_args.args[0]["session_id"] == "draft"
    assert "device_name" not in save.call_args.args[0]
    driver.quit.assert_called_once()
    assert not capture._capture_launch_lock.locked()


def test_liveness_wait_does_not_block_other_requests():
    release = threading.Event()
    driver = SimpleNamespace(get_window_size=lambda: release.wait(.5))
    async def scenario():
        check = asyncio.create_task(capture.capture_driver_alive())
        await asyncio.sleep(.01)
        assert not check.done(), 'Appium liveness blocked event loop'
        release.set()
        assert json.loads((await check).body)['alive']
    with patch.object(capture, 'get_capture_driver', return_value=driver), patch.object(capture, 'load_capture_session', return_value={'session_id': 'draft', 'active': True}):
        run_async(scenario())


def test_restored_draft_requires_reconnect_without_driver():
    session = {'session_id': 'draft', 'active': True, 'actions': [{'action': 'tap'}]}
    with patch.object(capture, 'load_capture_session', return_value=session), patch.object(capture, 'is_capture_active', return_value=True), patch.object(capture, 'get_capture_driver', return_value=None):
        data = json.loads(run_async(capture.capture_get_session()).body)
    assert data['reconnect_required'] is True
    assert data['session']['actions'] == session['actions']


def test_cancelled_request_does_not_release_launch_ownership_early():
    release = threading.Event()
    entered = threading.Event()
    driver = SimpleNamespace(quit=Mock())
    def launch(_):
        entered.set()
        release.wait(2)
        return {'ok': True, '_driver': driver}
    async def scenario():
        task = asyncio.create_task(capture.capture_launch(Request()))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            assert capture._capture_launch_lock.locked()
            assert capture.shared._capture_launch_active
        finally:
            release.set()
            for _ in range(100):
                if not capture._capture_launch_lock.locked():
                    break
                await asyncio.sleep(.005)
    with patch.object(capture, 'is_capture_active', return_value=True), patch.object(capture, 'load_capture_session', return_value={'session_id': 'draft', 'active': True}), patch.object(capture, '_do_start_appium_session', side_effect=launch), patch.object(capture, 'set_capture_driver') as publish:
        run_async(scenario())
    publish.assert_not_called()
    driver.quit.assert_called_once()
    assert not capture.shared._capture_launch_active


def test_failed_old_liveness_does_not_disconnect_replacement():
    old = SimpleNamespace(get_window_size=Mock(side_effect=TimeoutError('device gone')))
    replacement = SimpleNamespace()
    with patch.object(capture, 'get_capture_driver', return_value=old), patch.object(capture.shared, '_capture_driver', replacement), patch.object(capture, 'load_capture_session', return_value={'session_id': 'draft', 'active': True}):
        response = run_async(capture.capture_driver_alive())
        assert capture.shared.get_capture_driver() is replacement
    assert not json.loads(response.body)['alive']
    assert old._capture_disconnected
    assert not hasattr(replacement, '_capture_disconnected')


def test_driver_creation_transport_bounds_and_no_retries():
    from utils import capture_driver
    for platform, timeout in [('android', 90), ('ios', 390)]:
        observed = {}
        def remote(*args, **kwargs):
            config = kwargs['client_config']
            observed['creation_timeout'] = config.timeout
            observed['config'] = config
            return SimpleNamespace()
        capture_driver._remote_driver(SimpleNamespace(Remote=remote), object(), platform)
        assert observed['creation_timeout'] == timeout
        assert observed['config'].timeout == 8
        assert observed['config'].init_args_for_pool_manager == {'init_args_for_pool_manager': {'retries': 0}}


def test_disconnect_ui_preserves_draft_and_requires_explicit_reconnect(page):
    page.set_content('<div id="cs-save-status"></div><div id="cs-mirror-placeholder"></div><img id="cs-mirror-img">')
    source = Path(__file__).resolve().parents[2] / 'agents/dashboard/static/capture-studio.js'
    page.add_script_tag(content=source.read_text())
    page.evaluate('''() => {
      window.csSubStatusConn = connected => window.connected = connected;
      window.setInterval = callback => { window.poll = callback; return 1; };
      window.clearInterval = () => {};
      window.calls = [];
      window.fetch = async url => { calls.push(url); return {json:async()=>({ok:false,reconnect_required:true})}; };
      _cs.sessionId='draft'; _cs.mirrorConnected=true;
      _cs.actions=[{action:'input',value:'draft text',expected:'saved'}];
      csStartScreenWatcher(); poll();
    }''')
    page.wait_for_function('document.querySelector(".cs-mirror-error button") !== null')
    assert page.evaluate('_cs.mirrorConnected') is False
    assert page.evaluate('window.connected') is False
    assert page.evaluate('_cs.actions') == [{'action': 'input', 'value': 'draft text', 'expected': 'saved'}]
    assert page.evaluate('window.calls') == ['/capture/page_source_hash']
    assert page.locator('.cs-mirror-error button').inner_text() == '세션 재연결'


def test_capture_launch_rechecks_execution_admission_before_starting_worker():
    session = {'session_id': 'draft', 'active': True, 'platform': 'android'}
    with patch.object(capture, 'is_capture_active', return_value=True), patch.object(capture, 'load_capture_session', return_value=session), patch.object(capture.shared, 'execution_active_locked', return_value=True), patch.object(capture, '_do_start_appium_session') as launch:
        response = run_async(capture.capture_launch(Request()))
    assert response.status_code == 409
    launch.assert_not_called()
    assert not capture._capture_launch_lock.locked()
    assert not capture.shared._capture_launch_active


def test_capture_launch_rechecks_session_before_starting_worker():
    session = {'session_id': 'draft', 'active': True, 'platform': 'android'}
    with patch.object(capture, 'is_capture_active', return_value=True), patch.object(capture, 'load_capture_session', side_effect=[session, {**session, 'active': False}]), patch.object(capture, '_do_start_appium_session') as launch:
        response = run_async(capture.capture_launch(Request()))
    assert response.status_code == 409
    launch.assert_not_called()
    assert not capture._capture_launch_lock.locked()
    assert not capture.shared._capture_launch_active
