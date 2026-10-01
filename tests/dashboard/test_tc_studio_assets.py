from pathlib import Path


def test_tc_studio_is_available_as_first_tc_authoring_view():
    root = Path(__file__).resolve().parents[2]
    html = (root / "agents/dashboard/dashboard.html").read_text(encoding="utf-8")
    assert html.index('data-view="tc_studio"') < html.index('data-view="import"')
    assert 'id="view-tc_studio"' in html
    assert '/static/tc-studio/main.js' in html
    assert '/static/tc-studio/tc-studio.css' in html
    shell = (root / "agents/dashboard/static/dashboard-shell.js").read_text(encoding="utf-8")
    assert "view === 'tc_studio'" in shell
