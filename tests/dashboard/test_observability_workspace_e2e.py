"""Browser-level contract for the mockup-style observability workspace."""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

DASHBOARD = Path(__file__).parents[2] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

RUN_ID = "run_android_20260917_143012_881"
FAILED_NODE = "tests/generated/android/settings/tc_settings_battery.py::TestBattery::test_battery"
PASSED_NODE = "tests/generated/android/settings/tc_settings_wifi.py::TestWifi::test_wifi"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    from serve import app

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        pytest.fail("dashboard server did not start")
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=3)


@pytest.fixture
def workspace_page(page, live_server):
    attempts = [
        {
            "n": n,
            "outcome": "failed",
            "duration_sec": 40 + n,
            "failure_offset_sec": 40 + n,
            "kept": True,
            "video": {"path": f"battery/attempt{n}/video.mp4", "bytes": n * 1024},
            "syslog": {"path": f"battery/attempt{n}/syslog.txt", "bytes": 300 + n},
            "screenshot": {"path": f"battery/attempt{n}/screenshot.png", "bytes": 128},
            "screenshot_url": (
                f"/api/run_artifacts/{RUN_ID}/screenshot?nodeid={FAILED_NODE}&attempt={n}"
            ),
            "collect_errors": [],
        }
        for n in (1, 2, 3)
    ]
    manifest = {
        "ok": True,
        "run_id": RUN_ID,
        "platform": "android",
        "mode": "emulator",
        "udid": "emulator-5554",
        "device_name": "Android Emulator",
        "keep_policy": "on_failure",
        "entries": [
            {
                "nodeid": PASSED_NODE,
                "slug": "wifi",
                "outcome": "passed",
                "attempt_count": 1,
                "attempts": [{"n": 1, "outcome": "passed", "duration_sec": 9.2,
                              "kept": False, "video": None, "syslog": None,
                              "screenshot": None, "collect_errors": []}],
            },
            {
                "nodeid": FAILED_NODE,
                "slug": "battery",
                "outcome": "failed",
                "attempt_count": 3,
                "attempts": attempts,
            },
        ],
    }

    def artifacts(route, request):
        if "/video?" in request.url:
            route.fulfill(status=200, content_type="video/mp4", body=b"")
        elif "/logcat?" in request.url:
            route.fulfill(
                status=200,
                content_type="text/plain",
                body="09-17 I App: launch\n09-17 E AndroidRuntime: crash",
            )
        elif "/screenshot?" in request.url:
            route.fulfill(status=200, content_type="image/png", body=b"png")
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(manifest))

    page.route(f"**/api/run_artifacts/{RUN_ID}**", artifacts)
    page.set_default_timeout(5000)
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{live_server}/#obs/{RUN_ID}", wait_until="domcontentloaded")
    return page


def test_workspace_opens_with_run_summary_and_failed_case_selected(workspace_page):
    page = workspace_page
    # The delayed "latest run" restore must not overwrite an explicit #obs/run link.
    page.wait_for_timeout(1000)
    assert page.locator(".obs-run-workspace").get_attribute("data-run-id") == RUN_ID
    assert page.locator(".obs-run-summary").get_by_text(RUN_ID).count() == 1
    assert page.locator(".obs-run-case").count() == 2
    assert page.locator(".obs-run-case.is-selected").get_attribute("data-nodeid") == FAILED_NODE
    assert page.locator(".obs-evidence-title").inner_text() == "tc_settings_battery::test_battery"
    assert page.locator("[data-obs-attempt]").count() == 3
    assert "attempt=3" in page.locator(".obs-evidence-video").get_attribute("src")
    page.locator('.obs-evidence-section[data-kind="log"] .obs-evidence-log').wait_for()
    sections = page.locator(
        '.obs-evidence-section[data-kind="video"], '
        '.obs-evidence-section[data-kind="log"], '
        '.obs-evidence-section[data-kind="shot"]'
    )
    assert sections.count() == 3
    assert sections.evaluate_all(
        "elements => elements.map(element => element.dataset.kind)"
    ) == ["video", "log", "shot"]
    assert "/screenshot?" in page.locator(".obs-evidence-shot").get_attribute("src")
    assert page.locator(".obs-evidence-shot").get_attribute("alt") == "실행 스크린샷"
    boxes = [sections.nth(index).bounding_box() for index in range(3)]
    assert all(boxes)
    assert boxes[0]["y"] < boxes[1]["y"] < boxes[2]["y"]
    assert page.locator(".obs-evidence-tab").count() == 0

    selected = page.locator(".obs-run-case.is-selected")
    name_box = selected.locator(".obs-case-name").bounding_box()
    side_box = selected.locator(".obs-case-side").bounding_box()
    assert name_box and side_box
    assert name_box["x"] + name_box["width"] <= side_box["x"] + 1


def test_quick_run_defaults_to_skip_healing_and_single_attempt(workspace_page):
    checkbox = workspace_page.locator("#generated-heal")

    assert checkbox.is_checked()


def test_quick_run_failure_status_distinguishes_files_from_retry_attempts(workspace_page):
    page = workspace_page
    page.locator("#quick-run-status").wait_for(state="attached")

    rendered = page.evaluate(
        """() => {
            const status = document.getElementById('quick-run-status');
            _setQuickRunCompletionStatus(status, 3, 2);
            return {text: status.textContent, className: status.className};
        }"""
    )

    assert rendered == {
        "text": "● 3개 실행 완료 · 2개 실패",
        "className": "quick-run-status fail",
    }


def test_workspace_case_and_attempt_selection_update_evidence(workspace_page):
    page = workspace_page
    page.locator('.obs-run-case[data-nodeid="%s"]' % FAILED_NODE).click()
    page.locator('[data-obs-attempt="1"]').click()
    assert "attempt=1" in page.locator(".obs-evidence-video").get_attribute("src")
    assert "attempt=1" in page.locator(".obs-evidence-log").get_attribute("data-source")

    page.locator('.obs-run-case[data-nodeid="%s"]' % PASSED_NODE).click()
    assert page.locator(".obs-evidence-empty").get_by_text("보존 정책").count() == 2


def test_workspace_filters_inline_log_without_hiding_video(workspace_page):
    page = workspace_page
    log = page.locator('.obs-evidence-section[data-kind="log"] .obs-evidence-log')
    log.wait_for()
    page.locator(".obs-log-search").fill("AndroidRuntime")
    page.wait_for_function(
        "(element => element && element.textContent.includes('AndroidRuntime: crash'))"
        "(document.querySelector('.obs-evidence-log'))"
    )
    assert "AndroidRuntime: crash" in log.inner_text()
    assert "App: launch" not in log.inner_text()
    assert page.locator(".obs-evidence-video").is_visible()


def test_workspace_log_presets_do_not_duplicate_values_in_search(workspace_page):
    page = workspace_page
    log = page.locator('.obs-evidence-section[data-kind="log"] .obs-evidence-log')
    page.wait_for_function(
        "(element => element && element.textContent.includes('App: launch'))"
        "(document.querySelector('.obs-evidence-log'))"
    )
    page.get_by_role("button", name="오류", exact=True).click()

    assert page.locator(".obs-log-search").input_value() == ""
    assert "AndroidRuntime: crash" in log.inner_text()
    assert "App: launch" not in log.inner_text()


def test_system_log_colors_time_level_source_and_message_for_android_and_ios(workspace_page):
    page = workspace_page
    log = page.locator('.obs-evidence-section[data-kind="log"] .obs-evidence-log')
    log.wait_for()
    page.evaluate(
        """() => {
            const log = document.getElementById('obs-evidence-log');
            _obsInlineLog.source = log.dataset.source;
            _obsInlineLog.query = '';
            _obsInlineLog.preset = 'all';
            _obsInlineLog.lines = [
                '09-17 17:24:17.298  480  413 E AndroidRuntime: fatal crash',
                '2026-09-17 17:24:17.298 Df CoreSimulatorBridge[51704:838c4a] Requesting launch'
            ];
            _obsRenderInlineLog();
        }"""
    )

    rows = log.locator('.obs-log-row')
    assert rows.count() == 2
    assert rows.nth(0).locator('.obs-log-time').inner_text() == '09-17 17:24:17.298'
    assert rows.nth(0).locator('.obs-log-level').inner_text() == 'E'
    assert 'AndroidRuntime' in rows.nth(0).locator('.obs-log-source').inner_text()
    assert rows.nth(0).get_attribute('data-level') == 'error'
    assert rows.nth(1).locator('.obs-log-time').inner_text() == '2026-09-17 17:24:17.298'
    assert rows.nth(1).locator('.obs-log-level').inner_text() == 'Df'
    assert 'CoreSimulatorBridge' in rows.nth(1).locator('.obs-log-source').inner_text()
    assert rows.nth(1).get_attribute('data-level') == 'debug'


def test_system_log_highlights_search_text_inside_structured_rows(workspace_page):
    page = workspace_page
    log = page.locator('.obs-evidence-section[data-kind="log"] .obs-evidence-log')
    log.wait_for()
    page.evaluate(
        """() => {
            const log = document.getElementById('obs-evidence-log');
            _obsInlineLog.source = log.dataset.source;
            _obsInlineLog.query = '';
            _obsInlineLog.preset = 'all';
            _obsInlineLog.lines = [
                '2026-09-17 17:24:17.298 Df CoreSimulatorBridge[51704:838c4a] Requesting launch'
            ];
            _obsRenderInlineLog();
        }"""
    )

    page.locator('.obs-log-search').fill('CoreSimulatorBridge')

    assert log.locator('mark').inner_text() == 'CoreSimulatorBridge'
    assert log.locator('.obs-log-row').count() == 1


def test_structured_system_log_fits_inside_evidence_panel_without_horizontal_scroll(workspace_page):
    page = workspace_page
    log = page.locator('.obs-evidence-section[data-kind="log"] .obs-evidence-log')
    log.wait_for()
    page.evaluate(
        """() => {
            const log = document.getElementById('obs-evidence-log');
            _obsInlineLog.source = log.dataset.source;
            _obsInlineLog.query = '';
            _obsInlineLog.preset = 'all';
            _obsInlineLog.lines = [
                '2026-09-17 17:24:17.298 Df CoreSimulatorBridge[51704:838c4a] Requesting launch of com.apple.Preferences'
            ];
            _obsRenderInlineLog();
        }"""
    )

    dimensions = log.evaluate(
        "element => ({clientWidth: element.clientWidth, scrollWidth: element.scrollWidth})"
    )
    assert dimensions["scrollWidth"] <= dimensions["clientWidth"] + 1


def test_workspace_filters_case_results_and_paginates_ten_per_page(workspace_page):
    page = workspace_page
    page.wait_for_timeout(1000)
    entries = []
    for index in range(13):
        if index < 8:
            outcomes = ["passed"]
        elif index < 12:
            outcomes = ["failed"]
        else:
            outcomes = ["failed", "passed"]
        entries.append({
            "nodeid": f"tests/generated/ios/obs_demo/tc_{index + 1:02d}.py::test_case_{index + 1:02d}",
            "outcome": outcomes[-1],
            "attempts": [
                {
                    "n": attempt + 1,
                    "outcome": outcome,
                    "duration_sec": 1.0,
                    "kept": False,
                    "video": None,
                    "syslog": None,
                    "screenshot": None,
                    "collect_errors": [],
                }
                for attempt, outcome in enumerate(outcomes)
            ],
        })

    page.evaluate(
        "entries => _obsRenderWorkspace('run_ios_pagination', {"
        "run_id: 'run_ios_pagination', platform: 'ios', entries})",
        entries,
    )

    filters = page.locator(".obs-case-filter")
    assert filters.all_inner_texts() == ["전체 13", "성공 9", "실패 4"]
    assert page.locator(".obs-run-case").count() == 10
    assert page.locator(".obs-case-page-label").inner_text() == "1 / 2"
    assert page.locator(".obs-case-range").inner_text() == (
        "페이지당 10개 · 1–10 / 전체 13개"
    )

    page.get_by_role("button", name="다음", exact=True).click()
    assert page.locator(".obs-run-case").count() == 3
    assert page.locator(".obs-case-page-label").inner_text() == "2 / 2"
    assert page.locator(".obs-case-range").inner_text() == (
        "페이지당 10개 · 11–13 / 전체 13개"
    )

    last_case = page.locator(".obs-run-case").last
    last_nodeid = last_case.get_attribute("data-nodeid")
    last_case.click()
    assert page.locator(".obs-case-filter.active").inner_text() == "전체 13"
    assert page.locator(".obs-case-page-label").inner_text() == "2 / 2"
    assert page.locator(".obs-run-case.is-selected").get_attribute("data-nodeid") == last_nodeid

    page.get_by_role("button", name="성공 9", exact=True).click()
    assert page.locator(".obs-run-case").count() == 9
    assert page.locator(".obs-run-case.is-failed").count() == 0
    assert page.locator(".obs-run-case.is-flaky").count() == 1
    assert page.locator(".obs-case-page-label").inner_text() == "1 / 1"

    page.get_by_role("button", name="실패 4", exact=True).click()
    assert page.locator(".obs-run-case").count() == 4
    assert page.locator(".obs-run-case.is-failed").count() == 4
    assert page.locator(".obs-run-case.is-flaky").count() == 0


def test_quick_and_pipeline_views_use_full_available_content_width(workspace_page):
    page = workspace_page
    page.wait_for_timeout(1000)

    def widths():
        return page.evaluate(
            """() => {
                const main = document.querySelector('.app-main');
                const grid = main.querySelector(':scope > .grid');
                const style = getComputedStyle(main);
                return {
                    available: main.clientWidth
                        - parseFloat(style.paddingLeft)
                        - parseFloat(style.paddingRight),
                    grid: grid.getBoundingClientRect().width,
                };
            }"""
        )

    quick = widths()
    assert quick["grid"] >= quick["available"] - 2

    page.evaluate(
        "selectView('pipeline', document.querySelector('[data-view=pipeline]'))"
    )
    pipeline = widths()
    assert pipeline["grid"] >= pipeline["available"] - 2


def test_evidence_policy_control_shows_selected_action_and_immediate_effect(workspace_page):
    page = workspace_page
    page.wait_for_timeout(1000)

    page.locator("#obs-strip-quick label", has_text="항상").click()

    assert page.evaluate("_obsKeep") == "always"
    assert page.evaluate(
        "localStorage.getItem('qa-native-app.obs-keep')"
    ) == "always"
    for strip_id in ("obs-strip-quick", "obs-strip-pipeline"):
        strip = page.locator(f"#{strip_id}")
        selected_text = strip.locator(
            ".obs-policy-option.is-selected"
        ).inner_text()
        assert "✓" in selected_text
        assert selected_text.endswith("항상")
        assert strip.locator(".obs-policy-feedback").inner_text() == (
            "성공 포함 모든 증거 보존 · 약 33 MB/run"
        )


def test_case_result_typography_is_readable_at_desktop_size(workspace_page):
    page = workspace_page
    page.wait_for_timeout(1000)
    sizes = page.locator(".obs-run-case").first.evaluate(
        """element => ({
            rowHeight: element.getBoundingClientRect().height,
            name: parseFloat(getComputedStyle(element.querySelector('.obs-case-name')).fontSize),
            meta: parseFloat(getComputedStyle(element.querySelector('.obs-case-meta')).fontSize),
            duration: parseFloat(getComputedStyle(element.querySelector('.obs-case-duration')).fontSize),
            status: parseFloat(getComputedStyle(element.querySelector('.obs-status')).fontSize),
        })"""
    )

    assert sizes["rowHeight"] >= 74
    assert sizes["name"] >= 13
    assert sizes["meta"] >= 10.5
    assert sizes["duration"] >= 11
    assert sizes["status"] >= 10.5


def test_case_pager_stays_at_bottom_of_tall_result_panel(workspace_page):
    page = workspace_page
    page.wait_for_timeout(1000)
    positions = page.evaluate(
        """() => {
            const panel = document.querySelector('.obs-run-list-panel');
            const pager = panel.querySelector('.obs-case-pager');
            return {
                panelBottom: panel.getBoundingClientRect().bottom,
                pagerBottom: pager.getBoundingClientRect().bottom,
            };
        }"""
    )

    assert abs(positions["panelBottom"] - positions["pagerBottom"]) <= 1


def test_case_list_height_is_independent_from_tall_failure_evidence(workspace_page):
    page = workspace_page
    page.wait_for_timeout(1000)
    layout = page.evaluate(
        """() => {
            const list = document.querySelector('.obs-run-list-panel');
            const evidence = document.querySelector('.obs-evidence-panel');
            const listBox = list.getBoundingClientRect();
            const evidenceBox = evidence.getBoundingClientRect();
            return {
                listTop: listBox.top,
                evidenceTop: evidenceBox.top,
                listHeight: listBox.height,
                evidenceHeight: evidenceBox.height,
                listPosition: getComputedStyle(list).position,
            };
        }"""
    )

    assert abs(layout["listTop"] - layout["evidenceTop"]) <= 1
    assert layout["listHeight"] < layout["evidenceHeight"]
    assert layout["listPosition"] == "sticky"


def test_device_picker_typography_is_readable_in_quick_and_pipeline_views(workspace_page):
    page = workspace_page
    page.wait_for_timeout(1000)

    def device_sizes(container_id):
        return page.locator(f"#{container_id} .device-card").first.evaluate(
            """element => ({
                rowHeight: element.getBoundingClientRect().height,
                name: parseFloat(getComputedStyle(element.querySelector('.device-name')).fontSize),
                meta: parseFloat(getComputedStyle(element.querySelector('.device-meta')).fontSize),
                badge: parseFloat(getComputedStyle(element.querySelector('.device-badge')).fontSize),
                radio: element.querySelector('.device-radio').getBoundingClientRect().width,
            })"""
        )

    quick = device_sizes("quick-device-list")
    page.evaluate(
        "selectView('pipeline', document.querySelector('[data-view=pipeline]'))"
    )
    pipeline = device_sizes("pipeline-device-list")

    for sizes in (quick, pipeline):
        assert sizes["rowHeight"] >= 54
        assert sizes["name"] >= 13
        assert sizes["meta"] >= 11
        assert sizes["badge"] >= 10.5
        assert sizes["radio"] >= 15


def test_ios_workspace_uses_same_vertical_evidence_layout(workspace_page):
    page = workspace_page
    page.wait_for_timeout(1000)
    ios_manifest = {
        "run_id": RUN_ID,
        "platform": "ios",
        "mode": "simulator",
        "device_name": "iPhone 16 Simulator",
        "keep_policy": "on_failure",
        "entries": [{
            "nodeid": FAILED_NODE,
            "outcome": "failed",
            "attempts": [{
                "n": 1,
                "outcome": "failed",
                "duration_sec": 4.2,
                "failure_offset_sec": 4.2,
                "kept": True,
                "video": {"path": "ios/video.mp4", "bytes": 2048},
                "syslog": {"path": "ios/syslog.txt", "bytes": 512},
                "screenshot": None,
                "collect_errors": [],
            }],
        }],
    }
    page.evaluate("manifest => _obsRenderWorkspace(manifest.run_id, manifest)", ios_manifest)
    assert page.locator('.obs-run-workspace[data-platform="ios"]').count() == 1
    assert page.locator(".obs-run-summary").get_by_text("iPhone 16 Simulator").count() == 1
    assert page.locator(
        '.obs-evidence-section[data-kind="video"], '
        '.obs-evidence-section[data-kind="log"], '
        '.obs-evidence-section[data-kind="shot"]'
    ).evaluate_all(
        "elements => elements.map(element => element.dataset.kind)"
    ) == ["video", "log", "shot"]


def test_pipeline_result_injection_uses_vertical_evidence_layout(workspace_page):
    page = workspace_page
    page.locator("#quick-generated-result").evaluate("element => element.innerHTML = ''")
    page.evaluate("runId => _obsInjectEvidenceButtons(runId)", RUN_ID)
    page.locator('.obs-run-workspace[data-run-id="%s"]' % RUN_ID).wait_for()
    assert page.locator(
        '.obs-evidence-section[data-kind="video"], '
        '.obs-evidence-section[data-kind="log"], '
        '.obs-evidence-section[data-kind="shot"]'
    ).evaluate_all(
        "elements => elements.map(element => element.dataset.kind)"
    ) == ["video", "log", "shot"]


def test_quick_result_recovers_run_id_from_status_when_websocket_was_missed(workspace_page):
    page = workspace_page
    page.locator("#quick-generated-result").wait_for(state="attached")
    page.route(
        "**/api/status?platform=android",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"obs_last_run_id": RUN_ID}),
        ),
    )
    page.evaluate(
        """() => {
            _obsLastRunId = null;
            localStorage.removeItem('qa-native-app.obs-last-run-id.android');
            document.getElementById('quick-generated-result').innerHTML =
                '<div class="quick-result-card">legacy result</div>';
        }"""
    )

    page.evaluate(
        """async () => {
            const runId = await _obsResolveLatestRunId('android');
            await _obsInjectEvidenceButtons(runId);
        }"""
    )

    page.locator(f'.obs-run-workspace[data-run-id="{RUN_ID}"]').wait_for()
    assert page.locator(".quick-result-card").count() == 0


def test_completed_quick_run_renders_only_mockup_workspace(workspace_page):
    page = workspace_page
    page.locator("#quick-generated-result").wait_for(state="attached")
    page.route(
        "**/api/status?platform=android",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"obs_last_run_id": RUN_ID}),
        ),
    )
    page.evaluate(
        """() => {
            document.getElementById('quick-generated-result').innerHTML =
                '<div class="quick-result-card">legacy result</div>';
        }"""
    )

    page.evaluate("async () => await _obsRenderCompletedQuickRun('android')")

    page.locator(f'.obs-run-workspace[data-run-id="{RUN_ID}"]').wait_for()
    assert page.locator(".quick-result-card").count() == 0


def test_latest_run_id_falls_back_to_platform_run_list(workspace_page):
    page = workspace_page
    ios_run_id = "run_ios_20260917_143012_882"
    page.route(
        "**/api/status?platform=ios",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"obs_last_run_id": RUN_ID}),
        ),
    )
    page.route(
        "**/api/run_artifacts?platform=ios&limit=1",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True, "runs": [{"run_id": ios_run_id}]}),
        ),
    )
    page.evaluate(
        """() => {
            _obsLastRunId = null;
            localStorage.removeItem('qa-native-app.obs-last-run-id.ios');
        }"""
    )

    resolved = page.evaluate("async () => await _obsResolveLatestRunId('ios')")

    assert resolved == ios_run_id


def test_workspace_clamps_failure_seek_to_recorded_video(workspace_page):
    page = workspace_page
    page.locator('.obs-run-case[data-nodeid="%s"]' % FAILED_NODE).click()
    video = page.locator(".obs-evidence-video")
    video.evaluate(
        """element => {
            Object.defineProperty(element, 'duration', {value: 40, configurable: true});
            Object.defineProperty(element, 'currentTime', {value: 0, writable: true, configurable: true});
            element.dispatchEvent(new Event('loadedmetadata'));
        }"""
    )
    assert video.evaluate("element => element.currentTime") == pytest.approx(39.9)
    assert "00:39.9 CRASH" in page.locator(".obs-crash-marker").inner_text()


def test_workspace_stacks_columns_on_narrow_viewport(workspace_page):
    page = workspace_page
    page.set_viewport_size({"width": 720, "height": 900})
    left = page.locator(".obs-run-list-panel").bounding_box()
    right = page.locator(".obs-evidence-panel").bounding_box()
    assert left and right
    assert right["y"] > left["y"] + left["height"] - 2
    assert page.locator(".obs-run-list-panel").evaluate(
        "element => getComputedStyle(element).position"
    ) == "static"
