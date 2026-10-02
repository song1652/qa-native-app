"""Standalone report controls keep filters and per-attempt evidence independent."""
from scripts import report_html


def test_report_attempt_selection_does_not_collapse_case(page):
    case = report_html.case_row({
        'title': '설정 확인', 'error': 'NoSuchElementException: 설정',
        'attempts': [{'n': 1}, {'n': 2}],
    }, 'settings_0', 'failed')
    passed = report_html.case_row({'title': '앱 실행'}, 'settings_1', 'passed')
    document = report_html.build_report([{
        'label': 'settings', 'rows_html': case + passed, 'pass_cnt': 1,
        'total_cnt': 2, 'all_pass': False, 'has_tests': True,
    }], {'passed': 1, 'failed': 1}, '2026-10-02', platform='android')
    page.set_content(document)
    page.locator('[data-toggle-group=settings]').click()
    page.locator('[data-toggle=settings_0] .case-header').click()
    page.locator('[data-attempt="1"]').click()
    assert page.locator('#detail_settings_0').is_visible()
    assert page.locator('[data-attempt-panel="1"]').is_visible()
    assert not page.locator('[data-attempt-panel="2"]').is_visible()
    page.get_by_text('전체 오류 보기', exact=True).click()
    assert page.locator('.error-summary pre').is_visible()
    assert page.locator('#detail_settings_0').is_visible()
    page.locator('[data-filter-val=pass]').click()
    assert not page.locator('[data-toggle=settings_0]').is_visible()
    assert page.locator('[data-toggle=settings_1]').is_visible()
    assert 'active' in page.locator('[data-filter-val=pass]').get_attribute('class')
