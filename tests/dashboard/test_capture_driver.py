"""Capture driver adapter contracts that do not require a device."""

from agents.dashboard.utils.capture_driver import friendly_appium_error


def test_friendly_appium_error_maps_common_operator_failures():
    assert friendly_appium_error(ConnectionError("ECONNREFUSED")) == (
        "Appium 서버에 연결할 수 없습니다. 터미널에서 "
        "'appium --address 127.0.0.1 --port 4723'을 먼저 실행하세요."
    )
    assert "디바이스" in friendly_appium_error(RuntimeError("no device found"))
    assert "XCUITest" in friendly_appium_error(RuntimeError("xcuitest driver not installed"))


def test_friendly_appium_error_limits_unknown_message_to_first_line():
    message = "Message: " + "x" * 240 + "\nstack trace"

    assert friendly_appium_error(RuntimeError(message)) == "x" * 200
