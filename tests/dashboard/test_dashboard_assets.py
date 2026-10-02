"""Dashboard static-asset integration contracts."""
from pathlib import Path
import os
import re
import sys

from fastapi.testclient import TestClient


DASHBOARD = Path(__file__).parents[2] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

from serve import app  # noqa: E402
from routes import api  # noqa: E402


EXPECTED_SCRIPTS = [
    "/static/dashboard-shell.js",
    "/static/execution.js",
    "/static/quick-run.js",
    "/static/reports.js",
    "/static/observability.js",
    "/static/environment.js",
    "/static/environment-devices.js",
    "/static/capture-studio.js",
    "/static/capture-inspector.js",
    "/static/capture-actions.js",
    "/static/capture-livetail.js",
    "/static/tc-studio/api.js",
    "/static/tc-studio/state.js",
    "/static/tc-studio/detail.js",
    "/static/tc-studio/library.js",
    "/static/tc-studio/import.js",
    "/static/tc-studio/generate.js",
    "/static/tc-studio/connectors.js",
    "/static/tc-studio/review.js",
    "/static/tc-studio/export.js",
    "/static/tc-studio/main.js",
    "/static/dashboard-init.js",
]


def test_dashboard_assets_are_served_with_browser_content_types():
    with TestClient(app) as client:
        css = client.get("/static/dashboard.css")
        tc_css = client.get("/static/tc-studio/tc-studio.css")
        javascript_responses = [client.get(path) for path in EXPECTED_SCRIPTS]

    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    assert css.text.strip()
    for response in [css, tc_css, *javascript_responses]:
        assert response.headers['cache-control'] == 'no-cache'
    for response in javascript_responses:
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
        assert response.text.strip()


def test_dashboard_static_route_does_not_expose_unlisted_files():
    with TestClient(app) as client:
        response = client.get("/static/secrets.txt")

    assert response.status_code == 404


def test_dashboard_document_loads_external_assets_instead_of_inline_bundles():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    for path in ['/static/tokens.css', '/static/dashboard.css', '/static/tc-studio/tc-studio.css']:
        stamp = (DASHBOARD / path.lstrip('/')).stat().st_mtime_ns
        assert f'<link rel="stylesheet" href="{path}?v={stamp}">' in response.text
    expected = [
        f'{path}?v={(DASHBOARD / path.lstrip("/")).stat().st_mtime_ns}'
        for path in EXPECTED_SCRIPTS
    ]
    assert re.findall(r'<script src="([^"]+)"></script>', response.text) == expected
    assert response.headers['cache-control'] == 'no-cache'
    assert "<style>" not in response.text
    assert "<script>" not in response.text


def test_html_asset_versions_change_after_file_update_on_both_entry_pages(monkeypatch, tmp_path):
    static = tmp_path / 'static'
    (static / 'tc-studio').mkdir(parents=True)
    assets = ['dashboard.css', 'capture-studio.js', 'tc-studio/main.js']
    (tmp_path / 'dashboard.html').write_text(
        '<link href="/static/dashboard.css"><script src="/static/capture-studio.js"></script>'
        '<script src="/static/tc-studio/main.js"></script>'
    )
    for asset in assets:
        (static / asset).write_text('initial asset')
    monkeypatch.setattr(api, 'HERE', tmp_path)
    with TestClient(app) as client:
        initial = {path: client.get(path) for path in ['/', '/tc-studio']}
        old_stamp = (static / 'capture-studio.js').stat().st_mtime_ns
        (static / 'capture-studio.js').write_text('updated asset')
        os.utime(static / 'capture-studio.js', ns=(old_stamp + 1000000, old_stamp + 1000000))
        for path, old_document in initial.items():
            document = client.get(path)
            assert document.headers['cache-control'] == 'no-cache'
            assert f'/static/capture-studio.js?v={old_stamp}' in old_document.text
            assert f'/static/capture-studio.js?v={old_stamp + 1000000}' in document.text
            for asset in assets:
                stamp = (static / asset).stat().st_mtime_ns
                response = client.get(f'/static/{asset}?v={stamp}')
                assert response.status_code == 200
                assert response.headers['cache-control'] == 'no-cache'
                assert response.text == (static / asset).read_text()


def test_light_theme_tokens_are_served_before_component_styles():
    with TestClient(app) as client:
        response = client.get("/static/tokens.css")
        document = client.get("/").text
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert "--font-sans:" in response.text
    assert document.index('/static/tokens.css') < document.index('/static/dashboard.css')


def test_dashboard_control_handlers_are_loaded(page):
    """Every static button/input handler resolves after the shipped scripts load."""
    document = (DASHBOARD / 'dashboard.html').read_text()
    document = re.sub(r'<script\b[^>]*>.*?</script>', '', document, flags=re.S)
    document = re.sub(r'<link\b[^>]*>', '', document)
    page.route('http://control-bindings.test/', lambda route: route.fulfill(body=document, content_type='text/html'))
    page.goto('http://control-bindings.test/')
    # No startup polling, device access, or real WebSocket connections.
    page.evaluate("""() => {
      window.WebSocket=class {static OPEN=1;static CONNECTING=0;constructor(){this.readyState=0;}close(){}};
      window.fetch=async()=>({ok:true,json:async()=>({})});
    }""")
    errors=[]
    page.on('pageerror', lambda error: errors.append(str(error)))
    for script in EXPECTED_SCRIPTS:
        if script.endswith('dashboard-init.js'):
            continue
        page.add_script_tag(path=str(DASHBOARD / script.lstrip('/')))
    handlers=page.locator('*').evaluate_all("""elements=>elements.flatMap(element=>
      [...element.attributes].filter(a=>a.name.startsWith('on')).map(a=>a.value))""")
    names=set()
    for handler in handlers:
        names.update(re.findall(r'(?<![.\w])([A-Za-z_$]\w*)\s*\(', handler))
    names.difference_update({'if','function'})
    missing=page.evaluate("names=>names.filter(name=>typeof window[name]!=='function')", sorted(names))
    assert not missing,missing
    assert not errors,errors
