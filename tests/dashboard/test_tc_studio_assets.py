from pathlib import Path


def test_tc_studio_is_available_as_first_tc_authoring_view():
    root = Path(__file__).resolve().parents[2]
    html = (root / "agents/dashboard/dashboard.html").read_text(encoding="utf-8")
    assert html.index('data-view="tc_studio"') < html.index('data-view="import"')
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
