"""Dashboard executable discovery works without an interactive shell PATH."""
from pathlib import Path
import sys
from types import SimpleNamespace


DASHBOARD = Path(__file__).parents[3] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

import shared  # noqa: E402


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_finds_appium_in_nvm_when_path_lookup_is_empty(tmp_path):
    appium = _executable(
        tmp_path / ".nvm" / "versions" / "node" / "v24.13.0" / "bin" / "appium"
    )
    finder = getattr(shared, "_find_appium_bin", lambda **_kwargs: "")

    result = finder(home=tmp_path, environ={}, path_lookup=lambda _name: None)

    assert result == str(appium)


def test_finds_emulator_in_macos_android_sdk_when_path_lookup_is_empty(tmp_path):
    emulator = _executable(
        tmp_path / "Library" / "Android" / "sdk" / "emulator" / "emulator"
    )
    finder = getattr(shared, "_find_emulator_bin", lambda **_kwargs: "")

    result = finder(home=tmp_path, environ={}, path_lookup=lambda _name: None)

    assert result == str(emulator)


def test_explicit_binary_environment_variable_has_priority(tmp_path):
    explicit = _executable(tmp_path / "tools" / "appium")
    nvm = _executable(
        tmp_path / ".nvm" / "versions" / "node" / "v24.13.0" / "bin" / "appium"
    )
    assert nvm.exists()
    finder = getattr(shared, "_find_appium_bin", lambda **_kwargs: "")

    result = finder(
        home=tmp_path,
        environ={"APPIUM_BIN": str(explicit)},
        path_lookup=lambda _name: None,
    )

    assert result == str(explicit)


def test_python_discovery_skips_runtime_without_pytest(monkeypatch, tmp_path):
    """빠른 실행에는 Appium뿐 아니라 pytest도 설치된 Python이 필요하다."""
    project_python = _executable(tmp_path / ".venv" / "bin" / "python")
    appium_only_python = _executable(tmp_path / "system" / "python3")

    def fake_run(command, **_kwargs):
        executable, probe = command[0], command[2]
        if executable == str(project_python) and "pytest" in probe:
            return SimpleNamespace(returncode=0)
        if executable == str(appium_only_python) and probe == "import appium":
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(shared, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(shared.subprocess, "run", fake_run)
    monkeypatch.setattr(shared.shutil, "which", lambda name: str(appium_only_python))
    monkeypatch.setattr(shared.sys, "executable", str(appium_only_python))

    assert shared._find_python_bin() == str(project_python)
