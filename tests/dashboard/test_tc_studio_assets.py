from pathlib import Path


def test_tc_studio_is_available_as_first_tc_authoring_view():
    root = Path(__file__).resolve().parents[2]
    html = (root / "agents/dashboard/dashboard.html").read_text(encoding="utf-8")
    standalone = (root / "agents/dashboard/tc_studio.html").read_text(encoding="utf-8")
    assert 'data-view="import"' not in html
    assert 'data-view="import"' not in standalone
    assert 'href="/tc-studio"' in html
    assert 'id="view-tc_studio"' not in html
    from fastapi.testclient import TestClient
    from agents.dashboard.serve import app
    response = TestClient(app).get('/tc-studio')
    assert response.status_code == 200
    assert 'class="body-wrap"' in response.text
    assert 'id="tc-studio-root"' in response.text
    assert '/static/tc-studio/main.js' in response.text
    assert '/static/tc-studio/tc-studio.css' in response.text
    assert 'class="app-layout"' not in response.text


def test_legacy_import_link_opens_tc_studio_import():
    from fastapi.testclient import TestClient
    from agents.dashboard.serve import app

    response = TestClient(app).get('/?view=import', follow_redirects=False)
    assert response.status_code == 307
    assert response.headers['location'] == '/tc-studio?import=1'
