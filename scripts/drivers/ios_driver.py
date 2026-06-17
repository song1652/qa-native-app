"""iOS Appium driver factory."""
import json
import subprocess
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def _check_device_connected(mode: str = "simulator") -> None:
    if mode == "simulator":
        result = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "booted"],
            capture_output=True, text=True
        )
        if "Booted" not in result.stdout:
            raise RuntimeError(
                "[ios_driver] No booted simulator found. "
                "Run: xcrun simctl boot <device_udid>"
            )
    elif mode == "real_device":
        result = subprocess.run(
            ["idevice_id", "-l"],
            capture_output=True, text=True
        )
        if not result.stdout.strip():
            raise RuntimeError(
                "[ios_driver] No iOS real device connected. "
                "Check USB connection and trust settings."
            )


def get_capabilities(mode: str = "simulator") -> dict:
    devices = json.loads((CONFIG_DIR / "devices.json").read_text())
    test_data = json.loads((CONFIG_DIR / "test_data.json").read_text())
    caps = devices["ios"][mode].copy()
    caps["platformName"] = "iOS"
    caps["bundleId"] = test_data["app"]["ios"]["bundle_id"]
    app_path = test_data["app"]["ios"]["app_path"]
    if app_path:
        caps["app"] = app_path
    return caps


def create_driver(appium_url: str = "http://localhost:4723", mode: str = "simulator"):
    from appium import webdriver
    from appium.options.ios import XCUITestOptions

    _check_device_connected(mode)

    caps = get_capabilities(mode)
    options = XCUITestOptions().load_capabilities(caps)
    return webdriver.Remote(appium_url, options=options)
