"""Actual settings DOM and JS with deferred, fully mocked device requests."""
from pathlib import Path

DASHBOARD = Path(__file__).parents[3] / 'agents/dashboard'


def setup_env_controls(page):
    page.route('**/*', lambda route: route.abort())
    page.set_content((DASHBOARD / 'dashboard.html').read_text())
    page.evaluate('''() => {window.esc = value => String(value == null ? '' : value);
      window.pollEnvStatus = () => {};window.pending = [];
      window.fetch = (url, options) => new Promise(resolve => pending.push({url,options,resolve}));}''')
    page.add_script_tag(path=str(DASHBOARD / 'static/environment-devices.js'))


def test_late_android_discovery_cannot_replace_new_ios_add_dialog(page):
    setup_env_controls(page)
    page.evaluate("envShowAddModal('android','emulator');envCloseAddModal();envShowAddModal('ios','simulator')")
    page.evaluate('''() => pending[0].resolve({ok:true,json:async()=>({ok:true,avds:[{avd:'OldAVD',deviceName:'Old Android',platformVersion:'15'}]})})''')
    page.wait_for_timeout(20)
    assert page.locator('#env-add-device-select option').all_text_contents() == ['불러오는 중...']
    assert page.locator('#env-add-deviceName').input_value() == ''
    assert page.locator('#env-add-register').is_disabled()
    page.evaluate('''() => pending[1].resolve({ok:true,json:async()=>({ok:true,simulators:[{udid:'SIM-1',deviceName:'New iOS',platformVersion:'18'}]})})''')
    page.wait_for_function("document.getElementById('env-add-deviceName').value === 'New iOS'")
    assert page.locator('#env-add-udid').input_value() == 'SIM-1'


def test_previous_wifi_response_cannot_close_reopened_dialog(page):
    setup_env_controls(page)
    page.evaluate("envShowWifiPairModal();document.getElementById('env-pair-ip').value='192.168.1.2';document.getElementById('env-pair-port').value='30000';document.getElementById('env-pair-code').value='123456';envSubmitWifiPair();envCloseWifiPairModal();envShowWifiPairModal()")
    page.evaluate('''() => pending[0].resolve({ok:true,json:async()=>({ok:true,detail:'Old response'})})''')
    page.wait_for_timeout(2100)
    assert page.locator('#env-wifi-pair-modal').evaluate('(el)=>el.open')
    assert page.locator('#env-pair-result').inner_text() == ''


def test_previous_wda_response_cannot_overwrite_reopened_dialog(page):
    setup_env_controls(page)
    page.evaluate("envShowWdaBuildModal();document.getElementById('env-wda-udid').value='PHONE';document.getElementById('env-wda-teamid').value='TEAM';envSubmitWdaBuild();envCloseWdaBuildModal();envShowWdaBuildModal()")
    page.evaluate('''() => pending[0].resolve({ok:true,json:async()=>({ok:true,detail:'Old response'})})''')
    page.wait_for_timeout(20)
    assert page.locator('#env-wda-result').inner_text() == ''


def test_offline_generate_and_lint_preserve_prerequisite_state_without_appium(page):
    setup_env_controls(page)
    page.add_script_tag(path=str(DASHBOARD / 'static/environment.js'))
    page.evaluate("document.getElementById('btn-generate').disabled=false;document.getElementById('btn-lint').disabled=false;updateEnvAppiumCard({status:'stopped',drivers:{}})")
    assert not page.locator('#btn-generate').is_disabled()
    assert not page.locator('#btn-lint').is_disabled()
    assert page.locator('#btn-execute').is_disabled()
    page.evaluate("document.getElementById('btn-lint').disabled=true;updateEnvAppiumCard({status:'managed',drivers:{}})")
    assert page.locator('#btn-lint').is_disabled()


def test_appium_poll_preserves_stage_prerequisites_and_running_controls(page):
    setup_env_controls(page)
    page.add_script_tag(path=str(DASHBOARD / 'static/environment.js'))
    page.evaluate("window._prereq={execute:'lint',heal:'execute'};window._stepState={lint:'idle',execute:'idle'};window._runAllActive=false;updateEnvAppiumCard({status:'managed',drivers:{}})")
    assert page.locator('#btn-execute').is_disabled()
    assert page.locator('#btn-heal').is_disabled()
    page.evaluate("_stepState.lint='done';updateEnvAppiumCard({status:'managed',drivers:{}})")
    assert not page.locator('#btn-execute').is_disabled()
    page.evaluate("document.getElementById('btn-execute').classList.add('loading');document.getElementById('btn-execute').disabled=true;_runAllActive=true;document.getElementById('btn-run-all').disabled=false;updateEnvAppiumCard({status:'stopped',drivers:{}})")
    assert page.locator('#btn-execute').is_disabled()
    assert not page.locator('#btn-run-all').is_disabled()


def test_wifi_and_wda_disable_duplicate_requests_and_allow_retry_after_error(page):
    setup_env_controls(page)
    page.evaluate("envShowWifiPairModal();document.getElementById('env-pair-ip').value='192.168.1.2';document.getElementById('env-pair-port').value='30000';document.getElementById('env-pair-code').value='123456';envSubmitWifiPair();envSubmitWifiPair()")
    assert page.evaluate('pending.length') == 1
    assert page.locator('#env-wifi-pair-modal button[onclick="envSubmitWifiPair()"]').is_disabled()
    page.evaluate('''pending[0].resolve({ok:false,json:async()=>({ok:false,error:'Rejected'})})''')
    page.wait_for_function('!_envWifiBusy')
    assert not page.locator('#env-wifi-pair-modal button[onclick="envSubmitWifiPair()"]').is_disabled()
    page.evaluate("envCloseWifiPairModal();envShowWdaBuildModal();document.getElementById('env-wda-udid').value='PHONE';document.getElementById('env-wda-teamid').value='TEAM';envSubmitWdaBuild();envSubmitWdaBuild()")
    assert page.evaluate('pending.length') == 2
    assert page.locator('#env-wda-build-modal button[onclick="envSubmitWdaBuild()"]').is_disabled()
    page.evaluate('''pending[1].resolve({ok:false,json:async()=>({ok:false,error:'Rejected'})})''')
    page.wait_for_function('!_envWdaBusy')
    assert not page.locator('#env-wda-build-modal button[onclick="envSubmitWdaBuild()"]').is_disabled()
