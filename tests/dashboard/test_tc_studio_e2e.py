from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

import pytest
import uvicorn
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from tests.unit.tc_library.test_tc_platform_results import _workbook


def _post(url: str, body: bytes, content_type: str) -> dict:
    request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": content_type})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


@pytest.fixture
def tc_server(tmp_path: Path, monkeypatch):
    import _paths
    from agents.dashboard.serve import app

    monkeypatch.setattr(_paths, "TC_LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(_paths, "TESTCASES_DIR", tmp_path / "testcases")
    monkeypatch.setattr(_paths, "IMPORT_PROFILES_PATH", tmp_path / "mapping_profiles.json")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def test_two_excel_formats_show_only_mismatched_app_cases(tc_server, tmp_path):
    for suite, two_rows in (("one", False), ("two", True)):
        source = _workbook(tmp_path / f"{suite}.xlsx", two_rows)
        preview = _post(f"{tc_server}/api/tc-library/import/preview?filename={suite}.xlsx",
                        source.read_bytes(), "application/octet-stream")
        _post(f"{tc_server}/api/tc-library/import", json.dumps({
            "preview_id": preview["preview_id"], "suite": suite, "sheets": ["로그인"],
            "prefixes": {"로그인": suite.upper()}}).encode(), "application/json")

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_check_browser, tc_server).result(timeout=60)


def _check_browser(tc_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(tc_server)
        page.locator('[data-view="tc_studio"]').click()
        page.wait_for_function("document.querySelector('#grid-body tr[data-case]') !== null")
        assert page.locator('.app-layout').count() == 0
        assert page.locator('.body-wrap').count() == 1
        assert page.locator('table#grid').evaluate('(el) => getComputedStyle(el).display') == 'table'
        assert page.url.endswith('/tc-studio')
        assert not page.locator('.status-bar').is_visible()
        studio_box = page.locator('.tc-studio .studio').bounding_box()
        assert abs(studio_box['x'] - 308) <= 2 and abs(studio_box['y'] - 102) <= 2
        assert page.locator('#btn-import-xlsx').bounding_box()['width'] < 160
        for suite in ("one", "two"):
            page.locator("#suite-select").select_option(suite)
            page.locator("#lib-filter-mismatch").click()
            page.wait_for_function("document.querySelectorAll('#grid-body tr[data-case]').length === 1")
            assert page.locator("#grid-body tr[data-case]").count() == 1
            assert page.locator("#grid-body tr[data-case]").first.get_attribute("data-case").startswith(suite.upper())
            page.locator("#lib-filter-mismatch").click()
        page.locator("#suite-select").select_option("one")
        page.wait_for_function("document.querySelector('#grid-body tr[data-case]')?.dataset.case.startsWith('ONE_')")
        page.locator('#grid-body tr[data-case]').first.locator('[data-id="grid-row-check"]').check()
        page.locator("#bulk-platform").select_option("android")
        with page.expect_response(lambda response: "/one/bulk" in response.url) as bulk_response:
            page.locator("#bulk-result").select_option("fail")
        assert bulk_response.value.status == 200, bulk_response.value.text()
        page.locator("#lib-filter-mismatch").click()
        page.wait_for_function("document.querySelectorAll('#grid-body tr[data-case]').length === 0")
        assert page.locator('#grid-body tr[data-case]').count() == 0
        direct = browser.new_page()
        direct.goto(f'{tc_server}/tc-studio')
        direct.wait_for_selector('#suite-select')
        assert direct.locator('[data-view="tc_studio"]').get_attribute('class').find('active') >= 0
        direct.locator('a[href="/?view=pipeline"]').click()
        direct.wait_for_url(f'{tc_server}/?view=pipeline')
        assert direct.locator('#view-pipeline').is_visible()
        direct.close()
        browser.close()
