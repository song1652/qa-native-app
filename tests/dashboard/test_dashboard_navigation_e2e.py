"""Sidebar URLs preserve the selected screen through reload and browser history."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright
from tests.dashboard.test_tc_studio_e2e import tc_server


def test_sidebar_reload_and_history_keep_selected_view(tc_server):
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_check_navigation, tc_server).result(timeout=60)


def _check_navigation(base):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route('**/capture/**', lambda route: route.fulfill(json={'active': False}))
        page.route('**/api/status*', lambda route: route.fulfill(json={
            'appium': False, 'platform': 'android', 'devices': [],
            'running_steps': [], 'capture_active': False,
        }))
        page.route('**/api/env/status', lambda route: route.fulfill(json={}))
        page.goto(base + '/tc-studio')
        page.locator('#tc-studio-root .page-title').wait_for()
        page.locator('[data-view=capture]').click()
        page.wait_for_function("location.search.includes('view=capture')")
        page.locator('[data-view=dashboard]').click()
        page.reload()
        assert page.locator('#view-overview').is_visible()
        assert not page.locator('#view-capture').is_visible()
        assert urlparse(page.url).path == '/'
        assert 'view' not in parse_qs(urlparse(page.url).query)

        page.goto(base + '/?view=pipeline&platform=ios&tc_folder=settings#anchor')
        page.locator('[data-view=history]').click()
        query = parse_qs(urlparse(page.url).query)
        assert query == {'view': ['history'], 'platform': ['ios'], 'tc_folder': ['settings']}
        assert urlparse(page.url).fragment == 'anchor'
        page.locator('[data-view=dashboard]').click()
        length = page.evaluate('history.length')
        page.go_back()
        assert page.locator('#view-history').is_visible()
        page.go_forward()
        assert page.locator('#view-overview').is_visible()
        assert page.evaluate('history.length') == length
        page.locator('[data-view=dashboard]').click()
        assert page.evaluate('history.length') == length
        page.reload()
        assert page.locator('#view-overview').is_visible()
        assert parse_qs(urlparse(page.url).query) == {'platform': ['ios'], 'tc_folder': ['settings']}
        browser.close()
