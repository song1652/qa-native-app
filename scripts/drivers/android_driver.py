"""Android Appium driver factory."""
import json
import os
import shutil
import subprocess
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def _find_adb() -> str:
    candidates = [
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
        "/usr/local/bin/adb",
        shutil.which("adb") or "",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return "adb"

ADB = _find_adb()


def check_device_connected() -> bool:
    result = subprocess.run([ADB, "devices"], capture_output=True, text=True)
    lines = result.stdout.strip().splitlines()
    connected = [l for l in lines[1:] if l.strip() and "offline" not in l]
    return len(connected) > 0


def get_capabilities(mode: str = "emulator") -> dict:
    devices = json.loads((CONFIG_DIR / "devices.json").read_text())
    test_data = json.loads((CONFIG_DIR / "test_data.json").read_text())
    caps = devices["android"][mode].copy()
    caps["platformName"] = "Android"
    caps["appPackage"] = test_data["app"]["android"]["package"]
    caps["appActivity"] = test_data["app"]["android"]["activity"]
    app_path = test_data["app"]["android"]["app_path"]
    if app_path:
        caps["app"] = app_path
    return caps


def create_driver(appium_url: str = "http://localhost:4723", mode: str = "emulator"):
    from appium import webdriver
    from appium.options.android.uiautomator2.base import UiAutomator2Options

    if not check_device_connected():
        raise RuntimeError("Android device/emulator not connected. Run `adb devices` to verify.")

    caps = get_capabilities(mode)
    options = UiAutomator2Options().load_capabilities(caps)
    return webdriver.Remote(appium_url, options=options)
