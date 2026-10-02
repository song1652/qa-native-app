"""Manual Capture controls exercised without network or device actions."""
from pathlib import Path

STATIC = Path(__file__).parents[2] / 'agents/dashboard/static'


def setup_controls(page):
    page.set_content('''<div id="cs-timeline"></div><div id="cs-save-status"></div>
      <input id="cs-tc-id" value="tc_example"><input id="cs-tc-title" value="Example">
      <select id="cs-platform"><option>android</option></select><input id="cs-group" value="example">
      <pre id="cs-preview-md"></pre><pre id="cs-preview-py"></pre><div id="cs-preview-source"></div>
      <button id="cs-save-btn"></button><button id="cs-preview-save"></button><dialog id="cs-preview-modal"></dialog>
      <button id="approve"></button>''')
    page.evaluate('''() => {
      window._cs={sessionId:'session',context:'native',actions:[],approvedLocators:[],selectedNodeAttrs:null};
      window.esc = value => String(value == null ? '' : value);
      window.requests=[]; window.fetch=async (url, options) => {requests.push({url,body:JSON.parse(options.body)});return {json:async()=>({ok:true})};};
      window.csRefreshHierarchy=()=>{};
    }''')
    page.add_script_tag(path=str(STATIC / 'capture-inspector.js'))
    page.add_script_tag(path=str(STATIC / 'capture-actions.js'))


def test_approved_locator_is_scoped_to_selected_element(page):
    setup_controls(page)
    page.evaluate('''() => {
      _cs.selectedNodeAttrs={'resource-id':'app:first',class:'Button'};
      csApproveLocator('resource-id','app:first',5,document.getElementById('approve'));
      _cs.selectedNodeAttrs={'resource-id':'app:second',class:'Button'};
      csAddStep('tap');
    }''')
    assert page.evaluate('_cs.actions[0].value') == 'app:second'


def test_direct_back_has_step_number_and_readable_summary(page):
    setup_controls(page)
    page.evaluate("csAddDirectStep('back')")
    assert page.evaluate('_cs.actions[0].action') == 'back'
    assert page.evaluate('_cs.actions[0].index') == 1
    assert 'undefined' not in page.locator('#cs-timeline').inner_text()
    assert '뒤로가기' in page.locator('#cs-timeline').inner_text()


def test_bottom_back_button_records_visible_step_and_single_device_request(page):
    setup_controls(page)
    page.evaluate('csSendBack()')
    page.wait_for_function('requests.length === 1')
    assert page.evaluate('_cs.actions.length') == 1
    assert page.evaluate('requests[0].url') == '/capture/back'


def test_input_summary_and_preview_show_authored_text_and_locator(page):
    setup_controls(page)
    page.evaluate('''() => {
      _cs.actions=[{index:1,action:'input',strategy:'resource-id',value:'app:search',input_text:'Bluetooth',label:'Search'}];
      csRenderTimeline();csPreviewTC();
    }''')
    assert 'Bluetooth' in page.locator('#cs-timeline').inner_text()
    assert 'Bluetooth' in page.locator('#cs-preview-py').inner_text()
    assert 'app:search' in page.locator('#cs-preview-py').inner_text()


def test_preview_includes_manual_tap_locator(page):
    setup_controls(page)
    page.evaluate("_cs.actions=[{index:1,action:'tap',strategy:'resource-id',value:'app:search',label:'Search'}];csPreviewTC()")
    assert 'app:search' in page.locator('#cs-preview-py').inner_text()


def test_failed_clear_preserves_unsaved_manual_steps(page):
    setup_controls(page)
    page.evaluate("window.dashboardConfirm=async()=>true;_cs.actions=[{index:1,action:'tap',label:'Keep me'}];window.fetch=async()=>({json:async()=>({ok:false,error:'Unavailable'})})")
    page.evaluate('csClearActions()')
    assert page.evaluate('_cs.actions.length') == 1
    assert 'Unavailable' in page.locator('#cs-save-status').inner_text()


def test_old_clear_response_cannot_remove_new_session_steps(page):
    setup_controls(page)
    page.evaluate("window.dashboardConfirm=async()=>true;_cs.actions=[{action:'tap',label:'Old'}];window.fetch=()=>new Promise(resolve=>window.finishClear=()=>resolve({json:async()=>({ok:true})}));csClearActions();void 0")
    page.wait_for_function('typeof finishClear === "function"')
    page.evaluate("_cs.sessionId='new-session';_cs.actions=[{action:'tap',label:'New'}];finishClear()")
    page.wait_for_function('!_cs.clearing')
    assert page.evaluate('_cs.actions[0].label') == 'New'


def test_locator_candidates_use_android_class_attribute_and_ios_name(page):
    setup_controls(page)
    android = page.evaluate("csRenderLocatorCards({class:'android.widget.Button'})")
    assert '//*[@class=' in android
    ios = page.evaluate("csRenderLocatorCards({type:'XCUIElementTypeButton',name:'stable-id',label:'Settings'})")
    assert 'stable-id' in ios
    page.evaluate("_cs.selectedNodeAttrs={type:'XCUIElementTypeButton',name:'stable-id',label:'Settings'}")
    assert page.evaluate('_csBestLocator().value') == 'stable-id'


def test_clear_preserves_newly_appended_steps_and_renumbers_them(page):
    setup_controls(page)
    page.evaluate("window.dashboardConfirm=async()=>true;_cs.actions=[{index:1,action:'tap',label:'Old'}];window.fetch=()=>new Promise(resolve=>window.finishClear=()=>resolve({json:async()=>({ok:true})}));csClearActions();void 0")
    page.wait_for_function('typeof finishClear === "function"')
    page.evaluate("_cs.actions.push({index:2,action:'tap',label:'New'});finishClear()")
    page.wait_for_function('!_cs.clearing')
    assert page.evaluate('_cs.actions') == [{'index': 1, 'action': 'tap', 'label': 'New'}]


def test_locator_buttons_preserve_quotes_and_newlines_with_production_escaping(page):
    setup_controls(page)
    page.add_script_tag(path=str(STATIC / 'execution.js'))
    value = 'Bob\'s "Settings"\n& Bluetooth'
    page.evaluate('''value => {
      _cs.selectedNodeAttrs={'content-desc':value,class:'android.widget.Button'};
      document.body.insertAdjacentHTML('beforeend','<div id="actual-locators"></div>');
      document.getElementById('actual-locators').innerHTML=csRenderLocatorCards(_cs.selectedNodeAttrs);
      window.csValidateLocator=(strategy,value)=>window.validated={strategy,value};
    }''', value)
    page.locator('#actual-locators .cs-loc-card').first.get_by_role('button', name='검증', exact=True).click()
    assert page.evaluate('window.validated') == {'strategy': 'accessibility-id', 'value': value}
    page.locator('#actual-locators .cs-loc-card').first.get_by_role('button', name='승인 ✓', exact=True).click()
    assert page.evaluate('_cs.approvedLocators[0].value') == value
