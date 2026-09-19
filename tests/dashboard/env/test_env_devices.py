"""Environment device projection contracts."""

from agents.dashboard.utils.env_devices import (
    configured_android_rows,
    configured_ios_rows,
    normalize_device_list,
    real_device_rows,
)


def test_normalize_device_list_accepts_legacy_dict_and_rejects_other_values():
    assert normalize_device_list({"udid": "one"}) == [{"udid": "one"}]
    assert normalize_device_list([{"udid": "one"}, "bad", {"udid": "two"}]) == [
        {"udid": "one"},
        {"udid": "two"},
    ]
    assert normalize_device_list(None) == []


def test_configured_android_rows_marks_only_matching_runtime_active():
    rows = configured_android_rows(
        [{"avd": "Pixel_8"}, {"avd": "Pixel_Tablet"}],
        {"avd": "Pixel_8", "status": "running", "serial": "emulator-5554"},
    )

    assert rows == [
        {"avd": "Pixel_8", "status": "running", "serial": "emulator-5554"},
        {"avd": "Pixel_Tablet", "status": "stopped", "serial": None},
    ]


def test_configured_ios_rows_projects_boot_state():
    rows = configured_ios_rows(
        [{"udid": "BOOTED"}, {"udid": "OFF"}],
        {"udid": "BOOTED", "status": "running"},
    )

    assert rows == [
        {"udid": "BOOTED", "status": "running", "state": "Booted"},
        {"udid": "OFF", "status": "stopped", "state": "Shutdown"},
    ]


def test_real_device_rows_preserves_platform_specific_identifiers():
    android, ios = real_device_rows(
        [{"deviceName": "Galaxy", "udid": "R3CN", "wifi_ip": "10.0.0.2"}],
        [{"deviceName": "iPhone", "udid": "IOS-1"}],
        {"R3CN": True},
        {"IOS-1": False},
    )

    assert android == [{
        "deviceName": "Galaxy",
        "serial": "R3CN",
        "connected": True,
        "wifi_ip": "10.0.0.2",
    }]
    assert ios == [{"deviceName": "iPhone", "udid": "IOS-1", "connected": False}]
