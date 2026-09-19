"""Pure projections for configured and connected mobile devices."""

from collections.abc import Mapping, Sequence
from typing import Any


Device = dict[str, Any]


def normalize_device_list(value: Any) -> list[Device]:
    """Normalize current lists and the legacy single-device mapping format."""
    if isinstance(value, Mapping):
        return [dict(value)]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def configured_android_rows(configured: Any, runtime: Mapping[str, Any]) -> list[Device]:
    rows = []
    for device in normalize_device_list(configured):
        active = bool(device.get("avd")) and device.get("avd") == runtime.get("avd")
        rows.append({
            **device,
            "status": runtime.get("status", "stopped") if active else "stopped",
            "serial": runtime.get("serial") if active else None,
        })
    return rows


def configured_ios_rows(configured: Any, runtime: Mapping[str, Any]) -> list[Device]:
    rows = []
    for device in normalize_device_list(configured):
        active = bool(device.get("udid")) and device.get("udid") == runtime.get("udid")
        status = runtime.get("status", "stopped") if active else "stopped"
        rows.append({
            **device,
            "status": status,
            "state": "Booted" if status == "running" else "Shutdown",
        })
    return rows


def real_device_rows(
    android_devices: Any,
    ios_devices: Any,
    android_connected: Mapping[str, bool],
    ios_connected: Mapping[str, bool],
) -> tuple[list[Device], list[Device]]:
    android_rows = [
        {
            "deviceName": device.get("deviceName", ""),
            "serial": device.get("udid", ""),
            "connected": android_connected.get(device.get("udid", ""), False),
            "wifi_ip": device.get("wifi_ip", ""),
        }
        for device in normalize_device_list(android_devices)
    ]
    ios_rows = [
        {
            "deviceName": device.get("deviceName", ""),
            "udid": device.get("udid", ""),
            "connected": ios_connected.get(device.get("udid", ""), False),
        }
        for device in normalize_device_list(ios_devices)
    ]
    return android_rows, ios_rows
