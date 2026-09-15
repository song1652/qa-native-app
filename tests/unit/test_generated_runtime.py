import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from scripts.generated_runtime import reset_to_start, select_device


class _SwitchTo:
    def __init__(self, calls):
        self.calls = calls

    def context(self, name):
        self.calls.append(("context", name))


class _Driver:
    def __init__(self, platform):
        self.calls = []
        self.current_context = "WEBVIEW_1"
        self.current_package = "com.google.android.settings.intelligence"
        self.switch_to = _SwitchTo(self.calls)
        self.platform = platform

    def terminate_app(self, app_id):
        self.calls.append(("terminate", app_id))

    def activate_app(self, app_id):
        self.calls.append(("activate", app_id))

    def execute_script(self, name, args):
        self.calls.append((name, args))


def test_select_device_accepts_list_and_prefers_default(tmp_path):
    path = tmp_path / "devices.json"
    path.write_text(
        '{"android":{"emulator":[{"udid":"first"},{"udid":"chosen","default":true}]}}',
        encoding="utf-8",
    )

    assert select_device(path, "android", "emulator")["udid"] == "chosen"


def test_android_reset_closes_companion_package_and_starts_exact_activity(monkeypatch):
    driver = _Driver("android")
    monkeypatch.setattr("scripts.generated_runtime.time.sleep", lambda _seconds: None)

    reset_to_start(driver, "android", "com.android.settings", ".Settings")

    assert ("context", "NATIVE_APP") in driver.calls
    assert ("terminate", "com.google.android.settings.intelligence") in driver.calls
    assert ("terminate", "com.android.settings") in driver.calls
    assert ("activate", "com.android.settings") in driver.calls
    assert (
        "mobile: startActivity",
        {"intent": "com.android.settings/.Settings", "wait": True, "stop": True},
    ) in driver.calls


def test_ios_reset_terminates_and_reactivates_bundle(monkeypatch):
    driver = _Driver("ios")
    monkeypatch.setattr("scripts.generated_runtime.time.sleep", lambda _seconds: None)

    reset_to_start(driver, "ios", "com.apple.Preferences")

    assert ("terminate", "com.apple.Preferences") in driver.calls
    assert ("activate", "com.apple.Preferences") in driver.calls
    assert not any(call[0] == "mobile: startActivity" for call in driver.calls)
