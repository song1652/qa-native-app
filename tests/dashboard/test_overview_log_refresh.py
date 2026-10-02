"""Recent-log controls use live server data without overlapping polls."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'agents/dashboard/static'


@pytest.fixture
def overview_page(page):
    document = (ROOT / 'agents/dashboard/dashboard.html').read_text()
    document = re.sub(r'<script\b[^>]*>.*?</script>', '', document, flags=re.S)
    document = re.sub(r'<link\b[^>]*>', '', document)
    page.route('http://overview-controls.test/', lambda route: route.fulfill(body=document, content_type='text/html'))
    page.goto('http://overview-controls.test/')
    page.evaluate("""() => {
      window.esc = value => {const el=document.createElement('span');el.textContent=value;return el.innerHTML;};
      window.logs={'run_execute.txt':'pipeline first','run_test_ios_settings.txt':'quick first'};
      window.requests=[];window.rejectLog=false;
      window.fetch=async (url,options) => {
        requests.push({url,body:options&&options.body});
        if(url==='/api/run_log'){
          if(rejectLog)return {ok:false,json:async()=>({ok:false})};
          return {ok:true,json:async()=>({ok:true,log:logs[JSON.parse(options.body).log]||''})};
        }
        const values={'/api/state':{},'/api/status':{},'/api/generated':[]};
        return {ok:true,json:async()=>values[url]||{}};
      };
    }""")
    page.add_script_tag(path=str(STATIC / 'dashboard-shell.js'))
    return page


def seed_quick(page, active=False, filename=True):
    page.evaluate("""options => {
      localStorage.setItem('qa-native-app.quick-summary.ios',JSON.stringify({platform:'ios',total:1,passed:1,executedAt:'2026-10-02T10:00:00Z'}));
      localStorage.setItem('qa-native-app.quick-log.ios','stale browser log');
      if(options.active)localStorage.setItem('qa-native-app.quick-active.ios',JSON.stringify({platform:'ios',total:1,startedAt:'2026-10-02T11:00:00Z'}));
      if(options.filename)localStorage.setItem('qa-native-app.quick-log-name.ios','run_test_ios_settings.txt');
    }""", {'active': active, 'filename': filename})


def test_refresh_button_reads_new_pipeline_and_quick_logs(overview_page):
    page=overview_page
    page.evaluate('refreshOverview()')
    assert page.locator('#overview-log').inner_text()=='pipeline first'
    page.evaluate("logs['run_execute.txt']='pipeline updated'")
    page.locator('#overview-log-refresh').click()
    page.wait_for_function("document.querySelector('#overview-log').textContent==='pipeline updated'")
    seed_quick(page)
    page.locator('[data-overview-log=quick]').click()
    page.wait_for_function("document.querySelector('#overview-log').textContent==='quick first'")
    page.evaluate("logs['run_test_ios_settings.txt']='quick updated'")
    page.locator('#overview-log-refresh').click()
    page.wait_for_function("document.querySelector('#overview-log').textContent==='quick updated'")
    assert '로그 갱신 완료' in page.locator('#overview-log-refresh-status').inner_text()
    assert page.locator('#overview-log-refresh').is_enabled()


def test_active_quick_does_not_override_selected_pipeline_and_failures_are_visible(overview_page):
    page=overview_page
    seed_quick(page,active=True)
    page.evaluate('refreshOverview()')
    assert page.locator('#overview-log').inner_text()=='pipeline first'
    assert page.locator('[data-overview-log=pipeline]').get_attribute('class').endswith('active')
    page.evaluate('rejectLog=true')
    page.locator('#overview-log-refresh').click()
    page.wait_for_function("document.querySelector('#overview-log-refresh-status').textContent.includes('실패')")
    assert page.locator('#overview-log-refresh').is_enabled()
    assert page.locator('#overview-log').inner_text()=='pipeline first'


def test_slow_poll_coalesces_and_tab_switch_ignores_old_response(overview_page):
    page=overview_page
    seed_quick(page)
    page.evaluate("""() => {
      const original=fetch;
      window.fetch=(url,options)=>url==='/api/run_log'&&JSON.parse(options.body).log==='run_execute.txt'
        ?new Promise(resolve=>window.finishPipeline=()=>resolve({ok:true,json:async()=>({ok:true,log:'late pipeline'})}))
        :original(url,options);
      window.firstRefresh=refreshOverview();
    }""")
    page.evaluate('refreshOverview()')
    assert page.evaluate('_overviewRefreshId')==1
    assert page.locator('#overview-log-refresh').is_disabled()
    page.locator('[data-overview-log=quick]').click()
    page.wait_for_function("document.querySelector('#overview-log').textContent==='quick first'")
    page.evaluate('async()=>{finishPipeline();await firstRefresh;}')
    assert page.locator('#overview-log').inner_text()=='quick first'
    assert page.locator('#overview-log-refresh').is_enabled()
    # Repeated same-tab polling must eventually apply a slow response.
    page.evaluate("() => {setOverviewLog('pipeline');refreshOverview();refreshOverview();}")
    page.evaluate('finishPipeline()')
    page.wait_for_function("document.querySelector('#overview-log').textContent==='late pipeline'")
    assert page.locator('#overview-log-refresh').is_enabled()


def test_legacy_quick_history_resolves_last_group_and_cache_is_labeled(overview_page):
    page=overview_page
    seed_quick(page,filename=False)
    page.evaluate("localStorage.setItem('qa-native-app.run-history',JSON.stringify([{type:'quick',platform:'ios',groups:['login','settings']}]))")
    page.evaluate("_overviewLogMode='quick';refreshOverview()")
    assert page.locator('#overview-log').inner_text()=='quick first'
    page.evaluate("localStorage.removeItem('qa-native-app.run-history');refreshOverview()")
    assert page.locator('#overview-log').inner_text()=='stale browser log'
    assert '저장된 로그' in page.locator('#overview-log-refresh-status').inner_text()


def test_quick_execution_saves_server_log_reference_and_live_content(overview_page):
    page=overview_page
    page.add_script_tag(path=str(STATIC / 'quick-run.js'))
    page.evaluate("""() => {
      window._obsKeep='on_failure';window.getSelectedDeviceParams=()=>({});
      window.refreshStatus=()=>{};window.refreshReports=()=>{};window._quickRunActive=true;
      window.setInterval=fn=>{window.pollQuick=fn;return 1;};window.clearInterval=()=>{};
      const original=fetch;
      window.fetch=(url,options)=>url==='/api/run_test'
        ?Promise.resolve({ok:true,json:async()=>({ok:true,log:'run_test_ios_settings.txt'})})
        :original(url,options);
      window.quickPromise=executeGeneratedFolder('ios','settings',false);
    }""")
    page.wait_for_function("localStorage.getItem('qa-native-app.quick-log-name.ios')==='run_test_ios_settings.txt'")
    page.evaluate('pollQuick()')
    assert page.evaluate("localStorage.getItem('qa-native-app.quick-live-log.ios')")=='quick first'


def test_dashboard_reset_cancel_and_confirm_keep_actions_separate(overview_page):
    page=overview_page
    seed_quick(page)
    page.evaluate("""() => {
      localStorage.setItem('qa-native-app.run-history',JSON.stringify([{type:'quick',platform:'ios',total:1,passed:1,rate:100}]));
      window._runAllActive=false;
      const original=fetch;
      window.fetch=(url,options)=>(url==='/api/reset'||url==='/api/run-history')
        ?(requests.push({url,method:options&&options.method}),Promise.resolve({ok:true,json:async()=>({ok:true,entries:[]})}))
        :original(url,options);
    }""")
    page.locator('#overview-reset-btn').click()
    page.locator('.ui-confirm').get_by_role('button',name='취소',exact=True).click()
    assert page.evaluate("requests.filter(r=>r.url==='/api/reset').length")==0
    assert page.evaluate("localStorage.getItem('qa-native-app.quick-log-name.ios')")
    page.locator('#overview-reset-btn').click()
    page.locator('.ui-confirm').get_by_role('button',name='확인',exact=True).click()
    page.wait_for_function("localStorage.getItem('qa-native-app.run-history')===null")
    assert page.evaluate("requests.filter(r=>r.url==='/api/reset').length")==1
    assert page.evaluate("requests.filter(r=>r.url==='/api/run-history'&&r.method==='DELETE').length")==1
    assert page.evaluate("localStorage.getItem('qa-native-app.quick-log-name.ios')") is None
    assert page.locator('#overview-reset-btn').is_enabled()
