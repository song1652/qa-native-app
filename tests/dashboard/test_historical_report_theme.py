"""Viewing saved reports updates their theme without rewriting the evidence."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import sys
from pathlib import Path

from fastapi.responses import FileResponse

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / 'agents/dashboard'))
from routes import api


def _serve_report(name):
    # Playwright may already own this thread's event loop in a combined suite.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, api.serve_report(name)).result()


def test_historical_report_response_preserves_body_and_original_file(tmp_path, monkeypatch):
    original = b"""<!DOCTYPE html><html><head><title>App QA Report</title>
<style>:root{--bg-gradient:radial-gradient(#1e1b4b,#0d1117)}
body{background:var(--bg-gradient)}</style></head><body>
<div class="case-item fail" data-toggle="case_1">Original saved evidence
<a href="/screenshots/original.png">Screenshot</a></div>
<script>function toggle(uid){return uid;}</script></body></html>"""
    artifact = tmp_path / 'historical.html' 
    artifact.write_bytes(original)
    monkeypatch.setattr(api, 'REPORTS_DIR', tmp_path)
    response = _serve_report(artifact.name)
    document = response.body.decode()
    assert response.status_code == 200
    assert '--bg-gradient:' not in document
    assert 'IBM+Plex+Sans+KR' in document
    assert '--bg:#' not in document  # legacy compressed dark palette
    assert document.split('</head>', 1)[1] == original.decode().split('</head>', 1)[1]
    assert artifact.read_bytes() == original


def test_unrelated_report_is_served_unchanged(tmp_path, monkeypatch):
    artifact = tmp_path / 'custom.html'
    artifact.write_text('<html><style>body{color:red}</style><body>Evidence</body></html>')
    monkeypatch.setattr(api, 'REPORTS_DIR', tmp_path)
    response = _serve_report(artifact.name)
    assert isinstance(response, FileResponse)
    assert Path(response.path) == artifact


def test_missing_report_is_light_responsive_and_escapes_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(api, 'REPORTS_DIR', tmp_path)
    response = _serve_report('<missing>.html')
    document = response.body.decode()
    assert response.status_code == 404
    assert 'IBM+Plex+Sans+KR' in document
    assert 'width=device-width' in document
    assert '&lt;missing&gt;.html' in document
    assert '<missing>' not in document
    assert 'background:#08071b' not in document
    assert "href='/?view=reports'" in document
