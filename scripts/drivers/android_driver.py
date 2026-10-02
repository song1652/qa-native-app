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


def _get_default_device(platform: str, mode: str, config_dir: Path | None = None, udid: str = "") -> dict:
    """devices.json에서 default:true 항목 반환 (배열·dict 모두 호환)."""
    data = json.loads(((config_dir or CONFIG_DIR) / "devices.json").read_text(encoding="utf-8"))
    section = data.get(platform, {}).get(mode)
    if isinstance(section, dict):
        return section
    if isinstance(section, list):
        if udid:
            selected = next((item for item in section if item.get("udid") == udid), None)
            if selected is not None:
                return selected
        for item in section:
            if item.get("default"):
                return item
        return section[0] if section else {}
    return {}


_NON_APPIUM_KEYS = frozenset({"default", "wifi_ip", "team_id", "label", "note"})


def _filter_appium_caps(device: dict) -> dict:
    """devices.json 항목에서 Appium 비전달 필드를 제거한 caps dict 반환."""
    return {k: v for k, v in device.items() if k not in _NON_APPIUM_KEYS}


def get_capabilities(mode: str = "emulator", udid: str = "") -> dict:
    if mode not in ("emulator", "real_device"):
        raise ValueError(f"Invalid Android device mode: {mode}")
    test_data = json.loads((CONFIG_DIR / "test_data.json").read_text(encoding="utf-8"))
    raw = _get_default_device("android", mode, udid=udid)
    caps = _filter_appium_caps(raw)
    if udid:
        caps["udid"] = udid
        # An explicitly selected running emulator must not launch the default AVD.
        caps.pop("avd", None)
    caps["platformName"] = "Android"
    caps["appPackage"] = test_data["app"]["android"]["package"]
    caps["appActivity"] = test_data["app"]["android"]["activity"]
    app_path = test_data["app"]["android"]["app_path"]
    if app_path:
        caps["app"] = app_path
    return caps


def create_driver(appium_url: str = "http://localhost:4723", mode: str = "emulator", udid: str = ""):
    from appium import webdriver
    from appium.options.android.uiautomator2.base import UiAutomator2Options

    caps = get_capabilities(mode, udid)
    selected = caps.get("udid", "")
    virtual = mode == "emulator"
    if selected and selected.startswith("emulator-") != virtual:
        raise RuntimeError("Selected Android device does not match requested mode")
    result = subprocess.run([ADB, "devices"], capture_output=True, text=True, timeout=8)
    candidates = [parts[0] for line in result.stdout.splitlines()
                  if len(parts := line.split()) >= 2 and parts[1] == "device"
                  and parts[0].startswith("emulator-") == virtual]
    if selected:
        candidates = [serial for serial in candidates if serial == selected]
    elif virtual and caps.get("avd"):
        candidates = [serial for serial in candidates if subprocess.run(
            [ADB, "-s", serial, "emu", "avd", "name"], capture_output=True,
            text=True, timeout=8,
        ).stdout.splitlines()[:1] == [caps["avd"]]]
    if len(candidates) != 1:
        raise RuntimeError("Selected Android device unavailable or ambiguous; specify an exact UDID")
    caps["udid"] = candidates[0]
    options = UiAutomator2Options().load_capabilities(caps)
    return webdriver.Remote(appium_url, options=options)
