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


def test_saved_light_report_adopts_chip_layout_without_changing_saved_evidence(tmp_path, monkeypatch, page):
    import re
    from scripts import report_html

    row = report_html.case_row({'title': '저장된 실제 결과 제목'}, 'settings_0', 'passed')
    original = report_html.build_report([{
        'label': 'settings', 'rows_html': row, 'pass_cnt': 1,
        'total_cnt': 1, 'all_pass': True, 'has_tests': True,
    }], {'passed': 1}, '2026-10-02')
    # Recreate the previous saved-light layout: sidebar inside the layout,
    # header actions, filters inside the group heading, and collapsed group.
    sidebar = re.search(r'  <aside class="sidebar">.*?</aside>', original, re.DOTALL).group()
    original = original.replace(sidebar, '').replace('<div class="layout">', '<div class="layout">' + sidebar)
    original = original.replace('</header>', '<div class="report-actions"><a href="/?view=reports">대시보드에서 보기</a><button>인쇄 · PDF</button></div></header>')
    original = original.replace('<div class="report-actions">', '<div class="topbar"><div class="report-actions">').replace('</button></div></header>', '</button></div></div></header>')
    original = original.replace('    </div>\n  </div>\n  <div class="filter-bar"', '    </div>\n  <div class="filter-bar"')
    original = original.replace('  </div>\n  <div class="group-body"', '  </div>\n  </div>\n  <div class="group-body"')
    original = original.replace('toggleGroup("settings");', '')
    artifact = tmp_path / 'saved-light.html'
    artifact.write_text(original)
    monkeypatch.setattr(api, 'REPORTS_DIR', tmp_path)
    response = _serve_report(artifact.name)
    document = response.body.decode()
    assert document.split('</head>', 1)[1] == original.split('</head>', 1)[1]
    assert artifact.read_text() == original
    page.set_viewport_size({'width': 856, 'height': 1000})
    page.set_content(document)
    assert page.locator('#gbody_settings').is_visible()
    assert page.locator('body > .sidebar').count() == 1
    assert not page.get_by_text('대시보드에서 보기', exact=True).count()
    assert not page.get_by_text('인쇄 · PDF', exact=True).count()
    assert page.get_by_text('저장된 실제 결과 제목', exact=True).is_visible()
    assert page.locator('.filter-bar').bounding_box()['y'] >= page.locator('.group-header').bounding_box()['y'] + page.locator('.group-header').bounding_box()['height']
