"""Dashboard mockup data and filters must not change execution state."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_overview_matches_mockup_and_filters_only_display(page):
    document = (ROOT / 'agents/dashboard/dashboard.html').read_text()
    document = re.sub(r'<script\b[^>]*>.*?</script>', '', document, flags=re.S)
    document = re.sub(r'<link\b[^>]*>', '', document)
    page.route('http://overview.test/', lambda route: route.fulfill(body=document, content_type='text/html'))
    page.goto('http://overview.test/')
    history = [dict(type='pipeline', platform='ios' if i % 2 == 0 else 'android',
                    total=1, passed=1 if i % 2 == 0 else 0, failed=0 if i % 2 == 0 else 1,
                    rate=100 if i % 2 == 0 else 0, healCount=0,
                    executedAt=f'2026-10-02T09:{59-i:02d}:00Z', duration='29s')
               for i in range(12)]
    saved = json.dumps(history)
    page.evaluate("value => localStorage.setItem('qa-native-app.run-history', value)", saved)
    page.evaluate("""() => {
      window.esc = value => { const el=document.createElement('span');el.textContent=value;return el.innerHTML; };
      window.requests = [];
      window.fetch = async (url, options) => {
        requests.push(url);
        const payloads = {
          '/api/state': {platform:'android',heal_count:0},
          '/api/status': {appium:true,platform:'android',devices:['emulator-5554','device-123']},
          '/api/generated': [{platform:'android',count:3},{platform:'ios',count:2}],
          '/api/run_log': {log:'검증용 로그'}
        };
        return {json:async()=>payloads[url] || {}};
      };
    }""")
    page.add_script_tag(path=str(ROOT / 'agents/dashboard/static/dashboard-shell.js'))
    page.evaluate('refreshOverview()')
    assert page.locator('#overview-history-rate').inner_text() == '50%'
    assert page.locator('.overview-history-table th').all_text_contents() == ['시작', '종류', '대상', '결과', '통과', '소요']
    assert page.locator('.overview-history-table tbody tr').count() == 8
    first = page.locator('.overview-history-table tbody tr').first.locator('td')
    assert first.nth(2).inner_text() == '—'
    assert first.nth(5).inner_text() == '29초'
    assert first.nth(4).inner_text() == '1/1'
    assert page.locator('.overview-chart-point circle').count() == 10
    assert page.locator('.overview-chart-line').count() == 1
    assert '100%' in page.locator('.overview-rate-svg').get_attribute('aria-label')
    assert '0%' in page.locator('.overview-rate-svg').get_attribute('aria-label')
    requests_before = page.evaluate('requests.length')
    page.locator('.overview-filter-menu summary').click()
    page.get_by_role('group', name='플랫폼', exact=True).get_by_role('button', name='iOS', exact=True).click()
    assert page.locator('#overview-history-rate').inner_text() == '100%'
    assert page.locator('.overview-history-table tbody tr').count() == 6
    assert page.locator('.overview-history-table tbody tr[data-platform=ios]').count() == 6
    assert page.locator('.overview-chart-point circle').count() == 6
    assert page.evaluate('getPlatform()') == 'android'
    assert page.evaluate("localStorage.getItem('qa-native-app.run-history')") == saved
    assert page.evaluate('requests.length') == requests_before

    # A single recorded run is a single point, never an invented flat trend.
    single = [dict(type='quick', platform='android', total=4, passed=4, failed=0,
                   rate=100, healCount=0, duration='11s',
                   groups=['settings', 'location'], executedAt='2026-10-01T09:43:58Z')]
    page.evaluate("value => localStorage.setItem('qa-native-app.run-history', JSON.stringify(value))", single)
    page.evaluate("setOverviewPlatform('all')")
    assert page.locator('.overview-chart-point circle').count() == 1
    assert page.locator('.overview-chart-line').count() == 0
    assert page.locator('#overview-history-rate').inner_text() == '100%'
    assert page.locator('#overview-history-count').inner_text() == '통과 4 · 전체 4'
    assert page.locator('.overview-history-table tbody tr td:nth-child(3)').inner_text() == 'settings · location'
    assert page.locator('#overview-last-detail').inner_text().endswith('11초')
    page.evaluate("localStorage.setItem('qa-native-app.run-history', '[]'); setOverviewPlatform('all')")
    assert page.locator('.overview-chart-point').count() == 0
    assert page.locator('.overview-chart-empty').inner_text() == '실행 이력이 쌓이면 통과율 추이가 표시됩니다.'
    assert page.locator('#overview-history-rate').inner_text() == '—'
    assert page.evaluate('getPlatform()') == 'android'
    assert page.evaluate('requests.length') == requests_before

    # Environment comes from the existing poll result, including the other platform.
    page.evaluate("""renderOverviewEnvironment({
        appium:{status:'managed',port:4723},
        android:{status:'running',serial:'emulator-5554',avd:'Pixel',
                 real_devices:[{deviceName:'Lenovo TB320FC',connected:true}]},
        ios:{status:'running',simulator:'iPhone 17'}
    })""")
    assert page.locator('.overview-env-card').is_visible()
    assert page.locator('#overview-appium').inner_text() == '연결됨 · 127.0.0.1:4723'
    assert page.locator('#overview-android-emulator').inner_text() == 'emulator-5554'
    assert page.locator('#overview-android-real').inner_text() == 'Lenovo TB320FC'
    assert page.locator('#overview-ios').inner_text() == 'iPhone 17'
    assert page.evaluate('requests.length') == requests_before
