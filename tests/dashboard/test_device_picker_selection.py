"""Device choices remain accurate after grouping, keyboard input and refresh."""
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'agents/dashboard/static/execution.js'
ANDROID = [
    {'mode': 'real_device', 'udid': 'usb-a', 'deviceName': 'Phone', 'connected': True},
    {'mode': 'emulator', 'udid': 'emulator-a', 'deviceName': 'Emulator',
     'connected': True, 'default': True},
    {'mode': 'real_device', 'udid': 'usb-off', 'deviceName': 'Offline', 'connected': False},
]


def setup_picker(page):
    page.set_default_timeout(2000)
    page.set_content('''<div class="device-picker"><div id="pipeline-device-list"></div>
        <div id="pipeline-device-hint"></div></div>
        <div class="device-picker"><div id="quick-device-list"></div>
        <div id="quick-device-hint"></div></div>''')
    page.evaluate('window.esc = value => String(value)')
    page.add_script_tag(path=str(SCRIPT))
    page.evaluate("devices => _renderDeviceList('pipeline-device-list', 'pipeline-device-hint', devices, null, 'android')", ANDROID)


def test_grouped_device_radio_selects_the_visible_device_with_keyboard(page):
    setup_picker(page)
    phone = page.locator('#pipeline-device-list').get_by_role('radio', name='Phone', exact=False)
    phone.focus()
    page.keyboard.press('Space')
    assert phone.is_checked()
    assert page.evaluate("getSelectedDeviceParams('android')") == {
        'mode': 'real_device', 'device_udid': 'usb-a',
    }
    assert page.get_by_role('radio', name='Offline', exact=False).is_disabled()
    assert page.locator('input[type=radio]:checked').count() == 1


def test_refresh_keeps_platform_device_choices_independent(page):
    setup_picker(page)
    page.locator('#pipeline-device-list').get_by_role('radio', name='Phone', exact=False).check()
    ios = [{'mode': 'simulator', 'udid': 'ios-a', 'deviceName': 'iPhone', 'connected': True}]
    page.evaluate("devices => _renderDeviceList('quick-device-list', 'quick-device-hint', devices, null, 'ios')", ios)
    assert page.evaluate("getSelectedDeviceParams('android').device_udid") == 'usb-a'
    assert page.evaluate("getSelectedDeviceParams('ios').device_udid") == 'ios-a'
    page.evaluate("devices => _renderDeviceList('pipeline-device-list', 'pipeline-device-hint', devices, null, 'android')", ANDROID)
    assert page.locator('#pipeline-device-list').get_by_role('radio', name='Phone', exact=False).is_checked()


def test_refresh_replaces_disconnected_choice_with_connected_device(page):
    setup_picker(page)
    page.locator('#pipeline-device-list').get_by_role('radio', name='Phone', exact=False).check()
    changed = [dict(d, connected=False) if d['udid'] == 'usb-a' else d for d in ANDROID]
    page.evaluate("devices => _renderDeviceList('pipeline-device-list', 'pipeline-device-hint', devices, null, 'android')", changed)
    assert page.get_by_role('radio', name='Emulator', exact=False).is_checked()
    assert page.evaluate("getSelectedDeviceParams('android').device_udid") == 'emulator-a'
    assert not page.locator('#pipeline-device-list').get_by_role('radio', name='Phone', exact=False).is_checked()


def test_refresh_synchronizes_other_picker_when_device_disconnects(page):
    setup_picker(page)
    page.evaluate("devices => _renderDeviceList('quick-device-list', 'quick-device-hint', devices, null, 'android')", ANDROID)
    page.locator('#pipeline-device-list').get_by_role('radio', name='Phone', exact=False).check()
    assert page.locator('#quick-device-list').get_by_role('radio', name='Phone', exact=False).is_checked()
    changed = [dict(d, connected=False) if d['udid'] == 'usb-a' else d for d in ANDROID]
    page.evaluate("devices => _renderDeviceList('quick-device-list', 'quick-device-hint', devices, null, 'android')", changed)
    for picker in ['pipeline-device-list', 'quick-device-list']:
        container = page.locator('#' + picker)
        assert container.get_by_role('radio', name='Emulator', exact=False).is_checked()
        assert not container.get_by_role('radio', name='Phone', exact=False).is_checked()
        assert container.get_by_role('radio', name='Phone', exact=False).is_disabled()
    assert page.evaluate("getSelectedDeviceParams('android').device_udid") == 'emulator-a'
