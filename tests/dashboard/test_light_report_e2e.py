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
    assert page.locator('[data-toggle-group=settings]').get_attribute('aria-expanded') == 'true'
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
    assert page.locator('#gbody_settings').is_visible()
    assert page.locator('.group-card > .filter-bar [data-filter-val=pass]').is_visible()
    page.locator('[data-filter-val=all]').click()
    assert page.locator('#gbody_settings').is_visible()
    assert page.locator('[data-toggle=settings_0]').is_visible()
    page.locator('[data-toggle-group=settings]').click()
    assert not page.locator('#gbody_settings').is_visible()


def test_report_navigation_stats_and_filters_follow_reference_layout(page):
    case = report_html.case_row({'title': '설정 화면 저장 결과 확인'}, 'settings_0', 'passed')
    document = report_html.build_report([{
        'label': 'settings', 'rows_html': case, 'pass_cnt': 1,
        'total_cnt': 1, 'all_pass': True, 'has_tests': True,
    }], {'passed': 1, 'failed': 0}, '2026-10-02', platform='android')
    for width in [1440, 1024, 856, 768, 390]:
        page.set_viewport_size({'width': width, 'height': 1000})
        page.set_content(document)
        assert page.locator('#gbody_settings').is_visible()
        assert page.locator('.report-actions').count() == 0
        nav = page.locator('.sidebar').bounding_box()
        heading = page.locator('.topbar').bounding_box()
        stats = page.locator('.stats').bounding_box()
        group = page.locator('.group-header').bounding_box()
        filters = page.locator('.filter-bar').bounding_box()
        assert nav['y'] + nav['height'] <= heading['y']
        assert heading['y'] + heading['height'] <= stats['y']
        assert group['y'] + group['height'] <= filters['y']
        cards = page.locator('.stat-card').all()
        assert len({round(card.bounding_box()['y']) for card in cards}) == 1
        assert page.evaluate('document.documentElement.scrollWidth') == width
        for control in page.locator('.fbtn,.report-actions a,.report-actions button').all():
            box = control.bounding_box()
            assert box['x'] >= 0 and box['x'] + box['width'] <= width
        page.locator('[data-toggle-group=settings]').focus()
        page.keyboard.press('Space')
        assert not page.locator('#gbody_settings').is_visible()
        page.keyboard.press('Enter')
        assert page.locator('#gbody_settings').is_visible()
