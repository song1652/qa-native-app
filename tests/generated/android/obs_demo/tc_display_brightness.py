"""
TC: 화면 밝기 슬라이더 존재 확인 (obs_demo — 관측성 기능 검증용)

실제 Appium 연결 없이 실행 가능한 관측성 파이프라인 검증 TC.
이 TC는 FAIL하여 Error 타입 예외를 발생시킨다 (error outcome 테스트).
"""
import time


class TestDisplayBrightness:
    """화면 밝기 TC (ERROR 케이스 — error outcome 관측성 확인용)"""

    def test_brightness_slider_exists(self):
        """밝기 슬라이더 존재 확인 — 예외(error) 발생 케이스."""
        time.sleep(0.3)

        # 연결 실패 시뮬레이션 — ConnectionError
        raise ConnectionError(
            "Appium server connection failed: "
            "Could not connect to http://127.0.0.1:4723. "
            "Make sure Appium server is running with: appium --address 127.0.0.1 --port 4723"
        )
