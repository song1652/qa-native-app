"""Report row shortcuts must not swallow keyboard actions on its action buttons."""
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / 'agents/dashboard/static'


def test_report_actions_and_row_are_independently_keyboard_operable(page):
    page.set_content('''<div id="report-list"></div><span id="report-count"></span>
        <span id="report-selection-count"></span><span id="report-page"></span>
        <button id="report-delete-selected"></button><button id="report-prev"></button><button id="report-next"></button>
        <input type="checkbox" id="report-select-all">''')
    page.evaluate('''() => {
        window.esc = value => {const el=document.createElement('span');el.textContent=value;return el.innerHTML;};
        window.openedReports=[];window.deletedReports=[];
    }''')
    page.add_script_tag(path=str(STATIC / 'reports.js'))
    page.evaluate('''() => {
        // Observe UI intent only; this test never issues a delete request.
        window.showReport = name => openedReports.push(name);
        window.deleteReports = names => deletedReports.push(names);
        _reports=[{name:'report_android_example.html',modified_at:'2026-10-02',size:1024}];
        renderReports();
    }''')
    row = page.locator('.report-item')
    actions = row.locator('.report-actions')
    actions.get_by_role('button', name='열기', exact=True).focus()
    assert page.evaluate('openedReports') == []
    page.keyboard.press('Enter')
    assert page.evaluate('openedReports') == ['report_android_example.html']
    actions.get_by_role('button', name='삭제', exact=True).focus()
    page.keyboard.press('Enter')
    assert page.evaluate('deletedReports') == [['report_android_example.html']]
    assert page.evaluate('openedReports.length') == 1
    actions.get_by_role('button', name='삭제', exact=True).press('Space')
    assert page.evaluate('deletedReports.length') == 2
    assert page.evaluate('openedReports.length') == 1
    row.focus()
    row.press('Enter')
    assert page.evaluate('openedReports') == ['report_android_example.html'] * 2
