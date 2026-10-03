"""Recovery UI uses mocked browser reads; no dashboard server or devices."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'agents/dashboard/static'
NOTICE = dict(id='run-timeout', title='실행 시간 초과', message='실행 기록을 확인하세요.',
              action_label='실행 기록 보기', href='/?view=history', severity='warning',
              created_at='2026-10-03T00:00:00Z', category='timeout')


def test_notice_ui_is_loaded_by_dashboard():
    document = (ROOT / 'agents/dashboard/dashboard.html').read_text()
    assert '/static/recovery-notices.js' in document
    assert 'id="recovery-notices"' in document


@pytest.fixture
def notices_page(page):
    document = (ROOT / 'agents/dashboard/dashboard.html').read_text()
    document = re.sub(r'<script\b[^>]*>.*?</script>|<link\b[^>]*>', '', document, flags=re.S)
    page.route('http://notices.test/', lambda route: route.fulfill(body=document, content_type='text/html'))
    page.goto('http://notices.test/')
    page.clock.install()
    page.evaluate('''() => {
      window.requests=[];window.responses=[{ok:true,notices:[]}];
      window.fetch=async(url, options={})=>{
        requests.push({url,method:options.method||'GET'});
        const next=responses.length>1?responses.shift():responses[0];
        if(next==='network') throw new TypeError('offline');
        return {ok:!next.status,status:next.status||200,json:async()=>next};
      };
    }''')
    script = STATIC / 'recovery-notices.js'
    assert script.exists(), 'Recovery notice UI and bounded GET helper are missing'
    page.add_script_tag(path=str(script))
    page.wait_for_function('requests.length === 1')
    return page


def refresh(page, notices):
    page.evaluate('notices=>{responses=[{ok:true,notices}];}', notices)
    page.evaluate('recoveryNoticesRefresh()')


def test_notices_are_deduplicated_accessible_and_acknowledged_per_browser(notices_page):
    page = notices_page
    assert not page.locator('#recovery-notices').is_visible()
    refresh(page, [NOTICE, NOTICE])
    summary = page.locator('#recovery-notices summary')
    assert summary.inner_text() == '알림 1'
    summary.focus()
    page.keyboard.press('Enter')
    assert page.get_by_role('link', name='실행 기록 보기').get_attribute('href') == '/?view=history'
    assert page.locator('#recovery-announcement').inner_text() == '새 알림 1개가 있습니다.'
    page.evaluate("document.querySelector('#recovery-announcement').textContent='유지'")
    refresh(page, [NOTICE])
    assert page.locator('#recovery-announcement').inner_text() == '유지'
    page.get_by_role('button', name='확인했어요').click()
    refresh(page, [NOTICE])
    assert not page.locator('#recovery-notices').is_visible()
    assert page.evaluate('JSON.parse(localStorage.getItem("qa-native-app.recovery-acknowledged"))') == ['run-timeout']
    assert {request['method'] for request in page.evaluate('requests')} == {'GET'}


def test_exhausted_read_keeps_notices_and_visible_warning_until_restored(notices_page):
    page = notices_page
    refresh(page, [NOTICE])
    page.evaluate("responses=['network'];window.pending=recoveryNoticesRefresh()")
    page.clock.run_for(1600)
    page.evaluate('pending')
    assert page.locator('#recovery-connection-warning').is_visible()
    assert '서버 연결' in page.locator('#recovery-connection-warning').inner_text()
    page.locator('#recovery-notices summary').click()
    assert page.get_by_role('link', name='실행 기록 보기').count() == 1
    assert len(page.evaluate('requests')) == 5  # startup + success + three attempts
    refresh(page, [NOTICE])
    assert not page.locator('#recovery-connection-warning').is_visible()
    assert page.locator('#recovery-announcement').inner_text() == '서버 연결이 복구되었습니다.'


def test_only_temporary_get_failures_are_retried(notices_page):
    page = notices_page
    page.evaluate("responses=[{status:502},{status:503},{ok:true,notices:[]}];window.pending=recoveryNoticesRefresh()")
    page.clock.run_for(1600)
    page.evaluate('pending')
    assert len(page.evaluate('requests')) == 4
    page.evaluate("responses=[{status:403}];recoveryNoticesRefresh()")
    assert len(page.evaluate('requests')) == 5
    assert page.evaluate("async()=>{try{await safeNoticeGet('/api/recovery-notices',{method:'POST'});}catch(e){return e.message;}}")
    assert page.evaluate("async()=>{try{await safeNoticeGet('/capture/launch');}catch(e){return e.message;}}")
    assert len(page.evaluate('requests')) == 5


def test_poll_and_read_timeout_are_bounded_without_overlap(notices_page):
    page = notices_page
    page.evaluate('''() => {
      fetch=(url, options)=>new Promise((resolve,reject)=>{
        requests.push({url});options.signal.addEventListener('abort',()=>reject(new DOMException('timeout','AbortError')));
      });
      window.pending=recoveryNoticesRefresh();recoveryNoticesRefresh();
    }''')
    page.clock.run_for(16500)
    page.evaluate('pending')
    assert len(page.evaluate('requests')) == 4
    assert page.locator('#recovery-connection-warning').is_visible()


def test_notice_text_and_links_cannot_inject_markup(notices_page):
    page = notices_page
    refresh(page, [dict(NOTICE, title='<img src=x onerror=alert(1)>', href='javascript:alert(1)')])
    page.locator('#recovery-notices summary').click()
    assert page.locator('#recovery-notice-list img').count() == 0
    assert page.locator('#recovery-notice-list a').count() == 0
    assert '<img' in page.locator('#recovery-notice-list').inner_text()


def test_unchanged_notice_poll_preserves_keyboard_focus(notices_page):
    page = notices_page
    refresh(page, [NOTICE])
    page.locator('#recovery-notices summary').click()
    page.get_by_role('button', name='확인했어요').focus()
    refresh(page, [NOTICE])
    assert page.evaluate('document.activeElement.textContent') == '확인했어요'


def test_notice_context_identifies_platform_groups_and_local_time(notices_page):
    page = notices_page
    notice = dict(NOTICE, platform='ios', groups=['설정', '<b>검색</b>'], run_id='raw_long_internal_run_id')
    refresh(page, [notice])
    page.locator('#recovery-notices summary').click()
    context = page.locator('.recovery-notice-context')
    assert context.count() == 1
    assert 'iOS · 설정, <b>검색</b>' in context.inner_text()
    assert context.locator('b').count() == 0
    timestamp = context.locator('time')
    assert timestamp.get_attribute('datetime') == NOTICE['created_at']
    expected = page.evaluate("date=>new Date(date).toLocaleString('ko-KR',{year:'numeric',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})", NOTICE['created_at'])
    assert timestamp.inner_text() == expected
    assert 'raw_long_internal_run_id' not in page.locator('#recovery-notice-list').inner_text()
    page.get_by_role('button', name='확인했어요').focus()
    refresh(page, [dict(notice, groups=['설정', '검색'])])
    assert page.evaluate('document.activeElement.textContent') == '확인했어요'


def test_unknown_notice_context_omits_invalid_time_and_platform(notices_page):
    page = notices_page
    refresh(page, [dict(NOTICE, created_at='not-a-date', platform='unknown', groups=[None, 4, ''])])
    page.locator('#recovery-notices summary').click()
    assert page.locator('.recovery-notice-context time').count() == 0
    assert page.locator('.recovery-notice-context').count() == 0


@pytest.fixture
def capture_page(page):
    page.set_content('''<img id="cs-mirror-img"><div id="cs-mirror-placeholder"></div>
        <p id="cs-save-status"></p><div id="cs-hierarchy-tree"></div>''')
    page.clock.install()
    page.add_script_tag(path=str(STATIC / 'capture-studio.js'))
    page.evaluate('''() => {
      _cs.sessionId='draft-session';_cs.screenshotMode='poll';_cs.actions=[{type:'tap',value:'draft'}];
      window.csSubStatusConn=()=>{};window.requests=[];
      fetch=(url,options={})=>new Promise((resolve,reject)=>{
        requests.push({url,options});window.finishRead=resolve;
        if(options.signal) options.signal.addEventListener('abort',()=>reject(new DOMException('timeout','AbortError')));
      });
    }''')
    return page


def test_capture_screenshot_poll_does_not_overlap_and_times_out_without_relaunch(capture_page):
    page = capture_page
    page.evaluate('csMirrorConnect()')
    page.clock.run_for(19000)
    assert page.evaluate('requests.length') == 1
    page.clock.run_for(1000)
    page.clock.run_for(1200)
    assert page.evaluate('requests.length') == 2
    assert page.evaluate('requests.map(r=>r.url)') == ['/capture/screenshot', '/capture/screenshot']
    assert page.evaluate('_cs.actions') == [{'type': 'tap', 'value': 'draft'}]


def test_capture_failure_uses_recovery_message_and_explicit_action(capture_page):
    page = capture_page
    page.evaluate('csMirrorConnect()')
    page.evaluate('''async() => {
      finishRead({json:async()=>({ok:false,reconnect_required:true,
        recovery:{message:'같은 기기에 다시 연결하세요.',action:'reconnect_capture'}})});
      await Promise.resolve();
    }''')
    assert '같은 기기에 다시 연결하세요.' in page.locator('#cs-save-status').inner_text()
    assert page.get_by_role('button', name='세션 재연결').is_visible()
    page.clock.run_for(5000)
    assert page.evaluate('requests.length') == 1
    assert page.evaluate('_cs.actions') == [{'type': 'tap', 'value': 'draft'}]


def test_capture_liveness_read_shares_pending_request_and_twenty_second_budget(capture_page):
    page = capture_page
    page.evaluate('''() => {
      window.results=[];
      csDriverAlive().catch(error=>results.push(error.name));
      csDriverAlive().catch(error=>results.push(error.name));
    }''')
    assert page.evaluate('requests.length') == 1
    page.clock.run_for(19000)
    assert page.evaluate('results') == []
    page.clock.run_for(1000)
    assert page.evaluate('results') == ['AbortError', 'AbortError']
    assert page.evaluate('requests.length') == 1


def test_capture_deadline_covers_json_body_after_response_headers(capture_page):
    page = capture_page
    page.evaluate('''() => {
      window.results=[];
      fetch=async(url, options)=>{
        requests.push({url});
        return {json:()=>new Promise((resolve,reject)=>{
          options.signal.addEventListener('abort',()=>reject(new DOMException('timeout','AbortError')));
        })};
      };
      csDriverAlive().catch(error=>results.push(error.name));
    }''')
    page.clock.run_for(19000)
    assert page.evaluate('results') == []
    page.clock.run_for(1000)
    assert page.evaluate('results') == ['AbortError']
    assert page.evaluate('requests.length') == 1


def test_launch_failure_uses_environment_recovery_without_automatic_retry(capture_page):
    page = capture_page
    page.evaluate('csReLaunch()')
    page.evaluate('''async() => {
      finishRead({json:async()=>({ok:false,error:'original evidence',
        recovery:{message:'Appium 서버 상태를 확인하세요.',action:'check_environment'}})});
      await Promise.resolve();
    }''')
    assert page.locator('#cs-save-status').inner_text() == 'Appium 서버 상태를 확인하세요.'
    assert page.get_by_role('link', name='환경 설정 확인').get_attribute('href') == '/?view=config'
    assert page.get_by_role('button', name='세션 재연결').count() == 0
    page.clock.run_for(5000)
    assert page.evaluate('requests.map(r=>r.url)') == ['/capture/launch']
