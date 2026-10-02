from pathlib import Path


def test_tc_studio_is_available_as_first_tc_authoring_view():
    root = Path(__file__).resolve().parents[2]
    html = (root / "agents/dashboard/dashboard.html").read_text(encoding="utf-8")
    assert 'data-view="import"' not in html
    assert 'href="/tc-studio"' in html
    assert 'id="tc-studio-root"' in html
    from fastapi.testclient import TestClient
    from agents.dashboard.serve import app
    response = TestClient(app).get('/tc-studio')
    assert response.status_code == 200
    assert 'class="app-layout"' in response.text
    assert 'id="tc-studio-root"' in response.text
    assert '/static/tc-studio/main.js' in response.text
    assert '/static/tc-studio/tc-studio.css' in response.text


def test_legacy_import_link_opens_tc_studio_import():
    from fastapi.testclient import TestClient
    from agents.dashboard.serve import app

    response = TestClient(app).get('/?view=import', follow_redirects=False)
    assert response.status_code == 307
    assert response.headers['location'] == '/tc-studio?import=1'


def test_tc_studio_header_uses_dashboard_title_without_extra_label():
    root = Path(__file__).resolve().parents[2]
    dashboard = (root / 'agents/dashboard/dashboard.html').read_text(encoding='utf-8')
    from fastapi.testclient import TestClient
    from agents.dashboard.serve import app
    studio = TestClient(app).get('/tc-studio').text
    assert 'QA Control Center' in dashboard
    assert 'QA Control Center' in studio
    assert 'APP TC STUDIO' not in studio
    assert '<header class="title-row">' in studio
