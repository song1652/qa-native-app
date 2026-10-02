"""Capture driver adapter contracts that do not require a device."""

import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from agents.dashboard.utils import capture_driver as driver_adapter
from agents.dashboard.utils.capture_driver import friendly_appium_error


def test_friendly_appium_error_maps_common_operator_failures():
    assert friendly_appium_error(ConnectionError("ECONNREFUSED")) == (
        "Appium 서버에 연결할 수 없습니다. 터미널에서 "
        "'appium --address 127.0.0.1 --port 4723'을 먼저 실행하세요."
    )
    assert "디바이스" in friendly_appium_error(RuntimeError("no device found"))
    assert "XCUITest" in friendly_appium_error(RuntimeError("xcuitest driver not installed"))


def test_friendly_appium_error_limits_unknown_message_to_first_line():
    message = "Message: " + "x" * 240 + "\nstack trace"

    assert friendly_appium_error(RuntimeError(message)) == "x" * 200


@pytest.mark.parametrize(('target', 'udid', 'connected'), [
    ('emulator', '', 'USB-PHONE'),
    ('device', '', 'emulator-5554'),
    ('emulator', 'USB-PHONE', 'USB-PHONE'),
    ('device', 'emulator-5554', 'emulator-5554'),
    ('emulator', 'emulator-5554', 'emulator-5556'),
])
def test_android_capture_never_launches_without_exact_connected_target(monkeypatch, target, udid, connected):
    remote = Mock(side_effect=RuntimeError('must not create Appium session'))
    options = type('Options', (), {'set_capability': lambda *args: None})
    monkeypatch.setattr(driver_adapter, '_get_appium_import', lambda: (SimpleNamespace(Remote=remote), options))
    monkeypatch.setattr(driver_adapter, 'get_default_device', lambda *args: {})
    monkeypatch.setattr(driver_adapter._subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=f'List of devices attached\n{connected}\tdevice\n', returncode=0))
    clear = Mock()
    monkeypatch.setattr(driver_adapter, 'clear_capture_driver', clear)
    result = driver_adapter._do_start_android_session({'session_id': 'test', 'target': target, 'udid': udid})
    assert result['ok'] is False
    assert result['code'] in ('capture_device_unavailable', 'capture_target_mismatch')
    remote.assert_not_called()
    clear.assert_not_called()


def test_ios_capture_does_not_boot_stopped_simulator_or_pick_real_device(monkeypatch):
    remote = Mock(side_effect=RuntimeError('must not create Appium session'))
    monkeypatch.setattr(driver_adapter, '_get_appium_import', lambda: (SimpleNamespace(Remote=remote), None))
    monkeypatch.setattr(driver_adapter, 'get_default_device', lambda *args: {'udid': 'SIM-1', 'deviceName': 'iPhone'})
    payload = {'devices': {'runtime': [{'udid': 'SIM-1', 'name': 'iPhone', 'state': 'Shutdown', 'isAvailable': True}]}}
    monkeypatch.setattr(driver_adapter._subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(payload), returncode=0))
    clear = Mock()
    monkeypatch.setattr(driver_adapter, 'clear_capture_driver', clear)
    result = driver_adapter._do_start_ios_session({'session_id': 'test', 'target': 'emulator', 'bundle_id': 'com.example.app'})
    assert result['ok'] is False
    assert result['code'] == 'capture_device_unavailable'
    remote.assert_not_called()
    clear.assert_not_called()


def test_ios_capture_uses_supported_wda_launch_timeout(monkeypatch):
    remote = Mock(return_value=SimpleNamespace(
        session_id='ios-mocked', get_screenshot_as_base64=lambda: 'image',
    ))
    monkeypatch.setattr(driver_adapter, 'resolve_capture_device', lambda _: {
        'ok': True, 'udid': 'SELECTED-SIM', 'device_name': 'Selected iPhone',
    })
    monkeypatch.setattr(driver_adapter, '_get_appium_import', lambda: (SimpleNamespace(Remote=remote), None))
    monkeypatch.setattr(driver_adapter, 'clear_capture_driver', lambda: None)
    monkeypatch.setattr(driver_adapter, 'set_capture_driver', lambda _: None)
    monkeypatch.setattr(driver_adapter._time, 'sleep', lambda _: None)
    monkeypatch.setattr(driver_adapter, '_take_hierarchy_snapshot', lambda *_: 'snapshot')
    result = driver_adapter._do_start_ios_session({
        'session_id': 'mocked', 'target': 'emulator', 'bundle_id': 'com.apple.Preferences',
    })
    assert result['ok']
    caps = remote.call_args.kwargs['options'].to_capabilities()
    assert caps['appium:wdaLaunchTimeout'] == 180000
    assert 'appium:webDriverAgentStartupTimeout' not in caps
    assert caps['appium:udid'] == 'SELECTED-SIM'


def test_android_capture_launch_and_forward_use_selected_emulator(monkeypatch):
    class Options:
        def __init__(self):
            self.capabilities = {}
        def set_capability(self, key, value):
            self.capabilities[key] = value
    remote = Mock(return_value=SimpleNamespace(session_id='appium-1'))
    run = Mock(return_value=SimpleNamespace(stdout='List of devices attached\nemulator-5554\tdevice\nPHONE\tdevice\nemulator-5556\tdevice\n', returncode=0))
    monkeypatch.setattr(driver_adapter, '_get_appium_import', lambda: (SimpleNamespace(Remote=remote), Options))
    monkeypatch.setattr(driver_adapter, 'get_default_device', lambda *_: {})
    monkeypatch.setattr(driver_adapter._subprocess, 'run', run)
    monkeypatch.setattr(driver_adapter, 'clear_capture_driver', lambda: None)
    monkeypatch.setattr(driver_adapter, 'set_capture_driver', lambda _: None)
    monkeypatch.setattr(driver_adapter._time, 'sleep', lambda _: None)
    monkeypatch.setattr(driver_adapter, '_take_hierarchy_snapshot', lambda *_: 'snapshot')
    result = driver_adapter._do_start_android_session({'session_id': 'test', 'target': 'emulator', 'udid': 'emulator-5556'})
    assert result['ok'] and result['udid'] == 'emulator-5556'
    assert remote.call_args.kwargs['options'].capabilities['udid'] == 'emulator-5556'
    assert run.call_args.args[0] == ['adb', '-s', 'emulator-5556', 'forward', 'tcp:8093', 'tcp:7810']


@pytest.mark.parametrize('state,reality,expected', [('connected', 'physical', True), ('disconnected', 'physical', False), ('connected', 'simulated', False)])
def test_ios_real_capture_requires_connected_hardware_udid(monkeypatch, state, reality, expected):
    inventory = {'result': {'devices': [{'identifier': 'CORE-ID', 'properties': {'hardware': {'udid': 'PHONE-UDID', 'reality': reality}, 'connection': {'state': state}, 'state': {'name': 'Phone'}}}]}}
    def run(command, **kwargs):
        return SimpleNamespace(stdout=json.dumps({'devices': {}} if 'simctl' in command else inventory), returncode=0)
    monkeypatch.setattr(driver_adapter._subprocess, 'run', run)
    monkeypatch.setattr(driver_adapter, 'get_default_device', lambda *_: {})
    result = driver_adapter.resolve_capture_device({'platform': 'ios', 'target': 'device', 'udid': 'PHONE-UDID'})
    assert result['ok'] is expected
    if expected:
        assert result['udid'] == 'PHONE-UDID'
    assert not driver_adapter.resolve_capture_device({'platform': 'ios', 'target': 'device', 'udid': 'CORE-ID'})['ok']


def test_ios_simulator_explicit_udid_wins_over_device_name(monkeypatch):
    devices = {'devices': {'runtime': [{'udid': 'SIM-1', 'name': 'First', 'state': 'Shutdown'}, {'udid': 'SIM-2', 'name': 'Second', 'state': 'Booted'}]}}
    monkeypatch.setattr(driver_adapter._subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=json.dumps(devices), returncode=0))
    monkeypatch.setattr(driver_adapter, 'get_default_device', lambda *_: {'udid': 'SIM-1'})
    result = driver_adapter.resolve_capture_device({'platform': 'ios', 'target': 'emulator', 'udid': 'SIM-2', 'device_name': 'First'})
    assert result['ok'] and result['udid'] == 'SIM-2'


def test_stale_driver_cannot_receive_capture_commands(monkeypatch):
    driver = SimpleNamespace(capabilities={'udid': 'PHONE'}, tap=Mock())
    monkeypatch.setattr(driver_adapter, '_get_capture_driver', lambda: driver)
    monkeypatch.setattr(driver_adapter, 'load_capture_session', lambda: {'platform': 'android', 'target': 'emulator', 'udid': 'PHONE'})
    assert not driver_adapter._do_appium_tap(1, 2, 'test')
    driver.tap.assert_not_called()
