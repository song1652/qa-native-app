"""iOS display brightness intentional failure for evidence collection."""
import time


class TestDisplayBrightness:
    def test_display_brightness_slider_exists(self):
        """Simulate an XCUITest/WDA lookup failure."""
        time.sleep(0.3)

        raise ConnectionError(
            "XCUITest WebDriverAgent connection failed while locating the "
            "Display & Brightness slider on the iOS Simulator."
        )
