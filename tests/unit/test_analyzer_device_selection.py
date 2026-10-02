"""Driver factories must pin the requested device without substituting peers."""
import json
from types import SimpleNamespace

import pytest
from scripts.drivers import android_driver, ios_driver


@pytest.fixture
def configured(tmp_path, monkeypatch):
    for module in (android_driver, ios_driver):
        monkeypatch.setattr(module, 'CONFIG_DIR', tmp_path)
    (tmp_path / 'devices.json').write_text(json.dumps({
        'android': {'emulator': [{'deviceName': 'Default', 'avd': 'DefaultAVD', 'default': True}],
                    'real_device': [{'deviceName': 'Phone', 'udid': 'PHONE'}]},
        'ios': {'simulator': [{'deviceName': 'Default', 'udid': 'SIM-DEFAULT', 'default': True},
                             {'deviceName': 'Selected', 'udid': 'SIM-SELECTED'}],
                'real_device': [{'deviceName': 'Phone', 'udid': 'IOS-PHONE'}]},
    }))
    (tmp_path / 'test_data.json').write_text(json.dumps({'app': {
        'android': {'package': 'example.app', 'activity': '.Main', 'app_path': ''},
        'ios': {'bundle_id': 'example.app', 'app_path': ''},
    }}))
    import appium.webdriver
    monkeypatch.setattr(appium.webdriver, 'Remote', lambda url, options: options.to_capabilities())


@pytest.mark.parametrize('mode,udid,output,success', [
    ('emulator', 'emulator-5556', 'emulator-5554\tdevice\nemulator-5556\tdevice', True),
    ('emulator', 'emulator-5556', 'emulator-5554\tdevice', False),
    ('emulator', 'PHONE', 'PHONE\tdevice', False),
    ('real_device', 'PHONE', 'PHONE\tunauthorized\nemulator-5554\tdevice', False),
    ('real_device', 'PHONE', 'PHONE\tdevice', True),
])
def test_android_pins_only_ready_requested_kind(configured, monkeypatch, mode, udid, output, success):
    monkeypatch.setattr(android_driver.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout='List of devices attached\n' + output, returncode=0))
    if success:
        caps = android_driver.create_driver(mode=mode, udid=udid)
        assert caps['appium:udid'] == udid
        assert 'appium:avd' not in caps
    else:
        with pytest.raises((RuntimeError, ValueError)):
            android_driver.create_driver(mode=mode, udid=udid)


@pytest.mark.parametrize('booted', ['SIM-SELECTED', 'SIM-DEFAULT'])
def test_ios_requested_simulator_must_be_booted(configured, monkeypatch, booted):
    output = json.dumps({'devices': {'iOS': [{'udid': booted, 'state': 'Booted', 'name': 'Selected'}]}})
    monkeypatch.setattr(ios_driver.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=output, returncode=0))
    if booted == 'SIM-SELECTED':
        caps = ios_driver.create_driver(mode='simulator', udid='SIM-SELECTED')
        assert caps['appium:udid'] == 'SIM-SELECTED'
        assert caps['appium:deviceName'] == 'Selected'
    else:
        with pytest.raises(RuntimeError):
            ios_driver.create_driver(mode='simulator', udid='SIM-SELECTED')


def test_ios_real_device_requires_requested_udid(configured, monkeypatch):
    monkeypatch.setattr(ios_driver.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout='OTHER-PHONE\n', returncode=0))
    with pytest.raises(RuntimeError):
        ios_driver.create_driver(mode='real_device', udid='IOS-PHONE')
