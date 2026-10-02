"""Menu reentry reloads server data while retaining active work."""
import json
import re
from pathlib import Path

from tests.dashboard.test_tc_studio_e2e import tc_server  # noqa: F401

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'agents/dashboard/static'


@pytest.fixture
def navigation_page(page):
    document = (ROOT / 'agents/dashboard/dashboard.html').read_text()
    document = re.sub(r'<script\b[^>]*>.*?</script>', '', document, flags=re.S)
    document = re.sub(r'<link\b[^>]*>', '', document)
    page.route('http://navigation.test/', lambda route: route.fulfill(body=document, content_type='text/html'))
    page.goto('http://navigation.test/')
    page.evaluate("""() => {
      window.esc = value => {const el=document.createElement('span');el.textContent=value;return el.innerHTML;};
      window.refreshStatus = async () => {};
      window.loadDevicePicker = () => {};
      window._obsKeep = 'on_failure';
      window._obsStripHtml = () => '';
      window.updateAutomationStatus = () => {};
      window._obsRenderCompletedQuickRun = async () => {};
    }""")
    for script in ('dashboard-shell.js', 'reports.js', 'quick-run.js'):
        page.add_script_tag(path=str(STATIC / script))
    return page


def test_reports_menu_reloads_on_reentry_and_active_click(navigation_page):
    page = navigation_page
    reports = []
    requests = []
    def serve(route):
        requests.append(route.request.url)
        route.fulfill(json=reports)
    page.route('**/api/reports', serve)
    page.locator('[data-view="reports"]').click()
    page.wait_for_function("document.querySelector('#report-count').textContent === '0개 리포트'")
    reports.append({'name': 'report_android_new.html', 'modified_at': '2026-10-02', 'size': 1000})
    page.locator('[data-view="reports"]').click()
    page.wait_for_function("document.querySelector('#report-count').textContent === '1개 리포트'")
    assert page.locator('.report-name').inner_text() == 'report_android_new.html'
    assert len(requests) == 2
    assert page.locator('[data-view="reports"]').get_attribute('aria-current') == 'page'
    page.locator('[data-view="history"]').click()
    assert page.locator('[data-view="reports"]').get_attribute('aria-current') is None
    reports.clear()
    page.locator('[data-view="reports"]').click()
    page.wait_for_function("document.querySelector('#report-count').textContent === '0개 리포트'")
    assert len(requests) == 3


def test_quick_menu_refreshes_folders_without_erasing_completed_work(navigation_page):
    page = navigation_page
    data = [{'platform': 'android', 'count': 1, 'files': ['old/tc_old.py']}]
    requests = []
    def generated(route):
        requests.append(route.request.url)
        route.fulfill(json=data)
    page.route('**/api/generated?platform=android', generated)
    page.evaluate('refreshGenerated()')
    page.locator('.quick-group-list .quick-group-cb').uncheck()
    page.evaluate("""() => {
      _quickRunResultVisible=true;
      document.querySelector('#quick-generated-result').textContent='실행 결과 유지';
      document.querySelector('#quick-generated-log').textContent='기존 실행 로그';
    }""")
    data[0]['count'] = 2
    data[0]['files'].append('new/tc_new.py')
    page.locator('[data-view="tests"]').click()
    page.wait_for_function("document.querySelectorAll('.quick-group-list .quick-group-cb').length === 2")
    assert len(requests) == 2
    assert not page.locator('.quick-group-list .quick-group-cb').first.is_checked()
    assert page.locator('#quick-generated-result').inner_text() == '실행 결과 유지'
    assert page.locator('#quick-generated-log').text_content() == '기존 실행 로그'
    assert page.evaluate('_generatedTests[0].count') == 2
    page.evaluate('_quickRunActive=true')
    page.locator('[data-view="tests"]').click()
    assert len(requests) == 2


def test_history_menu_reflects_external_storage_changes(navigation_page):
    page = navigation_page
    entry = dict(type='quick', platform='android', passed=1, total=1, failed=0, rate=100, executedAt='2026-10-02')
    page.evaluate('value => localStorage.setItem("qa-native-app.run-history", value)', json.dumps([entry]))
    page.locator('[data-view="history"]').click()
    assert page.locator('#history-total').inner_text() == '1'
    page.evaluate('localStorage.removeItem("qa-native-app.run-history")')
    page.locator('[data-view="history"]').click()
    assert page.locator('#history-total').inner_text() == '0'
    assert page.locator('#history-rate').inner_text() == '0%'
    assert page.locator('#history-list').inner_text() == '실행 이력이 없습니다.'


def test_capture_menu_refreshes_status_without_restarting_session(navigation_page):
    page = navigation_page
    page.evaluate("""() => {
      window._csInitialized=true;
      window._cs={sessionId:'existing-session',actions:[{type:'tap'}]};
      window.csInit=()=>{throw new Error('must retain session');};
      window.pollEnvStatus=()=>fetch('/api/env/status');
      window.csMcpStatusPoll=()=>fetch('/capture/mcp_status');
    }""")
    requests = []
    def status(route):
        requests.append(route.request.url)
        route.fulfill(json={})
    page.route('**/api/env/status', status)
    page.route('**/capture/mcp_status', status)
    page.locator('[data-view="capture"]').click()
    page.wait_for_function('true')
    assert page.evaluate('_cs.sessionId') == 'existing-session'
    assert page.evaluate('_cs.actions.length') == 1
    assert len(requests) == 2


def test_studio_menu_reloads_library_and_retains_unsaved_detail(tc_server, page):
    import _tc_library as lib
    from _tc_model import new_case

    first = new_case(case_id='NAV_001', sheet='설정', path=['설정', '', ''], feature='첫 케이스')
    lib.import_cases('navigation', ['설정'], [first], 'seed')
    page.goto(f'{tc_server}/tc-studio')
    page.locator('#screen-generate.active').wait_for()
    page.locator('#suite-select').select_option('navigation')
    page.locator('[data-id="nav-tab-library"]').click()
    page.locator('tr[data-case="NAV_001"] [data-id="grid-cell-feature"]').click()
    page.locator('#detail-feature').fill('저장하지 않은 제목')
    assert page.locator('#d-dirty').is_visible()
    page.locator('#src-paste').evaluate("el => el.value = '저장하지 않은 기획 문서'")
    second = new_case(case_id='NAV_002', sheet='설정', path=['설정', '', ''], feature='외부에서 추가한 케이스')
    lib.import_cases('navigation', ['설정'], [second], 'external')
    page.locator('.sidebar-item[data-view="tc_studio"]').click()
    page.locator('tr[data-case="NAV_002"]').wait_for()
    assert page.locator('#detail-feature').input_value() == '저장하지 않은 제목'
    assert page.locator('#d-dirty').is_visible()
    assert page.locator('#suite-select').input_value() == 'navigation'
    assert page.locator('#src-paste').input_value() == '저장하지 않은 기획 문서'


def test_report_actions_and_selection_remain_separate(navigation_page):
    page = navigation_page
    page.route('**/api/reports', lambda route: route.fulfill(json=[{
        'name': 'report_android_new.html', 'modified_at': '2026-10-02', 'size': 1000,
    }]))
    page.evaluate('initReportControls()')
    page.locator('[data-view="reports"]').click()
    page.locator('.report-name').wait_for()
    assert page.locator('#report-delete-selected').is_disabled()
    page.locator('.report-item input').check()
    assert not page.locator('#report-delete-selected').is_disabled()
    assert page.locator('#report-iframe').get_attribute('src') is None
    page.locator('.report-actions button').filter(has_text='열기').click()
    assert page.locator('#report-iframe').get_attribute('src') == '/reports/report_android_new.html'
    assert page.locator('.report-actions a').get_attribute('target') == '_blank'
    page.locator('.report-item input').uncheck()
    assert page.locator('#report-delete-selected').is_disabled()


def test_leaving_evidence_clears_run_hash_and_preserves_history_navigation(navigation_page):
    page = navigation_page
    page.route('**/api/reports', lambda route: route.fulfill(json=[]))
    page.evaluate("history.replaceState({},'', '/?view=tests#obs/run_android_20261002_114701_780')")
    page.locator('[data-view=reports]').click()
    assert page.evaluate('location.hash') == ''
    assert '?view=reports' in page.url
    page.go_back()
    assert page.evaluate('location.hash') == '#obs/run_android_20261002_114701_780'


def test_late_evidence_load_does_not_pin_a_different_menu(navigation_page):
    page = navigation_page
    page.add_script_tag(path=str(STATIC / 'observability.js'))
    page.evaluate("""() => {
      history.replaceState({},'', '/?view=tests');
      window._obsResolveLatestRunId=()=>new Promise(resolve=>window.finishRun=resolve);
      window._obsInjectEvidenceButtons=async()=>{};
      window.pendingEvidence=_obsRenderCompletedQuickRun('android');
      history.pushState({},'', '/?view=reports');
    }""")
    page.evaluate("async()=>{finishRun('run_android_20261002_114701_780');await pendingEvidence;}")
    assert page.evaluate('location.hash') == ''


def test_saved_other_menu_with_old_evidence_hash_stays_on_that_menu(navigation_page):
    page = navigation_page
    page.add_script_tag(path=str(STATIC / 'observability.js'))
    page.evaluate("""() => {
      history.replaceState({},'', '/?view=reports#obs/run_android_20261002_114701_780');
      window.hashRequests=[];
      window.fetch=async url=>{hashRequests.push(url);return {ok:false};};
    }""")
    page.evaluate('_obsOpenHash()')
    assert page.evaluate('hashRequests') == []


def test_late_hash_manifest_does_not_reopen_quick_execution(navigation_page):
    page = navigation_page
    page.add_script_tag(path=str(STATIC / 'observability.js'))
    page.evaluate("""() => {
      history.replaceState({},'', '/#obs/run_android_20261002_114701_780');
      window.fetch=()=>new Promise(resolve=>window.finishManifest=resolve);
      window.reopened=false;
      window.selectView=()=>{reopened=true;};
      window.pendingHash=_obsOpenHash();
      history.pushState({},'', '/?view=reports');
    }""")
    page.evaluate("""async () => {
      finishManifest({ok:true,json:async()=>({entries:[{
        nodeid:'test_case',outcome:'passed',kept:true,screenshot:'screen.png'
      }]})});
      await pendingHash;
    }""")
    assert page.evaluate('reopened') is False


def test_late_latest_run_preserves_newly_selected_historical_run(navigation_page):
    page = navigation_page
    page.add_script_tag(path=str(STATIC / 'observability.js'))
    page.evaluate("""() => {
      history.replaceState({},'', '/?view=tests');
      window._obsResolveLatestRunId=()=>new Promise(resolve=>window.finishLatest=resolve);
      window.renderedRun=null;
      window._obsInjectEvidenceButtons=async run=>{renderedRun=run;};
      window.pendingLatest=_obsRenderCompletedQuickRun('android');
      history.pushState({},'', '/?view=tests#obs/run_android_20260930_114701_780');
    }""")
    page.evaluate("async()=>{finishLatest('run_android_20261002_114701_780');await pendingLatest;}")
    assert page.evaluate('location.hash') == '#obs/run_android_20260930_114701_780'
    assert page.evaluate('renderedRun') is None


def test_late_workspace_preserves_newly_selected_historical_run(navigation_page):
    page = navigation_page
    page.add_script_tag(path=str(STATIC / 'observability.js'))
    page.evaluate("""() => {
      history.replaceState({},'', '/?view=tests#obs/run_android_20261002_114701_780');
      window.fetch=()=>new Promise(resolve=>window.finishWorkspace=resolve);
      window.renderedRun=null;
      window._obsRenderWorkspace=run=>{renderedRun=run;};
      window.pendingWorkspace=_obsInjectEvidenceButtons('run_android_20261002_114701_780',true);
      history.pushState({},'', '/?view=tests#obs/run_android_20260930_114701_780');
    }""")
    page.evaluate("async()=>{finishWorkspace({ok:true,json:async()=>({entries:[]})});await pendingWorkspace;}")
    assert page.evaluate('renderedRun') is None
