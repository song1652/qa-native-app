"""iOS Wi-Fi toggle intentional failure for evidence collection."""
import time


class TestWifiToggle:
    def test_wifi_toggle_state(self):
        """Simulate a missing Wi-Fi switch in iOS Settings."""
        time.sleep(0.8)

        wifi_switch_found = False
        assert wifi_switch_found, (
            "iOS Wi-Fi switch not found. Expected accessibility label "
            "'Wi-Fi' in the Settings app; element lookup timed out."
        )
