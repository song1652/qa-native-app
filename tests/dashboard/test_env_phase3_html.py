"""
Phase 3 대시보드 HTML 정적 검증 테스트.

브라우저 없이 dashboard.html 소스를 직접 파싱해 Phase 3 UI 요소가
존재하는지 확인합니다.
- WiFi 페어링 모달 (Android 실기기)
- WDA 빌드 모달 (iOS 실기기)
- 버튼 flex:none 스타일
"""
from pathlib import Path

import pytest

_DASHBOARD_HTML_PATH = Path(__file__).parents[2] / "agents" / "dashboard" / "dashboard.html"
HTML = _DASHBOARD_HTML_PATH.read_text(encoding="utf-8")


# ── Phase 3 Android 실기기 UI ───────────────────────────────────

class TestPhase3AndroidRealHtml:

    def test_wifi_pair_button_present(self):
        """Android 실기기 카드에 WiFi 페어링 버튼이 있다."""
        assert "envShowWifiPairModal()" in HTML

    def test_wifi_pair_button_has_flex_none(self):
        """WiFi 페어링 버튼은 flex:none 스타일을 가진다 (레이아웃 버그 방지)."""
        # 버튼 정의 찾기
        idx = HTML.find("envShowWifiPairModal()")
        assert idx != -1
        # 해당 버튼 태그 앞 200자 안에 flex:none이 있어야 함
        btn_ctx = HTML[max(0, idx - 200):idx]
        assert "flex:none" in btn_ctx, "WiFi 페어링 버튼에 flex:none 스타일이 없음"

    def test_wifi_pair_modal_div_present(self):
        """env-wifi-pair-modal 모달 div가 존재한다."""
        assert 'id="env-wifi-pair-modal"' in HTML

    def test_wifi_pair_modal_has_ip_field(self):
        """WiFi 페어링 모달에 IP 입력 필드가 있다."""
        assert 'id="env-pair-ip"' in HTML

    def test_wifi_pair_modal_has_port_field(self):
        """WiFi 페어링 모달에 포트 입력 필드가 있다."""
        assert 'id="env-pair-port"' in HTML

    def test_wifi_pair_modal_has_code_field(self):
        """WiFi 페어링 모달에 페어링 코드 입력 필드가 있다."""
        assert 'id="env-pair-code"' in HTML

    def test_wifi_pair_modal_has_result_div(self):
        """WiFi 페어링 모달에 결과 표시 div가 있다."""
        assert 'id="env-pair-result"' in HTML

    def test_wifi_pair_api_endpoint(self):
        """envSubmitWifiPair가 /api/env/android/real/pair를 호출한다."""
        assert "/api/env/android/real/pair" in HTML

    def test_show_wifi_pair_modal_function(self):
        """envShowWifiPairModal 함수가 정의되어 있다."""
        assert "function envShowWifiPairModal()" in HTML

    def test_close_wifi_pair_modal_function(self):
        """envCloseWifiPairModal 함수가 정의되어 있다."""
        assert "function envCloseWifiPairModal()" in HTML

    def test_submit_wifi_pair_function(self):
        """envSubmitWifiPair 함수가 정의되어 있다."""
        assert "function envSubmitWifiPair()" in HTML

    def test_android_real_add_button_has_flex_none(self):
        """Android 실기기 ＋추가 버튼도 flex:none을 가진다."""
        # ＋추가 버튼과 WiFi 페어링 버튼이 같은 div에 있음
        idx = HTML.find("envShowAddModal('android','real_device')")
        assert idx != -1
        btn_ctx = HTML[max(0, idx - 200):idx]
        assert "flex:none" in btn_ctx, "Android 실기기 ＋추가 버튼에 flex:none 스타일이 없음"


# ── Phase 3 iOS 실기기 UI ────────────────────────────────────────

class TestPhase3IosRealHtml:

    def test_wda_build_button_present(self):
        """iOS 실기기 카드에 WDA 빌드 버튼이 있다."""
        assert "envShowWdaBuildModal()" in HTML

    def test_wda_build_button_has_flex_none(self):
        """WDA 빌드 버튼은 flex:none 스타일을 가진다 (레이아웃 버그 방지)."""
        idx = HTML.find("envShowWdaBuildModal()")
        assert idx != -1
        btn_ctx = HTML[max(0, idx - 200):idx]
        assert "flex:none" in btn_ctx, "WDA 빌드 버튼에 flex:none 스타일이 없음"

    def test_wda_build_modal_div_present(self):
        """env-wda-build-modal 모달 div가 존재한다."""
        assert 'id="env-wda-build-modal"' in HTML

    def test_wda_build_modal_has_udid_field(self):
        """WDA 빌드 모달에 UDID 입력 필드가 있다."""
        assert 'id="env-wda-udid"' in HTML

    def test_wda_build_modal_has_teamid_field(self):
        """WDA 빌드 모달에 Team ID 입력 필드가 있다."""
        assert 'id="env-wda-teamid"' in HTML

    def test_wda_build_modal_has_result_div(self):
        """WDA 빌드 모달에 결과 표시 div가 있다."""
        assert 'id="env-wda-result"' in HTML

    def test_wda_build_api_endpoint(self):
        """envSubmitWdaBuild가 /api/env/ios/real/wda_build를 호출한다."""
        assert "/api/env/ios/real/wda_build" in HTML

    def test_show_wda_build_modal_function(self):
        """envShowWdaBuildModal 함수가 정의되어 있다."""
        assert "function envShowWdaBuildModal()" in HTML

    def test_close_wda_build_modal_function(self):
        """envCloseWdaBuildModal 함수가 정의되어 있다."""
        assert "function envCloseWdaBuildModal()" in HTML

    def test_submit_wda_build_function(self):
        """envSubmitWdaBuild 함수가 정의되어 있다."""
        assert "function envSubmitWdaBuild()" in HTML

    def test_ios_real_add_button_has_flex_none(self):
        """iOS 실기기 ＋추가 버튼도 flex:none을 가진다."""
        idx = HTML.find("envShowAddModal('ios','real_device')")
        assert idx != -1
        btn_ctx = HTML[max(0, idx - 200):idx]
        assert "flex:none" in btn_ctx, "iOS 실기기 ＋추가 버튼에 flex:none 스타일이 없음"


# ── Phase 3 요청 본문 구조 ────────────────────────────────────────

class TestPhase3ApiRequestBody:

    def test_wifi_pair_sends_ip_port_code(self):
        """WiFi 페어링 요청이 ip, port, code 필드를 포함한다."""
        assert "ip: ip" in HTML
        assert "port: port" in HTML
        assert "code: code" in HTML

    def test_wda_build_sends_udid_team_id(self):
        """WDA 빌드 요청이 udid, team_id 필드를 포함한다."""
        assert "udid: udid" in HTML
        assert "team_id: teamId" in HTML

    def test_wifi_pair_validates_required_fields(self):
        """WiFi 페어링은 ip/port/code 미입력 시 early return한다."""
        assert "IP, 포트, 코드를 모두 입력하세요" in HTML

    def test_wda_build_validates_required_fields(self):
        """WDA 빌드는 udid/teamId 미입력 시 early return한다."""
        assert "UDID와 Team ID를 모두 입력하세요" in HTML

    def test_wifi_pair_uses_post_method(self):
        """WiFi 페어링 fetch 호출은 POST 메서드를 사용한다."""
        # fetch('/api/env/android/real/pair', { method: 'POST', ... })
        idx = HTML.find("/api/env/android/real/pair")
        assert idx != -1
        ctx = HTML[idx:idx + 200]
        assert "POST" in ctx

    def test_wda_build_uses_post_method(self):
        """WDA 빌드 fetch 호출은 POST 메서드를 사용한다."""
        idx = HTML.find("/api/env/ios/real/wda_build")
        assert idx != -1
        ctx = HTML[idx:idx + 200]
        assert "POST" in ctx


# ── Phase 3 성공/실패 피드백 ─────────────────────────────────────

class TestPhase3FeedbackMessages:

    def test_wifi_pair_success_feedback(self):
        """WiFi 페어링 성공 시 결과 메시지를 표시한다."""
        assert "페어링 성공" in HTML

    def test_wifi_pair_failure_feedback(self):
        """WiFi 페어링 실패 시 에러 메시지를 표시한다."""
        assert "페어링 실패" in HTML

    def test_wda_build_success_feedback(self):
        """WDA 빌드 성공 시 결과 메시지를 표시한다."""
        assert "WDA 빌드 시작됨" in HTML

    def test_wifi_pair_auto_close_on_success(self):
        """WiFi 페어링 성공 후 모달을 자동으로 닫는다."""
        assert "envCloseWifiPairModal" in HTML
        # setTimeout으로 auto-close
        assert "setTimeout" in HTML
