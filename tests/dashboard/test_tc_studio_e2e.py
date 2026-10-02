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
from _tc_model import new_case


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


def test_empty_studio_starts_with_authoring_inputs(tc_server):
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_check_empty_authoring, tc_server).result(timeout=60)


def test_existing_import_does_not_replace_default_authoring_page(tc_server):
    import _tc_library as lib

    imported = new_case(case_id='YAF_0001', sheet='혜택', path=['혜택', '', ''], feature='기존 TC')
    lib.import_cases('야핏무브', ['혜택'], [imported], 'seed')
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_check_default_with_existing, tc_server).result(timeout=60)
    assert len(lib.load_cases('야핏무브')) == 1


def test_sidebar_items_stay_in_place_between_dashboard_and_studio(tc_server):
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_check_sidebar_positions, tc_server).result(timeout=60)


def test_studio_navigation_preserves_dashboard_shell(tc_server):
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_check_shared_navigation, tc_server).result(timeout=60)


def test_legacy_import_url_opens_modal_in_shared_shell(tc_server):
    def check():
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f'{tc_server}/?view=import')
            page.locator('#import-modal').wait_for(state='visible')
            assert '/tc-studio?import=1' in page.url
            assert page.locator('.title-row').count() == 1
            browser.close()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(check).result(timeout=60)


def _check_shared_navigation(tc_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(tc_server)
        page.evaluate('window.__shellMarker = Math.random()')
        marker = page.evaluate('window.__shellMarker')
        page.locator('.sidebar-item[data-view="tc_studio"]').click()
        page.wait_for_selector('#tc-studio-root .page-title')
        assert page.url.endswith('/tc-studio')
        assert page.evaluate('window.__shellMarker') == marker
        assert page.locator('.title-row').count() == 1
        page.locator('.sidebar-item[data-view="dashboard"]').click()
        assert page.evaluate('window.__shellMarker') == marker
        assert not page.locator('#tc-studio-root').is_visible()
        browser.close()


def test_tc_studio_shows_live_environment_status(tc_server):
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_check_studio_status, tc_server).result(timeout=60)


def test_tc_studio_pipeline_link_keeps_ios_platform(tc_server):
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_check_ios_pipeline_link, tc_server).result(timeout=60)


def test_legacy_import_link_opens_excel_modal(tc_server):
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_check_legacy_import_link, tc_server).result(timeout=60)


def _check_legacy_import_link(tc_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f'{tc_server}/?view=import')
        page.wait_for_url(f'{tc_server}/tc-studio?import=1')
        page.locator('#import-modal').wait_for(state='visible')
        assert page.locator('#import-modal').is_visible()
        assert page.locator('#import-file').count() == 1
        browser.close()


def _check_ios_pipeline_link(tc_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route('**/api/state', lambda route: route.fulfill(json={
            'platform': 'android', 'step': 'executed', 'heal_count': 0,
        }))
        page.route('**/api/devices?platform=*', lambda route: route.fulfill(json={
            'ok': True, 'devices': [],
        }))
        page.goto(f'{tc_server}/?view=pipeline&from_tc_studio=1&platform=ios&tc_folder=ios_studio_case')
        page.locator('#radio-ios').wait_for(state='attached')
        page.wait_for_timeout(1000)
        assert page.locator('#radio-ios').is_checked()
        page.locator('.header-state-details summary').click()
        assert page.locator('#txt-automation').inner_text() == '자동화: XCUITest'
        browser.close()


def _check_studio_status(tc_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route('**/api/status*', lambda route: route.fulfill(json={
            'appium': True, 'devices': ['HA1XM5MS'], 'device_count': 1,
            'platform': 'android',
        }))
        page.route('**/api/state', lambda route: route.fulfill(json={
            'platform': 'android', 'step': 'generated', 'heal_count': 0,
        }))
        page.goto(f'{tc_server}/tc-studio')
        assert page.title() == 'App QA Dashboard'
        assert page.locator('.sidebar-item[data-view="tc_studio"]').inner_text() == 'TC 스튜디오'
        page.wait_for_selector('.page-title')
        assert page.locator('.page-title').inner_text() == 'TC 스튜디오'
        page.wait_for_function("document.querySelector('#txt-step')?.textContent === '생성 완료'")
        assert page.locator('.status-bar').is_visible()
        assert page.locator('#txt-appium').inner_text() == 'Appium 연결됨'
        assert page.locator('#txt-device').inner_text() == 'Android · HA1XM5MS'
        page.locator('.header-state-details summary').click()
        assert page.locator('#txt-automation').inner_text() == '자동화: ADB'
        browser.close()


def _check_sidebar_positions(tc_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        page.goto(tc_server)
        names = [item.get_attribute('data-view') for item in page.locator('.sidebar-item').all()]
        positions = {name: page.locator(f'.sidebar-item[data-view="{name}"]').bounding_box()['y'] for name in names}
        page.locator('.sidebar-item[data-view="tc_studio"]').click()
        page.wait_for_selector('#screen-generate.active')
        assert [item.get_attribute('data-view') for item in page.locator('.sidebar-item').all()] == names
        for name, y in positions.items():
            assert abs(page.locator(f'.sidebar-item[data-view="{name}"]').bounding_box()['y'] - y) <= 2, name
        page.locator('.sidebar-item[data-view="pipeline"]').click()
        page.wait_for_url(f'{tc_server}/?view=pipeline')
        for name, y in positions.items():
            assert abs(page.locator(f'.sidebar-item[data-view="{name}"]').bounding_box()['y'] - y) <= 2, name
        browser.close()


def _check_default_with_existing(tc_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f'{tc_server}/tc-studio')
        page.wait_for_function("document.querySelector('#suite-select')?.value === '기본양식'")
        page.wait_for_selector('#screen-generate.active')
        assert page.locator('#suite-select option').all_text_contents() == ['야핏무브 (1)', '기본양식 (0)']
        browser.close()


def _check_empty_authoring(tc_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f'{tc_server}/tc-studio')
        page.wait_for_function("document.querySelector('#suite-select')?.value === '기본양식'")
        # Suite selection precedes the library/context requests and screen rendering.
        page.wait_for_selector('#screen-generate.active')
        assert page.locator('#screen-generate').is_visible()
        assert page.locator('#src-paste').count() == 1
        assert page.locator('#btn-start-blank').is_hidden()
        page.wait_for_function("document.querySelectorAll('#gen-target-sheet option').length === 2")
        assert page.locator('#gen-target-sheet option').all_text_contents() == ['시트를 선택하세요', '테스트케이스']
        page.reload()
        page.wait_for_function("document.querySelector('#suite-select')?.value === '기본양식'")
        page.wait_for_selector('#screen-generate.active')
        assert page.locator('#screen-generate').is_visible()
        page.locator('#gen-target-sheet').select_option('테스트케이스')
        page.locator('#gen-path-l1').select_option('__new')
        page.locator('#gen-new-l1').fill('로그인')
        page.get_by_role('tab', name='텍스트 붙여넣기').click()
        page.locator('#src-paste').fill('로그인 버튼을 누르면 홈 화면으로 이동한다.')
        page.locator('#src-paste-add').click()
        page.wait_for_function("document.querySelector('#src-n')?.textContent === '1'")
        assert page.locator('#gen-submit').is_enabled()
        browser.close()


def _check_browser(tc_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(tc_server)
        page.locator('[data-view="tc_studio"]').click()
        page.wait_for_function("document.querySelector('#suite-select')?.value === '기본양식'")
        page.locator('#suite-select').select_option('one')
        page.wait_for_function("document.querySelector('#grid-body tr[data-case]') !== null")
        assert page.locator('.app-layout').count() == 1
        assert page.locator('.body-wrap').count() == 0
        assert page.locator('table#grid').evaluate('(el) => getComputedStyle(el).display') == 'table'
        assert page.url.endswith('/tc-studio')
        assert page.locator('.status-bar').is_visible()
        studio_box = page.locator('.tc-studio .studio').bounding_box()
        assert abs(studio_box['x'] - 264) <= 2 and abs(studio_box['y'] - 84) <= 2
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
        direct.locator('.sidebar-item[data-view="pipeline"]').click()
        direct.wait_for_url(f'{tc_server}/?view=pipeline')
        direct.locator('#view-pipeline').wait_for(state='visible')
        direct.close()
        browser.close()


def test_dashboard_confirmation_keeps_history_until_confirmed(tc_server):
    def check():
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(tc_server)
            page.evaluate("localStorage.setItem('qa-native-app.run-history', '[]')")
            page.evaluate('void resetHistory()')
            dialog = page.get_by_role('alertdialog', name='작업 확인')
            dialog.wait_for(state='visible', timeout=3000)
            dialog.get_by_role('button', name='취소', exact=True).click()
            assert page.evaluate("localStorage.getItem('qa-native-app.run-history')") == '[]'
            page.evaluate('void resetHistory()')
            dialog.get_by_role('button', name='확인', exact=True).click()
            assert page.evaluate("localStorage.getItem('qa-native-app.run-history')") is None
            assert dialog.count() == 0
            browser.close()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(check).result(timeout=60)


def test_light_studio_profile_dialog_and_extra_columns_preserve_inputs(tc_server):
    import _tc_library as lib
    case = new_case(case_id='LAY_0001', sheet='설정', path=['설정', '', ''], feature='설정 화면', expected='설정 표시')
    lib.import_cases('layout', ['설정'], [case], 'seed')

    def check():
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            page.goto(f'{tc_server}/tc-studio')
            page.locator('#screen-generate.active').wait_for()
            page.locator('#gen-profile-edit').click()
            modal = page.locator('#gen-profile-editor [role="dialog"]')
            assert modal.is_visible()
            assert modal.locator('#gen-rules-input').is_visible()
            page.locator('#gen-profile-cancel').click()
            assert not modal.is_visible()
            page.locator('#suite-select').select_option('layout')
            page.locator('[data-id="nav-tab-library"]').click()
            page.locator('[data-id="grid-cell-feature"]').wait_for()
            expected = page.locator('[data-id="grid-cell-expected"]').first
            assert expected.count() == 1
            assert not expected.is_visible()
            page.locator('#grid-extra-columns').click()
            assert expected.is_visible()
            assert expected.inner_text() == '설정 표시'
            page.locator('#grid-extra-columns').click()
            assert not expected.is_visible()
            assert page.locator('[data-id="grid-cell-feature"]').first.is_visible()
            browser.close()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(check).result(timeout=60)
    assert lib.load_cases('layout')[0]['expected'] == '설정 표시'


def test_light_studio_review_list_selects_existing_detail_card(tc_server):
    import _tc_library as lib
    cases = [new_case(case_id=f'RV_{i}', sheet='설정', path=['설정', '', ''], feature=f'초안 {i}', steps=['설정 화면을 연다'], expected='설정 제목이 표시된다') for i in (1, 2)]
    for case in cases:
        case['status'] = 'draft'
    lib.import_cases('review-layout', ['설정'], cases, 'seed')

    def check():
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            page.goto(f'{tc_server}/tc-studio')
            page.locator('#screen-generate.active').wait_for()
            page.locator('#suite-select').select_option('review-layout')
            # Browser-only fixture: importing marks cases approved; present them as drafts without persisting changes.
            page.evaluate('''() => {const api=TCS_NS.api, original=api.list; api.list=async(s,q)=>{const result=await original(s,{limit:1000});return {...result,items:result.items.map(c=>({...c,status:'draft'}))};};}''')
            page.locator('[data-id="nav-tab-review"]').click()
            page.locator('[data-review-index="1"]').wait_for()
            assert page.locator('[data-id="draft-card"]').count() == 2
            page.locator('[data-review-index="1"]').click()
            assert page.locator('[data-id="draft-card"][data-i="1"]').is_visible()
            assert not page.locator('[data-id="draft-card"][data-i="0"]').is_visible()
            assert page.locator('[data-id="draft-card"][data-i="1"] [data-id="draft-approve"]').is_enabled()
            page.locator('[data-review-index="0"]').click()
            assert page.locator('[data-id="draft-card"][data-i="0"]').is_visible()
            browser.close()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(check).result(timeout=60)


def test_review_keyboard_follows_filtered_cases_and_refreshes_source(tc_server):
    import _tc_library as lib
    cases = [new_case(case_id=f'KEY_{i}', sheet='설정', path=['설정', '', ''],
                      feature=f'검토 {i}', steps=['설정 화면을 연다'], expected='설정 제목이 표시된다')
             for i in (1, 2, 3)]
    lib.import_cases('keyboard-review', ['설정'], cases, 'seed')

    def check():
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            page.goto(f'{tc_server}/tc-studio')
            page.locator('#screen-generate.active').wait_for()
            page.locator('#suite-select').select_option('keyboard-review')
            page.evaluate('''() => {
              const api=TCS_NS.api, original=api.list;
              api.list=async(s,q)=>{const r=await original(s,{limit:1000});return {...r,
                items:r.items.map((c,i)=>({...c,status:i===1?'approved':'draft',source_refs:['ref-'+i]}))};};
              window.reviewWrites=[];
              api.patchCase=async(...args)=>{window.reviewWrites.push(args);throw new Error('Unexpected review write');};
            }''')
            page.locator('[data-id="nav-tab-review"]').click()
            page.locator('[data-review-index="2"]').wait_for()
            page.locator('[data-review-index="1"]').click()
            assert page.locator('#rv-ref').inner_text() == 'ref-1'
            page.locator('[data-id="review-filter"] [data-f="pending"]').click()
            assert page.locator('[data-id="draft-card"].focus').get_attribute('data-i') == '0'
            assert page.locator('#rv-ref').inner_text() == 'ref-0'
            page.keyboard.press('j')
            assert page.locator('[data-id="draft-card"].focus').get_attribute('data-i') == '2'
            assert page.locator('[data-id="draft-card"].focus').is_visible()
            assert page.locator('#rv-ref').inner_text() == 'ref-2'
            page.keyboard.press('k')
            assert page.locator('[data-id="draft-card"].focus').get_attribute('data-i') == '0'
            assert page.locator('#rv-ref').inner_text() == 'ref-0'
            page.locator('[data-id="review-filter"] [data-f="invalid"]').click()
            assert page.locator('[data-id="draft-card"]').count() == 0
            assert page.locator('#rv-ref').inner_text() == ''
            page.keyboard.press('a')
            page.keyboard.press('r')
            assert page.evaluate('window.reviewWrites') == []
            browser.close()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(check).result(timeout=60)
