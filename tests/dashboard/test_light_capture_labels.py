"""Capture status and locator confidence remain readable without color or icons."""
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / 'agents/dashboard/static'


def test_livetail_shows_source_and_result_text(page):
    page.set_content('<div id="csLtRows"></div>')
    page.evaluate("""() => {
        window._csLtRows = [];
        window._csLtOpen = true;
        window._csLtPinned = false;
        window._csLtFilters = {user: true, mcp: true, pipe: true};
    }""")
    page.add_script_tag(path=str(STATIC / 'capture-livetail.js'))
    page.evaluate("""() => {
        csLtAppend('user', 'tap', 'android', '설정', 'ok', '10ms');
        csLtAppend('mcp', 'find', 'android', '설정', 'warn', '20ms');
        csLtAppend('pipeline', 'assert', 'android', '설정', 'error', '30ms');
    }""")
    assert page.locator('.lt-ov-r').all_text_contents() == ['성공 10ms', '주의 20ms', '실패 30ms']
    assert page.locator('.lt-ov-ic').all_text_contents() == ['사용자', 'MCP', '실행']
    assert page.evaluate('_csLtRows.map(row => row.result)') == ['ok', 'warn', 'error']


def test_locator_confidence_keeps_rating_and_approval(page):
    page.set_content('<div id="locators"></div>')
    page.evaluate("""() => {
        window._cs = {approvedLocators: []};
        window.esc = value => {
            const span = document.createElement('span');
            span.textContent = value;
            return span.innerHTML;
        };
    }""")
    page.add_script_tag(path=str(STATIC / 'capture-inspector.js'))
    page.evaluate("""() => {
        document.querySelector('#locators').innerHTML = csRenderLocatorCards({
            'resource-id': 'app:id/settings', 'content-desc': '설정',
            'text': '설정', 'class': 'android.widget.Button'
        });
    }""")
    assert page.locator('.cs-loc-stars').all_text_contents() == ['5 / 5', '4 / 5', '3 / 5', '1 / 5']
    page.locator('.cs-loc-card').first.get_by_role('button', name='승인 ✓', exact=True).click()
    assert page.evaluate('_cs.approvedLocators') == [
        {'strategy': 'resource-id', 'value': 'app:id/settings', 'rating': 5}
    ]
    assert page.get_by_role('button', name='승인됨 ✓', exact=True).is_disabled()
