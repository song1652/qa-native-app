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


def test_capture_preview_keeps_save_disabled_and_draft_text(page):
    page.set_content('''<input id="cs-tc-id" value="tc_settings"><input id="cs-tc-title" value="설정 확인">
        <select id="cs-platform"><option value="android">Android</option></select><input id="cs-group" value="settings">
        <button id="cs-save-btn" disabled>저장</button><div id="cs-preview-modal" style="display:none">
        <pre id="cs-preview-md"></pre><pre id="cs-preview-py"></pre><div id="cs-preview-source"></div>
        <button id="cs-preview-save">저장 및 생성</button></div>''')
    page.evaluate("window._cs={actions:[{action:'tap',target_ref:'설정'}]}")
    page.add_script_tag(path=str(STATIC / 'capture-actions.js'))
    page.evaluate('csPreviewTC()')
    assert page.locator('#cs-preview-modal').is_visible()
    assert page.locator('#cs-preview-save').is_disabled()
    assert '설정' in page.locator('#cs-preview-md').inner_text()
    assert '기록한 동작 1개' in page.locator('#cs-preview-source').inner_text()
    page.evaluate('csClosePreview()')
    assert not page.locator('#cs-preview-modal').is_visible()
