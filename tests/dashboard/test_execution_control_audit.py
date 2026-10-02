"""Execution controls run against a routed document, never a device/server."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'agents/dashboard/static'


@pytest.fixture
def controls(page):
    document = (ROOT / 'agents/dashboard/dashboard.html').read_text()
    document = re.sub(r'<script\b[^>]*>.*?</script>', '', document, flags=re.S)
    document = re.sub(r'<link\b[^>]*>', '', document)
    page.context.route('http://controls.test/**', lambda route: route.fulfill(body=document, content_type='text/html'))
    page.goto('http://controls.test/')
    page.set_default_timeout(3000)
    for script in ('dashboard-shell.js', 'execution.js', 'reports.js', 'observability.js'):
        page.add_script_tag(path=str(STATIC / script))
    return page


def test_individual_execute_sends_selected_evidence_policy(controls):
    page = controls
    requests = []
    page.route('**/api/run', lambda route: (requests.append(route.request.post_data_json), route.fulfill(json={'ok': True, 'pid': 1})))
    page.evaluate("""() => { _obsKeep='always'; startLogPoll=()=>{}; getSelectedDeviceParams=()=>({mode:'emulator',device_udid:'emulator-123'}); }""")
    page.evaluate("runStep('execute')")
    assert requests[0]['obs_keep'] == 'always'
    assert requests[0]['device_udid'] == 'emulator-123'


def test_empty_evidence_filter_does_not_show_another_case(controls):
    page = controls
    page.evaluate("""() => {
      document.querySelector('#gen-all').innerHTML='<div id="quick-generated-result"></div>';
      _obsRenderWorkspace('example', {entries:[{nodeid:'passed-test',attempts:[{n:1,outcome:'passed',kept:false}]}]});
      _obsSetCaseFilter('fail');
    }""")
    assert page.locator('.obs-run-case').count() == 0
    assert page.locator('.obs-evidence-title').count() == 0
    assert 'passed-test' not in page.locator('#obs-evidence-content').inner_text()


def test_report_refresh_removes_deleted_selections(controls):
    page = controls
    reports = [{'name': 'a.html', 'modified_at': '2026-10-02', 'size': 100}]
    page.route('**/api/reports', lambda route: route.fulfill(json=reports))
    page.evaluate('refreshReports()')
    page.evaluate("toggleReportSelection('a.html',true)")
    assert not page.locator('#report-delete-selected').is_disabled()
    reports.clear()
    page.evaluate('refreshReports()')
    assert page.locator('#report-selection-count').inner_text() == '0개 선택'
    assert page.locator('#report-delete-selected').is_disabled()


def test_quoted_report_name_remains_selectable(controls):
    page = controls
    name = 'report_"설정\'확인".html'
    page.route('**/api/reports', lambda route: route.fulfill(json=[{'name': name, 'modified_at': '2026-10-02', 'size': 100}]))
    page.evaluate('refreshReports()')
    assert page.locator('.report-item input').get_attribute('data-name') == name
    page.locator('.report-item input').check()
    assert page.evaluate('Array.from(_reportSelected)') == [name]


def test_failed_batch_finishes_and_exposes_current_cancel(controls):
    page = controls
    states = [{'ok': True, 'done': False, 'step': 'execute', 'log': ''},
              {'ok': False, 'done': True, 'step': 'execute', 'log': ''}]
    page.route('**/api/run_all/status/test', lambda route: route.fulfill(json=states.pop(0)))
    page.evaluate("""() => { _runAllActive=true; window.finished=[]; _finishRunAll=value=>{finished.push(value);_runAllActive=false;}; _pollRunAllBatch('test'); }""")
    page.wait_for_function("document.querySelector('#sn-execute').classList.contains('running')")
    assert 'visible' in page.locator('#cancel-execute').get_attribute('class')
    page.wait_for_function('finished.length === 1')
    assert page.evaluate('finished') == [False]


def test_report_search_sort_page_preview_newtab_and_delete(controls):
    page = controls
    reports = [{'name': f'report_{n:02}.html', 'modified_at': f'2026-10-{n+1:02}', 'size': 100} for n in range(18)]
    deletes = []
    page.route('**/api/reports', lambda route: route.fulfill(json=reports))
    def delete(route):
        names = route.request.post_data_json['names']
        deletes.append(names)
        reports[:] = [row for row in reports if row['name'] not in names]
        route.fulfill(json={'ok': True})
    page.route('**/api/reports/delete', delete)
    page.evaluate('initReportControls(); refreshReports()')
    assert page.locator('.report-item').count() == 8
    assert page.locator('.report-name').first.inner_text() == 'report_17.html'
    page.locator('#report-next').click()
    assert page.locator('#report-page').inner_text() == '2 / 3'
    page.locator('#report-sort').select_option('name')
    assert page.locator('.report-name').first.inner_text() == 'report_00.html'
    page.locator('#report-search-input').fill('REPORT_1')
    assert page.locator('#report-count').inner_text() == '8개 리포트'
    page.locator('#report-select-all').check()
    assert page.locator('#report-selection-count').inner_text() == '8개 선택'
    page.locator('#report-search-input').fill('')
    assert page.locator('#report-selection-count').inner_text() == '8개 선택'
    page.locator('.report-actions button').filter(has_text='열기').first.click()
    assert page.locator('#report-iframe').get_attribute('src') == '/reports/report_00.html'
    with page.expect_popup() as popup:
        page.locator('.report-actions a').first.click()
    popup.value.wait_for_load_state()
    assert popup.value.url == 'http://controls.test/reports/report_00.html'
    popup.value.close()
    page.locator('#report-delete-selected').click()
    page.locator('.report-delete-dialog button[value=cancel]').click()
    assert deletes == []
    page.locator('#report-delete-selected').click()
    page.locator('.report-delete-dialog button[value=delete]').click()
    page.wait_for_function("document.querySelector('#report-count').textContent==='10개 리포트'")
    assert len(deletes[0]) == 8
    assert page.locator('#report-selection-count').inner_text() == '0개 선택'


def test_evidence_quoted_case_button_selects_exact_case(controls):
    page = controls
    page.evaluate("""() => {
      document.querySelector('#gen-all').innerHTML='<div id="quick-generated-result"></div>';
      _obsRenderWorkspace('example', {entries:[
        {nodeid:'first',attempts:[{n:1,outcome:'passed',kept:false}]},
        {nodeid:"group's-test",attempts:[{n:1,outcome:'passed',kept:false}]}
      ]});
    }""")
    page.locator('.obs-run-case').nth(1).click()
    assert page.evaluate('_obsWorkspace.nodeid') == "group's-test"


def test_skipped_or_unfinished_evidence_is_not_reported_as_passed(controls):
    page = controls
    status = page.evaluate("""() => ['skipped','unknown','passed'].map(outcome => _obsEntryStatus({attempts:[{n:1,outcome}]}))""")
    assert status[0]['label'] == '건너뜀'
    assert status[1]['label'] != '통과'
    assert status[2]['label'] == '통과'


def test_folder_select_and_shared_evidence_policy_controls(controls):
    page = controls
    page.route('**/api/tc-folders?platform=android', lambda route: route.fulfill(json={'folders':['first','second']}))
    page.evaluate("""async () => {
      await refreshTcFolders();
      document.querySelector('#gen-all').innerHTML='<div id="obs-strip-quick"></div>';
      _obsRenderStrips();
    }""")
    assert page.locator('input[name=tc-folder]:checked').count() == 2
    page.get_by_role('button', name='전체 해제', exact=True).click()
    assert page.evaluate('getTcFolders()') == []
    page.get_by_role('button', name='전체 선택', exact=True).click()
    assert page.evaluate('getTcFolders()') == ['first', 'second']
    page.locator('input[name=tc-folder]').first.uncheck()
    assert page.evaluate('getTcFolder()') == 'second'
    page.locator('#obs-strip-pipeline input[value=always]').check()
    assert page.locator('#obs-strip-quick input[value=always]').is_checked()
    assert page.evaluate("localStorage.getItem('qa-native-app.obs-keep')") == 'always'
    page.locator('#obs-strip-quick input[value=on_failure]').check()
    assert page.locator('#obs-strip-pipeline input[value=on_failure]').is_checked()


def test_evidence_pagination_attempt_media_log_presets_and_tc_content(controls):
    page = controls
    page.route('**/api/run_artifacts/example/logcat**', lambda route: route.fulfill(body='10-02 12:00:00.000 1 2 I Example: ready\n10-02 12:00:01.000 1 2 E AndroidRuntime: fatal crash', content_type='text/plain'))
    page.route('**/api/testcase**', lambda route: route.fulfill(json={'ok':True, 'content':'사전 조건: 설정 화면\n기대 결과: 저장됨'}))
    page.evaluate("""() => {
      document.querySelector('#gen-all').innerHTML='<div id="quick-generated-result"></div>';
      const entries=Array.from({length:12},(_,n)=>({nodeid:'tests/generated/android/settings/case'+n+'.py::test',attempts:[
        {n:1,outcome:'failed',kept:true,video:{path:'video.mp4',bytes:100},syslog:{path:'log.txt',bytes:100},screenshot:{path:'shot.png'}},
        {n:2,outcome:'passed',kept:false}]}));
      _obsRenderWorkspace('example',{platform:'android',app_id:'Example',entries});
    }""")
    assert page.locator('.obs-run-case').count() == 10
    page.locator('.obs-case-pager').get_by_role('button', name='다음', exact=True).click()
    assert page.locator('.obs-run-case').count() == 2
    page.locator('.obs-run-case').last.click()
    assert page.locator('.obs-evidence-head .obs-status').inner_text() == 'FLAKY'
    page.locator('[data-obs-attempt="1"]').click()
    assert page.locator('.obs-evidence-video').get_attribute('controls') is not None
    assert 'attempt=1' in page.locator('.obs-evidence-video').get_attribute('src')
    assert page.locator('.obs-evidence-shot').count() == 1
    page.wait_for_function("document.querySelector('#obs-evidence-log').textContent.includes('ready')")
    page.locator('.obs-log-filter[data-preset=error]').click()
    assert 'ready' not in page.locator('#obs-evidence-log').inner_text()
    assert 'fatal crash' in page.locator('#obs-evidence-log').inner_text()
    page.locator('.obs-log-search').fill('no-match')
    assert '일치하는 로그가 없습니다' in page.locator('#obs-evidence-log').inner_text()
    page.locator('.obs-log-search').fill('')
    page.locator('.obs-log-filter[data-preset=all]').click()
    assert 'ready' in page.locator('#obs-evidence-log').inner_text()
    assert '기대 결과: 저장됨' in page.locator('.obs-evidence-section[data-kind=tc]').inner_text()
