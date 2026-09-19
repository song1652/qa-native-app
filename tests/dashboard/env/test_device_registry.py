"""Pure mobile-device registry domain rules."""

import pytest

from agents.dashboard.utils.device_registry import (
    DeviceRegistryError,
    add_android_device,
    add_ios_device,
    remove_device,
)


def test_add_android_emulator_assigns_caps_port_and_default_without_mutating_input():
    original = {
        "android": {
            "emulator": [{
                "deviceName": "Pixel 7",
                "avd": "Pixel_7",
                "mjpegServerPort": 8093,
                "default": True,
            }]
        }
    }
    updated, entry = add_android_device(
        original,
        {
            "mode": "emulator",
            "deviceName": "Pixel 8",
            "avd": "Pixel_8",
            "platformVersion": "15",
            "default": True,
        },
        discovered={"deviceName": "Pixel 8 API 35", "platformVersion": "15"},
    )

    assert original["android"]["emulator"][0]["default"] is True
    assert updated["android"]["emulator"][0]["default"] is False
    assert entry["avd"] == "Pixel_8"
    assert entry["mjpegServerPort"] == 8094
    assert entry["automationName"] == "UiAutomator2"
    assert entry["default"] is True


def test_add_android_rejects_duplicate_identifier():
    data = {"android": {"real_device": [{"udid": "R3CN"}]}}

    with pytest.raises(DeviceRegistryError) as error:
        add_android_device(
            data,
            {"mode": "real_device", "deviceName": "Galaxy", "udid": "R3CN"},
        )

    assert (error.value.code, error.value.status_code) == ("duplicate_udid", 409)


def test_add_ios_simulator_uses_discovered_identity():
    updated, entry = add_ios_device(
        {"ios": {"simulator": []}},
        {
            "mode": "simulator",
            "deviceName": "requested",
            "udid": "00000000-0000-0000-0000-000000000001",
            "platformVersion": "18.0",
        },
        discovered={
            "deviceName": "iPhone 16",
            "udid": "00000000-0000-0000-0000-000000000001",
            "platformVersion": "18.0",
        },
    )

    assert updated["ios"]["simulator"] == [entry]
    assert entry == {
        "deviceName": "iPhone 16",
        "automationName": "XCUITest",
        "udid": "00000000-0000-0000-0000-000000000001",
        "platformVersion": "18.0",
        "default": True,
    }


def test_remove_device_reassigns_default_and_protects_last_virtual_device():
    data = {
        "android": {
            "emulator": [
                {"deviceName": "one", "default": True},
                {"deviceName": "two", "default": False},
            ]
        }
    }

    updated = remove_device(data, "android", "emulator", "one")
    assert updated["android"]["emulator"] == [{"deviceName": "two", "default": True}]

    with pytest.raises(DeviceRegistryError) as error:
        remove_device(updated, "android", "emulator", "two")
    assert (error.value.code, error.value.status_code) == ("last_device", 400)


def test_remove_real_device_allows_empty_section():
    data = {"ios": {"real_device": [{"deviceName": "phone", "default": True}]}}

    updated = remove_device(data, "ios", "real_device", "phone")

    assert updated["ios"]["real_device"] == []
