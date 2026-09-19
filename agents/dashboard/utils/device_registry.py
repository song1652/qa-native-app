"""Pure registration rules for Android and iOS device configuration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


class DeviceRegistryError(ValueError):
    def __init__(self, code: str, status_code: int = 400, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.detail = detail


def _section(data: dict, platform: str, mode: str) -> list[dict[str, Any]]:
    platform_data = data.setdefault(platform, {})
    current = platform_data.setdefault(mode, [])
    if isinstance(current, Mapping):
        current = [dict(current)]
        platform_data[mode] = current
    if not isinstance(current, list):
        current = []
        platform_data[mode] = current
    return current


def _raise_duplicate(key: str, value: str) -> None:
    raise DeviceRegistryError(
        f"duplicate_{key}",
        409,
        f"{key}={value} already exists",
    )


def _set_default(section: list[dict[str, Any]], entry: dict[str, Any], requested: Any) -> None:
    entry["default"] = bool(requested if requested is not None else not section)
    if entry["default"]:
        for item in section:
            item["default"] = False


def add_android_device(
    source: Mapping[str, Any],
    body: Mapping[str, Any],
    *,
    discovered: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = deepcopy(dict(source))
    mode = str(body.get("mode") or "").strip()
    if mode not in {"emulator", "real_device"}:
        raise DeviceRegistryError("mode must be emulator or real_device")
    section = _section(data, "android", mode)
    device_name = str((discovered or {}).get("deviceName") or body.get("deviceName") or "").strip()
    entry: dict[str, Any] = {"deviceName": device_name}

    if mode == "emulator":
        avd = str(body.get("avd") or "").strip()
        if any(item.get("avd") == avd for item in section):
            _raise_duplicate("avd", avd)
        entry.update({
            "avd": avd,
            "platformVersion": str(
                (discovered or {}).get("platformVersion")
                or body.get("platformVersion")
                or ""
            ).strip(),
            "automationName": "UiAutomator2",
            "noReset": True,
            "forceAppLaunch": True,
            "shouldTerminateApp": True,
            "mjpegServerPort": _next_mjpeg_port(section),
            "mjpegScalingFactor": 75,
            "mjpegServerScreenshotQuality": 70,
            "appPackage": "",
            "appActivity": "",
        })
    else:
        udid = str(body.get("udid") or "").strip()
        if any(item.get("udid") == udid for item in section):
            _raise_duplicate("udid", udid)
        entry.update({"udid": udid, "automationName": "UiAutomator2"})
        wifi_ip = str(body.get("wifi_ip") or "").strip()
        if wifi_ip:
            entry["wifi_ip"] = wifi_ip

    _set_default(section, entry, body.get("default"))
    section.append(entry)
    return data, entry


def _next_mjpeg_port(section: list[dict[str, Any]]) -> int:
    ports = [
        item.get("mjpegServerPort")
        for item in section
        if item.get("avd") and isinstance(item.get("mjpegServerPort"), int)
    ]
    return max(ports) + 1 if ports else 8093


def add_ios_device(
    source: Mapping[str, Any],
    body: Mapping[str, Any],
    *,
    discovered: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = deepcopy(dict(source))
    mode = str(body.get("mode") or "").strip()
    if mode not in {"simulator", "real_device"}:
        raise DeviceRegistryError("mode must be simulator or real_device")
    section = _section(data, "ios", mode)
    device_name = str((discovered or {}).get("deviceName") or body.get("deviceName") or "").strip()
    entry: dict[str, Any] = {"deviceName": device_name, "automationName": "XCUITest"}

    if mode == "simulator":
        udid = str((discovered or {}).get("udid") or body.get("udid") or "").strip()
        if any(str(item.get("udid") or "").upper() == udid.upper() for item in section):
            _raise_duplicate("udid", udid)
        if any(item.get("deviceName") == device_name for item in section):
            _raise_duplicate("deviceName", device_name)
        entry.update({
            "udid": udid,
            "platformVersion": str(
                (discovered or {}).get("platformVersion")
                or body.get("platformVersion")
                or ""
            ).strip(),
        })
    else:
        udid = str(body.get("udid") or "").strip()
        if any(item.get("udid") == udid for item in section):
            _raise_duplicate("udid", udid)
        entry["udid"] = udid
        team_id = str(body.get("team_id") or "").strip()
        if team_id:
            entry["team_id"] = team_id

    bundle_id = str(body.get("bundle_id") or "").strip()
    if bundle_id:
        entry["bundle_id"] = bundle_id
    _set_default(section, entry, body.get("default"))
    section.append(entry)
    return data, entry


def remove_device(
    source: Mapping[str, Any],
    platform: str,
    mode: str,
    device_name: str,
) -> dict[str, Any]:
    data = deepcopy(dict(source))
    section = _section(data, platform, mode)
    remaining = [item for item in section if item.get("deviceName") != device_name]
    if len(remaining) == len(section):
        raise DeviceRegistryError("device not found", 404)
    if mode != "real_device" and not remaining:
        raise DeviceRegistryError("last_device", 400)
    if remaining and not any(item.get("default") for item in remaining):
        remaining[0]["default"] = True
    data.setdefault(platform, {})[mode] = remaining
    return data
