"""WDA startup defaults use supported capabilities without device commands."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.drivers import ios_driver


@pytest.mark.parametrize('key,configured,expected', [
    ('wdaLaunchTimeout', None, 180000),
    ('wdaLaunchTimeout', 240000, 240000),
    ('appium:wdaLaunchTimeout', 240000, 240000),
])
@pytest.mark.parametrize('factory', ['generated', 'legacy'])
def test_ios_factories_default_wda_timeout_and_preserve_user_value(
    monkeypatch, tmp_path, key, configured, expected, factory,
):
    monkeypatch.delenv('DEVICE_MODE', raising=False)
    monkeypatch.delenv('DEVICE_UDID', raising=False)
    device = {'udid': 'SIM-ONLY', 'automationName': 'XCUITest'}
    if configured is not None:
        device[key] = configured
    (tmp_path / 'devices.json').write_text(json.dumps({'ios': {'simulator': device}}))
    (tmp_path / 'test_data.json').write_text(json.dumps({'app': {'ios': {
        'bundle_id': 'com.apple.Preferences', 'app_path': '',
    }}}))
    if factory == 'legacy':
        monkeypatch.setattr(ios_driver, 'CONFIG_DIR', tmp_path)
        caps = ios_driver.get_capabilities()
    else:
        script = Path(__file__).parents[2] / 'scripts' / '02_generate.py'
        spec = importlib.util.spec_from_file_location('generate_wda_timeout', script)
        generate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generate)

        class Options:
            def load_capabilities(self, caps):
                return caps
        namespace = {
            'Path': Path, 'json': json, 'os': os,
            'XCUITestOptions': Options,
            'webdriver': SimpleNamespace(Remote=lambda url, options: options),
        }
        exec(generate._build_ios_helpers(
            '1', 'settings', f'Path({str(tmp_path)!r})', 'com.apple.Preferences',
        ), namespace)
        caps = namespace['_build_driver']()
    from appium.options.ios.xcuitest.base import XCUITestOptions
    serialized = XCUITestOptions().load_capabilities(caps).to_capabilities()
    assert serialized['appium:wdaLaunchTimeout'] == expected
    assert caps['udid'] == 'SIM-ONLY'
    assert 'webDriverAgentStartupTimeout' not in caps


@pytest.mark.parametrize('devices,expected', [
    ([{'udid': 'FIRST'}, {'udid': 'DEFAULT', 'default': True}], 'DEFAULT'),
    ([{'udid': 'FIRST'}, {'udid': 'SECOND'}], 'FIRST'),
    ({'udid': 'LEGACY', 'default': True, 'note': 'operator note'}, 'LEGACY'),
])
def test_legacy_ios_driver_selects_default_in_array_and_filters_metadata(
    monkeypatch, tmp_path, devices, expected,
):
    (tmp_path / 'devices.json').write_text(json.dumps({'ios': {'simulator': devices}}))
    (tmp_path / 'test_data.json').write_text(json.dumps({'app': {'ios': {
        'bundle_id': 'com.apple.Preferences', 'app_path': '',
    }}}))
    monkeypatch.setattr(ios_driver, 'CONFIG_DIR', tmp_path)
    caps = ios_driver.get_capabilities()
    assert caps['udid'] == expected
    assert caps['wdaLaunchTimeout'] == 180000
    assert not {'default', 'note'} & caps.keys()
