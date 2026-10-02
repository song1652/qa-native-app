"""Dashboard static-asset integration contracts."""
from pathlib import Path
import re
import sys

from fastapi.testclient import TestClient


DASHBOARD = Path(__file__).parents[2] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

from serve import app  # noqa: E402


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
        javascript_responses = [client.get(path) for path in EXPECTED_SCRIPTS]

    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    assert css.text.strip()
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
    assert '<link rel="stylesheet" href="/static/dashboard.css">' in response.text
    assert '<link rel="stylesheet" href="/static/tc-studio/tc-studio.css">' in response.text
    assert re.findall(r'<script src="([^"]+)"></script>', response.text) == EXPECTED_SCRIPTS
    assert "<style>" not in response.text
    assert "<script>" not in response.text


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
