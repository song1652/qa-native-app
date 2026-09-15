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


def _get_default_device(platform: str, mode: str) -> dict:
    """devices.json에서 default:true 항목 반환 (배열·dict 모두 호환)."""
    data = json.loads((CONFIG_DIR / "devices.json").read_text(encoding="utf-8"))
    section = data.get(platform, {}).get(mode)
    if isinstance(section, dict):
        return section
    if isinstance(section, list):
        for item in section:
            if item.get("default"):
                return item
        return section[0] if section else {}
    return {}


_NON_APPIUM_KEYS = frozenset({"default", "wifi_ip", "team_id", "label", "note"})


def _filter_appium_caps(device: dict) -> dict:
    """devices.json 항목에서 Appium 비전달 필드를 제거한 caps dict 반환."""
    return {k: v for k, v in device.items() if k not in _NON_APPIUM_KEYS}


def get_capabilities(mode: str = "emulator") -> dict:
    test_data = json.loads((CONFIG_DIR / "test_data.json").read_text(encoding="utf-8"))
    raw = _get_default_device("android", mode)
    caps = _filter_appium_caps(raw)
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
