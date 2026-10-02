"""iOS Appium driver factory."""
import json
import subprocess
from pathlib import Path

from .android_driver import _filter_appium_caps, _get_default_device

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def _check_device_connected(mode: str = "simulator", udid: str = "", device_name: str = "") -> str:
    if mode == "simulator":
        result = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "booted", "--json"],
            capture_output=True, text=True, timeout=8,
        )
        devices = [device for group in json.loads(result.stdout).get("devices", {}).values()
                   for device in group if device.get("state") == "Booted"
                   and device.get("isAvailable", True)]
        if udid:
            devices = [device for device in devices if device.get("udid") == udid]
        elif device_name:
            devices = [device for device in devices if device.get("name") == device_name]
        candidates = [device["udid"] for device in devices]
    elif mode == "real_device":
        result = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True, timeout=8)
        candidates = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if udid:
            candidates = [candidate for candidate in candidates if candidate == udid]
    else:
        raise ValueError(f"Invalid iOS device mode: {mode}")
    if len(candidates) != 1:
        raise RuntimeError("Selected iOS device unavailable or ambiguous; specify an exact UDID")
    return candidates[0]


def get_capabilities(mode: str = "simulator", udid: str = "") -> dict:
    if mode not in ("simulator", "real_device"):
        raise ValueError(f"Invalid iOS device mode: {mode}")
    test_data = json.loads((CONFIG_DIR / "test_data.json").read_text())
    caps = _filter_appium_caps(_get_default_device("ios", mode, CONFIG_DIR, udid))
    if udid:
        caps["udid"] = udid
    caps["platformName"] = "iOS"
    if "wdaLaunchTimeout" not in caps and "appium:wdaLaunchTimeout" not in caps:
        caps["wdaLaunchTimeout"] = 180000
    caps["bundleId"] = test_data["app"]["ios"]["bundle_id"]
    app_path = test_data["app"]["ios"]["app_path"]
    if app_path:
        caps["app"] = app_path
    return caps


def create_driver(appium_url: str = "http://localhost:4723", mode: str = "simulator", udid: str = ""):
    from appium import webdriver
    from appium.options.ios import XCUITestOptions

    caps = get_capabilities(mode, udid)
    caps["udid"] = _check_device_connected(mode, caps.get("udid", ""), caps.get("deviceName", ""))
    options = XCUITestOptions().load_capabilities(caps)
    return webdriver.Remote(appium_url, options=options)
