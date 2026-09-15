"""
Phase 3 대시보드 E2E 테스트 — Playwright 브라우저 기반.

실제 FastAPI 서버를 스레드로 구동 후 Playwright로 브라우저를 열어
Phase 3 UI 상호작용(버튼 클릭 → 모달 열림 → 폼 제출 → API 호출)을
검증합니다.

실행:
  .venv/bin/pytest tests/dashboard/env/test_env_phase3_e2e.py -v --headed

참고: Appium·실기기 없이도 동작합니다 (API는 모두 route-intercept로 모킹).
"""
import json
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

DASHBOARD = Path(__file__).parents[3] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

# ── 서버 픽스처 ───────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    """FastAPI 앱을 임시 포트로 백그라운드 스레드에서 구동한다."""
    from serve import app  # noqa: E402

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # 서버 준비 대기 (최대 5초)
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        pytest.fail("FastAPI 서버가 5초 안에 시작되지 않음")

    url = f"http://127.0.0.1:{port}"
    yield url

    server.should_exit = True
    thread.join(timeout=3)


# ── API 모킹 픽스처 ─────────────────────────────────────────────

@pytest.fixture
def dashboard_page(page, live_server):
    """
    대시보드를 로드하고 ENV 관련 API를 모킹한다.
    - /api/env/status  → 기본 stopped 상태
    - /api/status      → idle
    - /api/generated   → []
    - /api/env/android/real/pair   → {"ok": true, "detail": "mock"}
    - /api/env/ios/real/wda_build  → {"ok": true, "pid": 9999}
    """
    def _env_status(route, request):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "appium":  {"status": "stopped", "pid": None, "port": 4723,
                            "error_msg": None, "started_at": None},
                "android": {"status": "stopped", "avd": None, "started_at": None,
                            "devices": [], "real_devices": []},
                "ios":     {"status": "stopped", "simulator": None,
                            "started_at": None, "devices": [], "real_devices": []},
                "capture_active": False,
                "pipeline_active": False,
            }),
        )

    def _status(route, request):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "idle", "platform": None}),
        )

    def _generated(route, request):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps([]),
        )

    def _wifi_pair(route, request):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True, "detail": "mock 페어링 성공"}),
        )

    def _wda_build(route, request):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True, "pid": 9999, "log": "/tmp/wda_build.log"}),
        )

    page.route("**/api/env/status", _env_status)
    page.route("**/api/status", _status)
    page.route("**/api/generated*", _generated)
    page.route("**/api/testcases*", _generated)
    page.route("**/api/env/android/real/pair", _wifi_pair)
    page.route("**/api/env/ios/real/wda_build", _wda_build)

    page.goto(live_server, wait_until="domcontentloaded")

    # 환경 설정(config) 탭으로 이동 → view-config가 표시됨
    # selectView('config', el)을 JS로 직접 호출해 탭 전환
    page.evaluate("selectView('config', document.querySelector('[data-view=config]'))")
    # view-config가 실제로 보이는지 확인
    page.wait_for_function(
        "document.getElementById('view-config').style.display !== 'none'",
        timeout=3000,
    )
    return page


# ── Android 실기기 — WiFi 페어링 모달 ───────────────────────────

class TestWifiPairModal:

    def test_wifi_pair_button_exists_in_dom(self, dashboard_page):
        """📡 WiFi 페어링 버튼이 DOM에 존재한다."""
        btn = dashboard_page.locator("button", has_text="WiFi 페어링")
        assert btn.count() >= 1, "WiFi 페어링 버튼이 존재하지 않음"

    def test_wifi_pair_button_not_stretched(self, dashboard_page):
        """📡 WiFi 페어링 버튼이 컨테이너를 가득 채우지 않는다 (flex:none)."""
        btn = dashboard_page.locator("button", has_text="WiFi 페어링").first
        container = btn.evaluate("el => el.parentElement.getBoundingClientRect().width")
        btn_width = btn.evaluate("el => el.getBoundingClientRect().width")
        # 버튼 너비가 컨테이너의 절반 이하여야 함 (flex:none 적용 확인)
        assert btn_width < container * 0.6, (
            f"버튼({btn_width}px)이 너무 넓음 — 컨테이너({container}px)의 60% 초과"
        )

    def test_wifi_pair_modal_hidden_by_default(self, dashboard_page):
        """WiFi 페어링 모달은 기본적으로 숨겨져 있다."""
        modal = dashboard_page.locator("#env-wifi-pair-modal")
        assert modal.count() == 1
        display = modal.evaluate("el => el.style.display")
        assert display == "none", f"모달이 기본 표시 상태: display={display!r}"

    def test_wifi_pair_modal_opens_on_button_click(self, dashboard_page):
        """WiFi 페어링 버튼 클릭 시 모달이 flex로 전환된다."""
        btn = dashboard_page.locator("button", has_text="WiFi 페어링").first
        btn.click()
        modal = dashboard_page.locator("#env-wifi-pair-modal")
        display = modal.evaluate("el => el.style.display")
        assert display == "flex", f"모달이 열리지 않음: display={display!r}"

    def test_wifi_pair_modal_fields_visible(self, dashboard_page):
        """모달 열린 후 IP·포트·코드 입력 필드가 보인다."""
        dashboard_page.locator("button", has_text="WiFi 페어링").first.click()
        assert dashboard_page.locator("#env-pair-ip").count() == 1
        assert dashboard_page.locator("#env-pair-port").count() == 1
        assert dashboard_page.locator("#env-pair-code").count() == 1

    def test_wifi_pair_cancel_closes_modal(self, dashboard_page):
        """취소 버튼 클릭 시 모달이 닫힌다."""
        dashboard_page.locator("button", has_text="WiFi 페어링").first.click()
        modal = dashboard_page.locator("#env-wifi-pair-modal")
        # 취소 버튼은 모달 내부에 있음
        cancel = modal.locator("button", has_text="취소")
        cancel.click()
        display = modal.evaluate("el => el.style.display")
        assert display == "none", "취소 후 모달이 닫히지 않음"

    def test_wifi_pair_submit_empty_shows_alert(self, dashboard_page):
        """빈 폼 제출 시 alert를 표시한다."""
        dashboard_page.locator("button", has_text="WiFi 페어링").first.click()
        modal = dashboard_page.locator("#env-wifi-pair-modal")

        alerted = []
        dashboard_page.on("dialog", lambda d: (alerted.append(d.message), d.accept()))

        modal.locator("button", has_text="페어링").click()
        assert len(alerted) == 1
        assert "입력하세요" in alerted[0]

    def test_wifi_pair_submit_calls_api(self, dashboard_page):
        """IP·포트·코드 입력 후 제출 시 /api/env/android/real/pair를 호출한다."""
        api_called = []

        def _intercept(route, request):
            api_called.append(json.loads(request.post_data or "{}"))
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"ok": True, "detail": "paired"}),
            )

        dashboard_page.route("**/api/env/android/real/pair", _intercept)

        dashboard_page.locator("button", has_text="WiFi 페어링").first.click()
        modal = dashboard_page.locator("#env-wifi-pair-modal")

        dashboard_page.fill("#env-pair-ip", "192.168.1.42")
        dashboard_page.fill("#env-pair-port", "37177")
        dashboard_page.fill("#env-pair-code", "123456")

        modal.locator("button", has_text="페어링").click()

        # API 호출 확인 (최대 2초 대기)
        deadline = time.time() + 2
        while not api_called and time.time() < deadline:
            time.sleep(0.1)

        assert len(api_called) == 1
        body = api_called[0]
        assert body.get("ip") == "192.168.1.42"
        assert str(body.get("port")) == "37177"
        assert str(body.get("code")) == "123456"

    def test_wifi_pair_success_shows_feedback(self, dashboard_page):
        """API 성공 응답 시 결과 div에 성공 메시지가 표시된다."""
        dashboard_page.locator("button", has_text="WiFi 페어링").first.click()
        dashboard_page.fill("#env-pair-ip", "192.168.1.42")
        dashboard_page.fill("#env-pair-port", "37177")
        dashboard_page.fill("#env-pair-code", "654321")

        modal = dashboard_page.locator("#env-wifi-pair-modal")
        modal.locator("button", has_text="페어링").click()

        # "페어링 중..." 이후 최종 결과로 업데이트될 때까지 대기
        result = dashboard_page.locator("#env-pair-result")
        dashboard_page.wait_for_function(
            """(function() {
              var el = document.getElementById('env-pair-result');
              var text = el.textContent || '';
              return text.length > 0 && !text.includes('페어링 중');
            })()""",
            timeout=5000,
        )
        text = result.text_content()
        assert "성공" in text or "paired" in text or "mock" in text.lower()


# ── iOS 실기기 — WDA 빌드 모달 ──────────────────────────────────

class TestWdaBuildModal:

    def test_wda_build_button_exists_in_dom(self, dashboard_page):
        """🔨 WDA 빌드 버튼이 DOM에 존재한다."""
        btn = dashboard_page.locator("button", has_text="WDA 빌드")
        assert btn.count() >= 1, "WDA 빌드 버튼이 존재하지 않음"

    def test_wda_build_button_not_stretched(self, dashboard_page):
        """🔨 WDA 빌드 버튼이 컨테이너를 가득 채우지 않는다 (flex:none)."""
        btn = dashboard_page.locator("button", has_text="WDA 빌드").first
        container = btn.evaluate("el => el.parentElement.getBoundingClientRect().width")
        btn_width = btn.evaluate("el => el.getBoundingClientRect().width")
        assert btn_width < container * 0.6, (
            f"버튼({btn_width}px)이 너무 넓음 — 컨테이너({container}px)의 60% 초과"
        )

    def test_wda_build_modal_hidden_by_default(self, dashboard_page):
        """WDA 빌드 모달은 기본적으로 숨겨져 있다."""
        modal = dashboard_page.locator("#env-wda-build-modal")
        assert modal.count() == 1
        display = modal.evaluate("el => el.style.display")
        assert display == "none", f"모달이 기본 표시 상태: display={display!r}"

    def test_wda_build_modal_opens_on_button_click(self, dashboard_page):
        """WDA 빌드 버튼 클릭 시 모달이 flex로 전환된다."""
        btn = dashboard_page.locator("button", has_text="WDA 빌드").first
        btn.click()
        modal = dashboard_page.locator("#env-wda-build-modal")
        display = modal.evaluate("el => el.style.display")
        assert display == "flex", f"모달이 열리지 않음: display={display!r}"

    def test_wda_build_modal_fields_visible(self, dashboard_page):
        """모달 열린 후 UDID·Team ID 입력 필드가 보인다."""
        dashboard_page.locator("button", has_text="WDA 빌드").first.click()
        assert dashboard_page.locator("#env-wda-udid").count() == 1
        assert dashboard_page.locator("#env-wda-teamid").count() == 1

    def test_wda_build_cancel_closes_modal(self, dashboard_page):
        """취소 버튼 클릭 시 WDA 모달이 닫힌다."""
        dashboard_page.locator("button", has_text="WDA 빌드").first.click()
        modal = dashboard_page.locator("#env-wda-build-modal")
        modal.locator("button", has_text="취소").click()
        display = modal.evaluate("el => el.style.display")
        assert display == "none", "취소 후 모달이 닫히지 않음"

    def test_wda_build_submit_empty_shows_alert(self, dashboard_page):
        """빈 폼 제출 시 alert를 표시한다."""
        dashboard_page.locator("button", has_text="WDA 빌드").first.click()
        modal = dashboard_page.locator("#env-wda-build-modal")

        alerted = []
        dashboard_page.on("dialog", lambda d: (alerted.append(d.message), d.accept()))

        modal.locator("button", has_text="빌드 시작").click()
        assert len(alerted) == 1
        assert "입력하세요" in alerted[0]

    def test_wda_build_submit_calls_api(self, dashboard_page):
        """UDID·Team ID 입력 후 제출 시 /api/env/ios/real/wda_build를 호출한다."""
        api_called = []

        def _intercept(route, request):
            api_called.append(json.loads(request.post_data or "{}"))
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"ok": True, "pid": 9999}),
            )

        dashboard_page.route("**/api/env/ios/real/wda_build", _intercept)

        dashboard_page.locator("button", has_text="WDA 빌드").first.click()
        modal = dashboard_page.locator("#env-wda-build-modal")

        dashboard_page.fill("#env-wda-udid", "00008120-001A44981688001C")
        dashboard_page.fill("#env-wda-teamid", "ABCD123456")

        modal.locator("button", has_text="빌드 시작").click()

        deadline = time.time() + 2
        while not api_called and time.time() < deadline:
            time.sleep(0.1)

        assert len(api_called) == 1
        body = api_called[0]
        assert body.get("udid") == "00008120-001A44981688001C"
        assert body.get("team_id") == "ABCD123456"

    def test_wda_build_success_shows_feedback(self, dashboard_page):
        """API 성공 응답 시 결과 div에 성공 메시지가 표시된다."""
        dashboard_page.locator("button", has_text="WDA 빌드").first.click()
        dashboard_page.fill("#env-wda-udid", "00008120-001A44981688001C")
        dashboard_page.fill("#env-wda-teamid", "ABCD123456")

        modal = dashboard_page.locator("#env-wda-build-modal")
        modal.locator("button", has_text="빌드 시작").click()

        result = dashboard_page.locator("#env-wda-result")
        dashboard_page.wait_for_function(
            "document.getElementById('env-wda-result').style.display !== 'none'",
            timeout=3000,
        )
        text = result.text_content()
        assert "WDA" in text or "빌드" in text or "PID" in text or "9999" in text


# ── 버튼 레이아웃 공통 검증 ──────────────────────────────────────

class TestPhase3ButtonLayout:

    def test_android_real_buttons_in_same_row(self, dashboard_page):
        """Android 실기기 ＋추가·WiFi 페어링 버튼이 같은 flex 컨테이너에 있다."""
        add_btn = dashboard_page.locator("button[onclick=\"envShowAddModal('android','real_device')\"]")
        wifi_btn = dashboard_page.locator("button[onclick='envShowWifiPairModal()']")
        assert add_btn.count() == 1
        assert wifi_btn.count() == 1

        add_parent = add_btn.evaluate("el => el.parentElement.id || el.parentElement.className")
        wifi_parent = wifi_btn.evaluate("el => el.parentElement.id || el.parentElement.className")
        # 같은 부모
        assert add_parent == wifi_parent

    def test_ios_real_buttons_in_same_row(self, dashboard_page):
        """iOS 실기기 ＋추가·WDA 빌드 버튼이 같은 flex 컨테이너에 있다."""
        add_btn = dashboard_page.locator("button[onclick=\"envShowAddModal('ios','real_device')\"]")
        wda_btn = dashboard_page.locator("button[onclick='envShowWdaBuildModal()']")
        assert add_btn.count() == 1
        assert wda_btn.count() == 1

        add_parent = add_btn.evaluate("el => el.parentElement.id || el.parentElement.className")
        wda_parent = wda_btn.evaluate("el => el.parentElement.id || el.parentElement.className")
        assert add_parent == wda_parent
