"""
런타임 디바이스 오버라이드 — DEVICE_MODE / DEVICE_UDID env var를 읽어
생성 파일의 PLATFORM_MODE 모듈 상수를 교체하고 _get_device를 패치합니다.
"""
import os


def pytest_runtest_setup(item):
    device_mode = os.environ.get("DEVICE_MODE")
    device_udid = os.environ.get("DEVICE_UDID")
    if not device_mode and not device_udid:
        return

    mod = item.module

    if device_mode and hasattr(mod, "PLATFORM_MODE"):
        mod.PLATFORM_MODE = device_mode

    if device_udid and hasattr(mod, "_get_device"):
        _orig = mod._get_device

        def _patched(platform, mode):
            override_mode = os.environ.get("DEVICE_MODE", mode)
            uid = os.environ.get("DEVICE_UDID", "")
            devs = _orig.__globals__["_load_json"](
                _orig.__globals__["CONFIG_DIR"] / "devices.json"
            ).get(platform, {}).get(override_mode, {})
            if isinstance(devs, dict):
                return devs
            if isinstance(devs, list):
                if uid:
                    match = next((d for d in devs if d.get("udid") == uid), None)
                    if match:
                        return match
                return next((d for d in devs if d.get("default")), devs[0] if devs else {})
            return {}

        mod._get_device = _patched
