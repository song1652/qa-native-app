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
    "/static/import-studio.js",
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
