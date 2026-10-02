"""Capture respects the selected device kind; all device/network actions are mocked."""
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'agents/dashboard/static/capture-studio.js'
VIRTUAL = {'mode': 'emulator', 'udid': 'emulator-5554', 'deviceName': 'Virtual', 'connected': True}
REAL = {'mode': 'real_device', 'udid': 'usb-1', 'deviceName': 'Phone', 'connected': True}


def setup_capture(page, devices):
    page.set_content('''<select id="cs-platform" onchange="csPlatformToggle()"><option>android</option><option>ios</option></select>
        <select id="cs-target" onchange="csTargetChanged()"><option value="emulator">Virtual</option><option value="device">Real</option></select>
        <input id="cs-pkg" value="app.test"><input id="cs-activity"><input id="cs-group"><input id="cs-mjpeg-port" value="8093">
        <input id="cs-bundle-id" value="app.test"><select id="cs-device-name"></select>
        <div id="cs-setup-status"></div><button id="cs-start-btn" disabled>Start</button>''')
    page.evaluate('devices => {window.devices = devices; window.requests = []; window.fetch = async (url, options) => { requests.push({url, body: options && JSON.parse(options.body)}); return {json: async () => url.startsWith("/api/devices") ? {devices: window.devices} : url === "/capture/session" ? {ok:false,error:"mock session response"} : {ok:true}}; };}', devices)
    page.add_script_tag(path=str(SCRIPT))


def test_stopped_virtual_does_not_enable_or_start_connected_real_device(page):
    setup_capture(page, [dict(VIRTUAL, connected=False), REAL])
    page.evaluate('csCheckEnv()')
    assert page.locator('#cs-start-btn').is_disabled()
    assert '에뮬레이터' in page.locator('#cs-setup-status').inner_text()
    page.evaluate('csStartSession()')
    page.wait_for_function('!_cs.launching')
    assert not page.evaluate('requests.some(r => r.url === "/capture/session")')


def test_start_posts_selected_kind_and_exact_connected_udid(page):
    setup_capture(page, [REAL, VIRTUAL])
    page.evaluate('csCheckEnv()')
    page.wait_for_function('!document.getElementById("cs-start-btn").disabled')
    page.evaluate('csStartSession()')
    page.wait_for_function('requests.some(r => r.url === "/capture/session")')
    body = page.evaluate('requests.find(r => r.url === "/capture/session").body')
    assert body['target'] == 'emulator'
    assert body['udid'] == VIRTUAL['udid']


def test_changing_kind_invalidates_environment_check(page):
    setup_capture(page, [VIRTUAL, REAL])
    page.evaluate('csCheckEnv()')
    page.wait_for_function('!document.getElementById("cs-start-btn").disabled')
    page.select_option('#cs-target', 'device')
    assert page.locator('#cs-start-btn').is_disabled()
    assert '환경 확인' in page.locator('#cs-setup-status').inner_text()


def test_disconnected_virtual_after_check_blocks_session_post(page):
    setup_capture(page, [VIRTUAL, REAL])
    page.evaluate('csCheckEnv()')
    page.wait_for_function('!document.getElementById("cs-start-btn").disabled')
    page.evaluate('devices[0].connected = false; csStartSession()')
    page.wait_for_function('!_cs.launching')
    assert not page.evaluate('requests.some(r => r.url === "/capture/session")')
    assert page.locator('#cs-start-btn').is_disabled()


def test_ios_real_target_lists_real_devices_only(page):
    setup_capture(page, [dict(VIRTUAL, mode='simulator'), REAL])
    page.select_option('#cs-target', 'device')
    page.select_option('#cs-platform', 'ios')
    page.wait_for_function('document.getElementById("cs-device-name").options.length === 1')
    assert page.locator('#cs-device-name option').all_text_contents() == ['Phone']
    page.evaluate('csStartSession()')
    page.wait_for_function('requests.some(r => r.url === "/capture/session")')
    body = page.evaluate('requests.find(r => r.url === "/capture/session").body')
    assert body['target'] == 'device'
    assert body['udid'] == REAL['udid']
    assert body['device_name'] == 'Phone'


def test_real_device_without_resolved_udid_stays_disabled(page):
    setup_capture(page, [dict(REAL, udid='')])
    page.select_option('#cs-target', 'device')
    page.evaluate('csCheckEnv()')
    assert page.locator('#cs-start-btn').is_disabled()
    page.evaluate('csStartSession()')
    page.wait_for_function('!_cs.launching')
    assert not page.evaluate('requests.some(r => r.url === "/capture/session")')


def test_stale_environment_response_cannot_enable_new_target(page):
    setup_capture(page, [VIRTUAL, REAL])
    page.evaluate('''() => {
        const original = window.fetch;
        window.fetch = (url, options) => url === '/api/check/appium'
            ? new Promise(resolve => window.finishAppium = () => resolve({json: async () => ({ok:true})}))
            : original(url, options);
        csCheckEnv();
    }''')
    page.select_option('#cs-target', 'device')
    page.evaluate('finishAppium()')
    assert page.locator('#cs-start-btn').is_disabled()
    assert '환경 확인' in page.locator('#cs-setup-status').inner_text()


def test_stopped_ios_simulator_never_starts_connected_iphone(page):
    setup_capture(page, [dict(VIRTUAL, mode='simulator', connected=False), REAL])
    page.select_option('#cs-platform', 'ios')
    page.wait_for_function('document.getElementById("cs-device-name").options.length === 1')
    page.evaluate('csCheckEnv()')
    assert page.locator('#cs-start-btn').is_disabled()
    assert '시뮬레이터' in page.locator('#cs-setup-status').inner_text()
    page.evaluate('csStartSession()')
    page.wait_for_function('!_cs.launching')
    assert not page.evaluate('requests.some(r => r.url === "/capture/session")')


def test_restore_retains_real_target_and_saved_ios_device_name(page):
    setup_capture(page, [dict(VIRTUAL, mode='simulator'), dict(REAL, udid='usb-2', deviceName='Other'), REAL])
    page.evaluate('''() => {
        window.csMcpStartPoll = () => {};
        document.getElementById('cs-device-name').innerHTML = '<option>Other</option>';
        document.body.insertAdjacentHTML('beforeend', '<span id="cs-session-badge"></span>');
        const original = window.fetch;
        window.fetch = async (url, options) => url === '/capture/session' && !options
            ? {json: async () => ({active:true, session:{session_id:'saved', platform:'ios', target:'device', device_name:'Phone'}})}
            : original(url, options);
        csInit();
    }''')
    page.wait_for_function('document.getElementById("cs-device-name").options.length === 2')
    assert page.locator('#cs-target').input_value() == 'device'
    assert page.locator('#cs-device-name').input_value() == 'Phone'
    assert page.locator('#cs-start-btn').is_disabled()


def test_actual_setup_fields_invalidate_target_checks():
    html = (SCRIPT.parent.parent / 'dashboard.html').read_text()
    assert 'id="cs-target" class="cs-select" onchange="csTargetChanged()"' in html
    assert 'id="cs-device-name" class="cs-select" onchange="csTargetChanged()"' in html
    assert 'id="cs-platform" class="cs-select" onchange="csPlatformToggle()"' in html


def test_ios_name_change_while_device_check_pending_does_not_post_session(page):
    setup_capture(page, [dict(VIRTUAL, mode='simulator'), dict(VIRTUAL, mode='simulator', udid='sim-2', deviceName='Other')])
    page.select_option('#cs-platform', 'ios')
    page.wait_for_function('document.getElementById("cs-device-name").options.length === 2')
    page.evaluate('''() => {
        const original = window.fetch;
        window.fetch = (url, options) => url.startsWith('/api/devices')
            ? new Promise(resolve => window.finishDevices = () => resolve({json: async () => ({devices})}))
            : original(url, options);
        csStartSession();
    }''')
    page.select_option('#cs-device-name', 'Other')
    page.evaluate('finishDevices()')
    page.wait_for_function('!_cs.launching')
    assert not page.evaluate('requests.some(r => r.url === "/capture/session")')


def test_target_change_while_session_post_pending_cancels_launch(page):
    setup_capture(page, [VIRTUAL, REAL])
    page.evaluate('''() => {
        window.csRenderTimeline = () => {};
        window.csForceNewSession = () => window.resetSessionId = _cs.sessionId;
        const original = window.fetch;
        window.fetch = (url, options) => {
            if(url === '/capture/session') {
                requests.push({url, body:JSON.parse(options.body)});
                return new Promise(resolve => window.finishSession = () => resolve({json: async () => ({ok:true, session_id:'new-session'})}));
            }
            if(url === '/capture/launch') {
                requests.push({url});
                return new Promise(() => {});
            }
            return original(url, options);
        };
        csStartSession();
    }''')
    page.wait_for_function('typeof finishSession === "function"')
    page.select_option('#cs-target', 'device')
    page.evaluate('finishSession()')
    page.wait_for_function('!_cs.launching', timeout=1000)
    assert not page.evaluate('requests.some(r => r.url === "/capture/launch")')
    assert page.locator('#cs-start-btn').is_disabled()

    assert page.evaluate('_cs.sessionId') == 'new-session'
    page.get_by_role('button', name='세션 종료 후 새 세션 준비').click()
    assert page.evaluate('resetSessionId') == 'new-session'
