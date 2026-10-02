"""Contracts for Capture Studio's actions-to-pytest generator."""
from datetime import datetime
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


DASHBOARD = Path(__file__).parents[2] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

from utils.capture_codegen import (  # noqa: E402
    CaptureCodegenValidationError,
    generate_test_from_actions,
)


@pytest.mark.parametrize(
    ("platform", "identity"),
    [
        ("android", {"app_pkg": "com.android.settings", "app_activity": ".Settings"}),
        ("ios", {"bundle_id": "com.apple.Preferences"}),
    ],
)
def test_generate_test_from_actions_writes_compilable_pytest(
    tmp_path, platform, identity
):
    body = {
        "tc_id": f"tc_{platform}_generated",
        "title": "Generated smoke test",
        "platform": platform,
        "tc_group": "capture_codegen",
        "actions": [{"type": "wait", "wait_seconds": 0}],
        **identity,
    }

    result = generate_test_from_actions(
        body,
        {},
        tmp_path,
        generated_at=datetime(2026, 9, 18, 12, 0),
    )

    output_path = tmp_path / result["file"]
    assert result["ok"] is True
    assert output_path.read_text(encoding="utf-8") == result["code"]
    assert "자동 생성: Capture Studio (2026-09-18 12:00)" in result["code"]
    compile(result["code"], str(output_path), "exec")


def test_generate_test_from_actions_rejects_invalid_platform(tmp_path):
    with pytest.raises(
        CaptureCodegenValidationError,
        match="tc_id와 platform이 필요합니다",
    ):
        generate_test_from_actions(
            {"tc_id": "tc_invalid", "platform": "windows"},
            {},
            tmp_path,
        )


def test_generate_test_from_actions_rejects_empty_executable_actions(tmp_path):
    with pytest.raises(
        CaptureCodegenValidationError,
        match="실행 가능한 액션이 하나 이상 필요합니다",
    ):
        generate_test_from_actions(
            {
                "tc_id": "tc_empty",
                "platform": "android",
                "actions": [],
            },
            {},
            tmp_path,
        )

    assert not (tmp_path / "tests" / "generated").exists()


def generated_driver_namespace(tmp_path, platform, session, devices):
    result = generate_test_from_actions(
        {"tc_id": "tc_identity", "platform": platform, "tc_group": "identity",
         "actions": [{"type": "wait", "wait_seconds": 0}]},
        {"app_package": "com.example", "app_activity": ".Main",
         "bundle_id": "com.example", **session}, tmp_path,
    )
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "devices.json").write_text(json.dumps(devices))
    tree = ast.parse(result["code"])
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom) and node.module.startswith(("appium", "selenium"))
    )]

    class Options:
        def load_capabilities(self, caps):
            return caps

    namespace = {
        "__file__": str(tmp_path / result["file"]),
        "webdriver": SimpleNamespace(Remote=lambda url, options: options),
        "UiAutomator2Options": Options, "XCUITestOptions": Options,
    }
    exec(compile(tree, "capture_generated", "exec"), namespace)
    return namespace


@pytest.mark.parametrize(("platform", "target", "uid", "mode"), [
    ("android", "emulator", "emulator-5560", "emulator"),
    ("android", "device", "usb-selected", "real_device"),
    ("ios", "emulator", "selected-simulator", "simulator"),
    ("ios", "device", "selected-iphone", "real_device"),
])
def test_generated_driver_retains_captured_kind_and_identity(
    monkeypatch, tmp_path, platform, target, uid, mode,
):
    monkeypatch.delenv("DEVICE_MODE", raising=False)
    monkeypatch.delenv("DEVICE_UDID", raising=False)
    namespace = generated_driver_namespace(tmp_path, platform,
        {"target": target, "udid": uid},
        {platform: {mode: [{"default": True, "udid": "another-device", "avd": "OtherAVD"}]}},
    )
    caps = namespace["_build_driver"]()
    assert namespace["PLATFORM_MODE"] == mode
    assert caps["udid"] == uid
    assert "avd" not in caps


def test_generated_driver_allows_explicit_run_device_override(monkeypatch, tmp_path):
    monkeypatch.setenv("DEVICE_MODE", "real_device")
    monkeypatch.setenv("DEVICE_UDID", "usb-run-choice")
    namespace = generated_driver_namespace(tmp_path, "android",
        {"target": "emulator", "udid": "emulator-5560"},
        {"android": {"emulator": [{"avd": "RecordedAVD"}],
                     "real_device": [{"udid": "usb-default"}]}},
    )
    assert namespace["_build_driver"]()["udid"] == "usb-run-choice"


def test_generated_driver_blocks_unidentified_real_device(monkeypatch, tmp_path):
    monkeypatch.delenv("DEVICE_MODE", raising=False)
    monkeypatch.delenv("DEVICE_UDID", raising=False)
    namespace = generated_driver_namespace(tmp_path, "android", {"target": "device"},
        {"android": {"real_device": [{"deviceName": "Phone"}],
                     "emulator": [{"avd": "OtherAVD"}]}},
    )
    with pytest.raises(RuntimeError, match="기기"):
        namespace["_build_driver"]()


@pytest.mark.parametrize(("target", "uid"), [
    ("emulator", "usb-phone"), ("device", "emulator-5554"),
])
def test_generated_driver_blocks_android_identity_of_opposite_kind(
    monkeypatch, tmp_path, target, uid,
):
    monkeypatch.delenv("DEVICE_MODE", raising=False)
    monkeypatch.delenv("DEVICE_UDID", raising=False)
    namespace = generated_driver_namespace(tmp_path, "android",
        {"target": target, "udid": uid}, {"android": {}},
    )
    with pytest.raises(RuntimeError, match="종류"):
        namespace["_build_driver"]()


def test_generated_driver_runtime_override_survives_pytest_hook(monkeypatch, tmp_path):
    from tests.generated.conftest import pytest_runtest_setup

    monkeypatch.setenv("DEVICE_MODE", "emulator")
    monkeypatch.setenv("DEVICE_UDID", "emulator-5560")
    namespace = generated_driver_namespace(tmp_path, "android",
        {"target": "device", "udid": "usb-captured"},
        {"android": {"emulator": [{"avd": "DefaultAVD", "default": True}]}},
    )
    module = SimpleNamespace(**namespace)
    pytest_runtest_setup(SimpleNamespace(module=module))
    namespace["_get_device"] = module._get_device
    namespace["PLATFORM_MODE"] = module.PLATFORM_MODE
    caps = namespace["_build_driver"]()
    assert caps["udid"] == "emulator-5560"
    assert "avd" not in caps
