"""Compact rate chart follows the reference without inventing test outcomes."""
from tests.dashboard.test_overview_log_refresh import overview_page  # noqa: F401
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_reference_chart_has_six_grid_lines_and_labeled_colored_points(overview_page):
    page = overview_page
    page.add_style_tag(path=str(ROOT / 'agents/dashboard/static/tokens.css'))
    page.add_style_tag(path=str(ROOT / 'agents/dashboard/static/dashboard.css'))
    rates = [100, 0, 0, 100, 100]
    entries = [{'passed': rate, 'total': 100, 'failed': 100-rate, 'status': 'passed' if rate else 'failed',
                'executedAt': f'2026-10-03T10:{49+i:02d}:00+09:00'} for i, rate in enumerate(rates)]
    page.evaluate('entries => document.body.innerHTML = renderOverviewRateChart(entries.slice().reverse())', entries)
    assert page.locator('.overview-chart-grid').count() == 6
    assert page.locator('.overview-chart-grid').last.get_attribute('y1') == '112'
    assert page.locator('.overview-chart-point > text:first-of-type').all_text_contents() == ['100%', '0%', '0%', '100%', '100%']
    assert page.locator('.overview-chart-time').all_text_contents() == ['10:49', '10:50', '10:51', '10:52', '10:53']
    assert page.locator('.overview-chart-point.pass circle').count() == 3
    assert page.locator('.overview-chart-point.fail circle').count() == 2
    assert page.locator('.overview-chart-line').get_attribute('points') == '40,32 140,112 240,112 340,32 440,32'
    style = page.locator('.overview-chart-point circle').first.evaluate('(el) => {const s=getComputedStyle(el);return {stroke:s.stroke,strokeWidth:s.strokeWidth,r:el.getAttribute("r")};}')
    assert style['stroke'] == 'rgb(255, 255, 255)'
    assert style['strokeWidth'] == '1.5px'
    assert style['r'] == '3.5'


def test_single_point_has_no_fake_line_and_missing_outcomes_stay_empty(overview_page):
    page = overview_page
    page.evaluate('document.body.innerHTML = renderOverviewRateChart([{passed:1,total:1,status:"passed",executedAt:"2026-10-03T10:49:00+09:00"}])')
    assert page.locator('.overview-chart-point circle').count() == 1
    assert page.locator('.overview-chart-line').count() == 0
    page.evaluate('document.body.innerHTML = renderOverviewRateChart([{passed:0,total:0,status:"failed"}])')
    assert page.locator('.overview-chart-empty').count() == 1
