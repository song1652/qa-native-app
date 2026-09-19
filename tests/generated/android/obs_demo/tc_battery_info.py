"""
TC: 배터리 정보 화면 진입 확인 (obs_demo — 관측성 기능 검증용)

실제 Appium 연결 없이 실행 가능한 관측성 파이프라인 검증 TC.
conftest.py 훅이 실행되어 manifest에 결과가 기록된다.
"""
import time


class TestBatteryInfo:
    """배터리 정보 화면 TC (PASS 케이스)"""

    def test_battery_info_visible(self):
        """배터리 화면 진입 — 항상 성공하는 케이스."""
        # 실제 기기 테스트 시뮬레이션: 약간의 지연 후 단언
        time.sleep(0.5)

        # 관측성 검증: 이 TC는 항상 PASS
        battery_level = 87  # 시뮬레이션 값
        assert battery_level > 0, "Battery level should be > 0"
        assert battery_level <= 100, "Battery level should be <= 100"

        # 추가 검증
        battery_status = "Charging"
        assert battery_status in ("Charging", "Discharging", "Full"), \
            f"Unexpected battery status: {battery_status}"
