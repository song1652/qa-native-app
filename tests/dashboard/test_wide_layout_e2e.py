"""Reading and setup screens stay usable on wide desktop monitors."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from playwright.sync_api import sync_playwright

from tests.dashboard.test_tc_studio_e2e import tc_server


@pytest.mark.parametrize('width,height', [(1440, 900), (1920, 1080), (2560, 1440), (3840, 2160)])
def test_desktop_content_widths(tc_server, width, height, tmp_path):
    import _tc_library as lib
    from _tc_model import new_case

    lib.import_cases('wide-layout', ['설정'], [new_case(
        case_id='WIDE_1', sheet='설정', path=['설정', '', ''],
        feature='긴 제목과 본문이 있는 설정 화면 검토',
        steps=['설정 화면을 열고 계정 정보를 확인한다'],
        expected='사용자의 계정 정보와 설정 항목이 표시된다',
    )], 'seed')

    def check():
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': width, 'height': height})
            page.route('**/api/status*', lambda route: route.fulfill(json={
                'appium': False, 'platform': 'android', 'devices': [],
                'running_steps': [], 'capture_active': False,
            }))
            page.route('**/api/env/status', lambda route: route.fulfill(json={}))
            for view, selector in [('dashboard', '#view-overview'),
                                   ('pipeline', '#view-pipeline'),
                                   ('history', '#view-history'),
                                   ('config', '#view-config')]:
                page.goto(f'{tc_server}/?view={view}')
                content = page.locator(selector)
                content.wait_for(state='visible')
                box = content.bounding_box()
                assert box['width'] <= 2001, (view, box)
                limit = 1440 if view == 'history' else 2000
                assert abs(box['width'] - min(width - 296, limit)) <= 1, (view, box)
                assert abs(box['x'] - (264 + max(0, width - 2296) / 2)) <= 1
                assert box['y'] == 84
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                if view == 'dashboard':
                    for selector in ['.overview-heading-row', '.overview-summary', '.overview-columns']:
                        section = page.locator(selector).bounding_box()
                        assert abs(section['x'] - box['x']) <= 1
                        assert abs(section['width'] - min(width - 296, 1440)) <= 1
                page.screenshot(path=str(tmp_path / f'{view}.png'))
            for view, selector in [('tests', '#view-tests'),
                                   ('reports', '#view-reports'),
                                   ('capture', '#view-capture')]:
                page.goto(f'{tc_server}/?view={view}')
                page.locator(selector).wait_for(state='visible')
                box = page.locator(selector).bounding_box()
                limit = 1440 if view == 'reports' else 2000
                assert abs(box['width'] - min(width - 296, limit)) <= 1, (view, box)
                assert abs(box['x'] - (264 + max(0, width - 2296) / 2)) <= 1, (view, box)
                assert box['y'] == 84
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(tmp_path / f'{view}.png'))
            page.goto(f'{tc_server}/tc-studio')
            page.locator('#screen-generate').wait_for(state='visible')
            segments = page.get_by_role('group', name='대상 플랫폼')
            buttons = segments.get_by_role('button')
            sizes = [buttons.nth(i).bounding_box()['width'] for i in range(3)]
            assert max(sizes) - min(sizes) <= 1
            assert buttons.first.evaluate('(el) => getComputedStyle(el).borderRadius') == '0px'
            buttons.nth(1).click()
            assert page.locator('#gen-platforms').input_value() == 'android'
            assert buttons.nth(1).get_attribute('aria-pressed') == 'true'
            header = page.locator('.tc-studio .page-header').bounding_box()
            assert header['width'] <= 1441
            assert abs(header['x'] - (264 + max(0, width - 2296) / 2)) <= 1
            assert header['y'] == 84
            for tab, selector in [('기획 정보 · 생성', '.tc-studio .gen'),
                                  ('라이브러리', '.tc-studio .lib'),
                                  ('초안 검토', '.tc-studio .review'),
                                  ('내보내기', '.tc-studio .exp')]:
                page.get_by_role('tab', name=tab).click()
                content = page.locator(selector)
                content.wait_for(state='visible')
                box = content.bounding_box()
                assert abs(box['x'] - header['x']) <= 1, (tab, header, box)
                limit = 2000 if tab == '라이브러리' else 1440
                assert abs(box['width'] - min(width - 296, limit)) <= 1, (tab, box)
            page.locator('#suite-select').select_option('wide-layout')
            page.get_by_role('tab', name='초안 검토').click()
            page.locator('#screen-review').wait_for(state='visible')
            assert page.locator('.tc-studio .review').bounding_box()['width'] <= 1441
            page.locator('.dcard.focus').wait_for(state='visible')
            assert page.locator('.dcard.focus').bounding_box()['width'] <= 801
            page.screenshot(path=str(tmp_path / 'review.png'))
            page.get_by_role('tab', name='라이브러리').click()
            page.locator('#screen-library').wait_for(state='visible')
            assert page.locator('.tc-studio .lib').bounding_box()['width'] <= 2001
            page.goto(tc_server)
            page.locator('#view-overview').wait_for(state='visible')
            page.locator('#overview-rate-chart').evaluate("""el => {
                el.innerHTML = renderOverviewRateChart([
                    {total: 10, passed: 10, executedAt: '2026-10-11T10:00:00+09:00'},
                    {total: 10, passed: 8, executedAt: '2026-10-11T09:00:00+09:00'},
                    {total: 10, passed: 5, executedAt: '2026-10-11T08:00:00+09:00'}
                ]);
            }""")
            chart_width = page.locator('.overview-rate-svg').bounding_box()['width']
            available = page.locator('#overview-rate-chart').bounding_box()['width']
            assert chart_width >= available * .95
            assert page.locator('.overview-rate-svg').bounding_box()['height'] <= 240
            page.screenshot(path=str(tmp_path / 'overview.png'))
            browser.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(check).result(timeout=60)
