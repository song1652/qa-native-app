"""Server history remains authoritative across browser caches and failures."""
import pytest

from tests.dashboard.test_navigation_refresh import navigation_page  # noqa: F401
from tests.dashboard.test_overview_log_refresh import overview_page  # noqa: F401

ENTRIES = [
    {'run_id': 'server-android', 'type': 'quick', 'platform': 'android', 'passed': 2, 'failed': 1, 'total': 3,
     'groups': ['settings'], 'duration': '12s', 'executedAt': '2026-10-02T14:00:00+09:00', 'status': 'failed'},
    {'run_id': 'server-ios', 'type': 'pipeline', 'platform': 'ios', 'passed': 1, 'failed': 0, 'total': 1,
     'groups': ['login'], 'duration': '8s', 'executedAt': '2026-10-02T13:00:00+09:00', 'status': 'passed'},
]


@pytest.fixture
def history_page(navigation_page):
    page = navigation_page
    state = {'entries': [dict(entry) for entry in ENTRIES], 'fail_get': False, 'fail_delete': False, 'calls': []}
    def serve(route):
        method = route.request.method
        state['calls'].append(method)
        failed = state['fail_delete'] if method == 'DELETE' else state['fail_get']
        if method == 'DELETE' and not failed:
            state['entries'] = []
        route.fulfill(status=503 if failed else 200, json={'ok': not failed, 'entries': state['entries'], 'error': 'mock unavailable' if failed else ''})
    page.route('**/api/run-history', serve)
    page.evaluate("localStorage.clear();window.dashboardConfirm=async()=>true;window.alert=message=>window.lastAlert=message")
    return page, state


def open_history(page):
    page.locator('[data-view="history"]').click()
    page.wait_for_function("document.getElementById('history-source-status').textContent.includes('서버에 저장된')")
    page.wait_for_function("document.getElementById('history-total').textContent === '2'")


def test_server_history_populates_empty_browser_and_recalculates_rates(history_page):
    page, state = history_page
    open_history(page)
    assert page.locator('.history-row:not(.header)').count() == 2
    assert page.locator('.history-pass').all_text_contents() == ['67%', '100%']
    assert page.locator('.history-group').all_text_contents() == ['settings', 'login']
    assert page.evaluate("localStorage.getItem('qa-native-app.run-history')") is None
    assert state['calls'] == ['GET']


def test_server_history_does_not_merge_duplicate_or_stale_local_records(history_page):
    page, _ = history_page
    legacy = [dict(ENTRIES[0], rate=99), dict(ENTRIES[1], run_id='obsolete', groups=['stale'])]
    page.evaluate('entries=>localStorage.setItem("qa-native-app.run-history",JSON.stringify(entries))', legacy)
    open_history(page)
    assert page.locator('.history-row:not(.header)').count() == 2
    assert 'stale' not in page.locator('#history-list').inner_text()
    assert page.evaluate('loadRunHistory().map(entry=>entry.run_id)') == ['server-android', 'server-ios']


def test_history_reentry_fetches_latest_server_records(history_page):
    page, state = history_page
    open_history(page)
    state['entries'].insert(0, dict(ENTRIES[1], run_id='new-run', groups=['new-group']))
    page.locator('[data-view="history"]').click()
    page.wait_for_function("document.getElementById('history-total').textContent === '3'")
    assert page.locator('.history-group').first.inner_text() == 'new-group'
    assert state['calls'] == ['GET', 'GET']


def test_history_server_failure_preserves_last_loaded_rows(history_page):
    page, state = history_page
    open_history(page)
    before = page.locator('#history-list').inner_html()
    state['fail_get'] = True
    page.evaluate('refreshRunHistory()')
    assert page.locator('#history-list').inner_html() == before
    assert page.locator('#history-total').inner_text() == '2'
    assert '기존 표시' in page.locator('#history-source-status').inner_text()


def test_first_server_failure_keeps_legacy_browser_fallback(history_page):
    page, state = history_page
    state['fail_get'] = True
    page.evaluate('entry=>localStorage.setItem("qa-native-app.run-history",JSON.stringify([entry]))', dict(ENTRIES[0], rate=67))
    page.locator('[data-view="history"]').click()
    page.wait_for_function("document.getElementById('history-source-status').textContent.includes('기존 표시')")
    assert page.locator('#history-total').inner_text() == '1'
    assert page.locator('.history-group').inner_text() == 'settings'


def test_failed_server_delete_does_not_clear_visible_or_legacy_history(history_page):
    page, state = history_page
    page.evaluate('entries=>localStorage.setItem("qa-native-app.run-history",JSON.stringify(entries))', ENTRIES)
    open_history(page)
    before = page.locator('#history-list').inner_html()
    legacy = page.evaluate("localStorage.getItem('qa-native-app.run-history')")
    state['fail_delete'] = True
    page.get_by_role('button', name='기록 초기화', exact=True).click()
    page.wait_for_function("typeof window.lastAlert === 'string'")
    assert page.locator('#history-list').inner_html() == before
    assert page.evaluate("localStorage.getItem('qa-native-app.run-history')") == legacy
    assert state['calls'][-1] == 'DELETE'


def test_successful_server_delete_clears_history_only_after_confirmation(history_page):
    page, state = history_page
    open_history(page)
    page.evaluate('window.dashboardConfirm=async()=>false')
    page.get_by_role('button', name='기록 초기화', exact=True).click()
    assert state['calls'] == ['GET']
    assert page.locator('#history-total').inner_text() == '2'
    page.evaluate('window.dashboardConfirm=async()=>true')
    page.get_by_role('button', name='기록 초기화', exact=True).click()
    page.wait_for_function("document.getElementById('history-total').textContent === '0'")
    assert page.locator('.history-row:not(.header)').count() == 0
    assert state['calls'][-1] == 'DELETE'
    assert page.evaluate('loadRunHistory()') == []


def test_dashboard_trend_and_summary_use_server_history_without_local_cache(overview_page):
    page = overview_page
    page.evaluate('''entries => {
      localStorage.clear();const original=window.fetch;
      window.fetch=(url,options)=>url==='/api/run-history'
        ?Promise.resolve({ok:true,json:async()=>({ok:true,entries})}):original(url,options);
    }''', ENTRIES)
    page.evaluate('refreshOverview()')
    assert page.locator('#overview-trend tbody tr').count() == 2
    assert page.locator('#overview-trend tbody').inner_text().count('settings') == 1
    assert page.locator('#overview-rate-chart svg').count() == 1
    assert page.locator('#overview-quick-status').inner_text() == '실패 2/3'
    assert page.evaluate("localStorage.getItem('qa-native-app.run-history')") is None
