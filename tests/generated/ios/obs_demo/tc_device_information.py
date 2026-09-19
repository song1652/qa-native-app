"""iOS device information PASS case for the observability demo."""
import time


class TestDeviceInformation:
    def test_device_information_visible(self):
        """Represent a successful Settings device-information assertion."""
        time.sleep(0.5)

        device_name = "iPhone Simulator"
        platform_name = "iOS"
        assert device_name.startswith("iPhone")
        assert platform_name == "iOS"
