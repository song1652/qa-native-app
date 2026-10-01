import json
from pathlib import Path
from types import SimpleNamespace

from tests.generated import conftest


def test_device_override_remains_valid_on_pytest_rerun(monkeypatch, tmp_path):
    config = tmp_path / "devices.json"
    config.write_text(json.dumps({"android": {"emulator": [
        {"udid": "emulator-5554", "default": True},
    ]}}), encoding="utf-8")
    namespace = {
        "CONFIG_DIR": tmp_path,
        "_load_json": lambda path: json.loads(Path(path).read_text()),
    }
    exec("def _get_device(platform, mode): return {}", namespace)
    module = SimpleNamespace(_get_device=namespace["_get_device"], PLATFORM_MODE="emulator")
    item = SimpleNamespace(module=module)
    monkeypatch.setenv("DEVICE_MODE", "emulator")
    monkeypatch.setenv("DEVICE_UDID", "emulator-5554")

    conftest.pytest_runtest_setup(item)
    conftest.pytest_runtest_setup(item)

    assert module._get_device("android", "emulator")["udid"] == "emulator-5554"
