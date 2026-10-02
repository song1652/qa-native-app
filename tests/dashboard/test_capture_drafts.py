"""Capture action drafts survive a real browser reload without device calls."""
import json
from pathlib import Path
import re

import pytest

STATIC = Path(__file__).parents[2] / 'agents/dashboard/static'
STUBS = '''csPlatformToggle=()=>{};csMirrorConnect=()=>{};csRefreshHierarchy=()=>{};
csMcpStartPoll=()=>{};csMcpStopPoll=()=>{};csInfoStripShow=()=>{};csInfoStripHide=()=>{};
csMirrorDisconnect=()=>{};csStopScreenWatcher=()=>{};window._csLtOpen=false;
window.dashboardConfirm=async()=>true;'''


def setup_draft_page(page, session_id='same-session'):
    document = (STATIC.parent / 'dashboard.html').read_text()
    document = re.sub(r'<script\b[^>]*>.*?</script>|<link\b[^>]*>', '', document, flags=re.S)
    document += ''.join(f'<script src="/{name}"></script>' for name in [
        'capture-studio.js', 'capture-inspector.js', 'capture-actions.js',
    ])
    page.route('http://capture-draft.test/', lambda route: route.fulfill(body=document))
    page.route(re.compile(r'http://capture-draft.test/.*\.js$'), lambda route: route.fulfill(
        body=(STATIC / route.request.url.rsplit('/', 1)[1]).read_text(),
        content_type='text/javascript',
    ))
    session = {'session_id': session_id, 'platform': 'android', 'target': 'emulator',
               'actions': [{'index': 1, 'action': 'tap', 'device_x': 10, 'device_y': 20}]}
    page.add_init_script('''window.WebSocket=class{constructor(){this.readyState=0;}close(){}};
      window.esc=value=>String(value == null ? '' : value);
      window.fetch=async url=>({json:async()=>url==='/capture/session'
        ? {active:true,session:''' + json.dumps(session) + '''}
        : url==='/capture/driver_alive' ? {alive:true} : {ok:true}});''')
    page.goto('http://capture-draft.test/')
    page.evaluate(STUBS)


def test_manual_tap_and_assert_with_expected_survive_reload_without_raw_duplicate(page):
    setup_draft_page(page)
    page.evaluate('''_cs.sessionId='same-session';
      _cs.selectedNodeAttrs={'resource-id':'app:id/title',text:'Title'};
      csAddStep('tap');csAddStep('assert');csSetStepExpected(1,'Title is visible');''')
    page.reload()
    page.evaluate(STUBS + 'csInit();')
    page.wait_for_function("document.getElementById('cs-workspace').style.display==='block'")
    actions = page.evaluate('_cs.actions')
    assert [action['action'] for action in actions] == ['tap', 'assert']
    assert actions[1]['expected'] == 'Title is visible'
    assert actions[0]['value'] == 'app:id/title'
    assert 'device_x' not in actions[0]


@pytest.mark.parametrize('draft', ['[]', 'broken json', '[null]', None])
def test_empty_draft_is_authoritative_and_invalid_draft_uses_server(page, draft):
    setup_draft_page(page)
    if draft is not None:
        page.evaluate("value=>sessionStorage.setItem('capture-draft:same-session',value)", draft)
    page.evaluate(STUBS + 'csInit();')
    page.wait_for_function("document.getElementById('cs-workspace').style.display==='block'")
    assert len(page.evaluate('_cs.actions')) == (0 if draft == '[]' else 1)


def test_draft_from_another_session_is_not_restored(page):
    setup_draft_page(page, 'new-session')
    page.evaluate('''sessionStorage.setItem('capture-draft:old-session',
      JSON.stringify([{action:'assert'}]));''')
    page.evaluate(STUBS + 'csInit();')
    page.wait_for_function("document.getElementById('cs-workspace').style.display==='block'")
    assert page.evaluate('_cs.actions[0].action') == 'tap'


def test_successful_clear_persists_empty_draft_across_reload(page):
    setup_draft_page(page)
    page.evaluate('''_cs.sessionId='same-session';_cs.actions=[{action:'assert'}];
      csRenderTimeline();csClearActions();''')
    page.wait_for_function('!_cs.clearing')
    page.reload()
    page.evaluate(STUBS + 'csInit();')
    page.wait_for_function("document.getElementById('cs-workspace').style.display==='block'")
    assert page.evaluate('_cs.actions') == []


def test_unavailable_storage_does_not_prevent_manual_edits(page):
    setup_draft_page(page)
    page.evaluate('''Storage.prototype.setItem=()=>{throw Error('storage unavailable')};
      _cs.sessionId='same-session';_cs.selectedNodeAttrs={'resource-id':'app:id/title'};
      csAddStep('tap');csSetStepExpected(0,'Still editable');''')
    assert page.evaluate('_cs.actions[0].expected') == 'Still editable'


@pytest.mark.parametrize('entry', ['csEndSession', 'csForceNewSession'])
def test_successful_end_removes_only_ended_session_draft(page, entry):
    setup_draft_page(page)
    page.evaluate('''_cs.sessionId='same-session';
      sessionStorage.setItem('capture-draft:same-session','[]');
      sessionStorage.setItem('capture-draft:other-session','[]');''')
    page.evaluate(entry + '();')
    page.wait_for_function("_cs.sessionId===''")
    assert page.evaluate("sessionStorage.getItem('capture-draft:same-session')") is None
    assert page.evaluate("sessionStorage.getItem('capture-draft:other-session')") == '[]'


@pytest.mark.parametrize('entry', ['csEndSession', 'csForceNewSession'])
def test_failed_end_keeps_draft_for_recovery(page, entry):
    setup_draft_page(page)
    page.evaluate('''_cs.sessionId='same-session';
      sessionStorage.setItem('capture-draft:same-session','[]');
      window.fetch=async()=>({json:async()=>({ok:false,error:'mocked failure'})});''')
    page.evaluate(entry + '();')
    page.wait_for_function("_cs.sessionId===''")
    assert page.evaluate("sessionStorage.getItem('capture-draft:same-session')") == '[]'
