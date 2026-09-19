"""
TC: Wi-Fi 토글 동작 확인 (obs_demo — 관측성 기능 검증용)

실제 Appium 연결 없이 실행 가능한 관측성 파이프라인 검증 TC.
이 TC는 의도적으로 FAIL하여 로그·영상 아티팩트 보존을 검증한다.
"""
import time


class TestWifiToggle:
    """Wi-Fi 토글 TC (FAIL 케이스 — 관측성 아티팩트 보존 확인용)"""

    def test_wifi_toggle_state(self):
        """Wi-Fi 토글 상태 확인 — 의도적으로 실패하는 케이스."""
        time.sleep(0.8)

        # 실패 시나리오: UI 요소를 찾지 못한 상황 시뮬레이션
        wifi_element_found = False  # 에뮬레이터/기기 없어서 False
        assert wifi_element_found, (
            "Wi-Fi toggle element not found. "
            "Expected resource-id='com.android.settings:id/switch_widget' "
            "to be present in Network & internet screen. "
            "Actual: element not located after 10s timeout."
        )
