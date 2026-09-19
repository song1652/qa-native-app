import importlib
import json
import struct
from pathlib import Path
from types import SimpleNamespace


def _obs():
    module = importlib.import_module("tests._observability")
    module._session_state.clear()
    return module


def _mvhd_mp4(timescale: int, duration: int) -> bytes:
    payload = (
        b"\x00\x00\x00\x00"
        + struct.pack(">I", 0)
        + struct.pack(">I", 0)
        + struct.pack(">I", timescale)
        + struct.pack(">I", duration)
    )
    mvhd = struct.pack(">I", 8 + len(payload)) + b"mvhd" + payload
    moov = struct.pack(">I", 8 + len(mvhd)) + b"moov" + mvhd
    return struct.pack(">I", 16) + b"ftyp" + b"isom0000" + moov


def test_session_start_is_lazy_for_non_generated_suites(tmp_path, monkeypatch):
    obs = _obs()
    monkeypatch.setattr(obs, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.delenv("QA_RUN_ID", raising=False)
    monkeypatch.delenv("QA_OBS_DISABLE", raising=False)

    obs.session_start(SimpleNamespace())

    assert not (tmp_path / "runs").exists()
    assert obs._session_state == {}


def test_never_policy_does_not_initialize_or_start_processes(tmp_path, monkeypatch):
    obs = _obs()
    monkeypatch.setattr(obs, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setenv("QA_OBS_KEEP", "never")
    monkeypatch.setenv("QA_RUN_ID", "run_android_20260917_120000_001")
    monkeypatch.setenv("QA_PLATFORM", "android")
    item = SimpleNamespace(nodeid="tests/generated/android/demo/test_one.py::test_one")

    obs.start(item)

    assert not (tmp_path / "runs").exists()
    assert obs._session_state == {}


def test_append_attempt_preserves_each_attempt(tmp_path):
    obs = _obs()
    artifact_dir = tmp_path / "artifacts"
    manifest = {"entries": []}
    first = {"n": 1, "outcome": "failed", "kept": True}
    second = {"n": 2, "outcome": "passed", "kept": True}

    obs._append_attempt(manifest, "node", "slug", first)
    obs._append_attempt(manifest, "node", "slug", second)

    entry = manifest["entries"][0]
    assert entry["attempt_count"] == 2
    assert entry["outcome"] == "passed"
    assert entry["attempts"] == [first, second]


def test_mp4_validator_rejects_missing_moov(tmp_path):
    obs = _obs()
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"\x00\x00\x00\x10ftypisom0000")

    assert obs._validate_mp4(path) is False


def test_mp4_validator_rejects_zero_duration(tmp_path):
    obs = _obs()
    path = tmp_path / "zero.mp4"
    path.write_bytes(_mvhd_mp4(1000, 0))

    assert obs._validate_mp4(path) is False


def test_mp4_validator_accepts_positive_duration(tmp_path):
    obs = _obs()
    path = tmp_path / "valid.mp4"
    path.write_bytes(_mvhd_mp4(1000, 2500))

    assert obs._validate_mp4(path) is True
    assert obs._mp4_duration_seconds(path) == 2.5


def test_android_recording_starts_device_side_and_returns_exact_pid(monkeypatch):
    obs = _obs()
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if len(args) >= 5 and args[3] == "shell" and "screenrecord" in args[4]:
            return SimpleNamespace(returncode=0, stdout="4321\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(obs.subprocess, "run", fake_run)

    pid = obs._start_android_recording(
        "emulator-5554", "/sdcard/test.mp4", {"bit_rate": 2_000_000, "time_limit_sec": 180}
    )

    assert pid == 4321
    start_call = next(call for call in calls if "screenrecord" in " ".join(call))
    assert len(start_call) == 5
    assert "screenrecord --bit-rate 2000000 --time-limit 180 /sdcard/test.mp4" in start_call[4]
    assert "echo $!" in start_call[4]


def test_android_recording_stop_signals_only_recorded_pid(monkeypatch):
    obs = _obs()
    calls = []
    alive_checks = iter([0, 1])

    def fake_run(args, **kwargs):
        calls.append(args)
        if "kill" in args and "-0" in args:
            return SimpleNamespace(returncode=next(alive_checks), stdout="", stderr="")
        if "stat" in args:
            return SimpleNamespace(returncode=0, stdout="4096\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(obs.subprocess, "run", fake_run)
    monkeypatch.setattr(obs.time, "sleep", lambda _seconds: None)

    assert obs._stop_android_recording("emulator-5554", 4321) is True
    assert any(call[-3:] == ["kill", "-2", "4321"] for call in calls)
    assert not any(call[-3:] == ["kill", "-15", "4321"] for call in calls)
    assert not any("pkill" in call for call in calls)


def test_android_short_recording_waits_until_minimum_duration():
    obs = _obs()

    assert obs._minimum_recording_delay(100.0, 1.0, now=100.25) == 0.75
    assert obs._minimum_recording_delay(100.0, 1.0, now=101.5) == 0.0


def test_android_minimum_duration_starts_after_recorder_is_confirmed_ready(
    tmp_path, monkeypatch
):
    """Recorder launch/probe time must not consume the minimum encoded duration."""
    obs = _obs()
    events = []
    artifact_dir = tmp_path / "artifacts"
    obs._session_state.update(
        {
            "artifact_dir": artifact_dir,
            "platform": "android",
            "mode": "emulator",
            "udid": "emulator-5554",
            "video_ok": True,
            "config": {"video": {"android": {"min_duration_sec": 1.0}}, "syslog": {}},
            "tc_procs": {},
        }
    )

    class Proc:
        def poll(self):
            return None

    monkeypatch.setattr(obs, "_start_android_recording", lambda *_args: events.append("start") or 42)
    monkeypatch.setattr(
        obs, "_android_recording_alive", lambda *_args: events.append("ready") or True
    )
    monkeypatch.setattr(obs.time, "monotonic", lambda: events.append("clock") or 100.0)
    monkeypatch.setattr(obs.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(obs.subprocess, "Popen", lambda *_args, **_kwargs: Proc())

    item = SimpleNamespace(nodeid="tests/generated/android/demo/test_short.py::test_short")
    obs.start(item)

    slug = obs._node_slug(item.nodeid)
    assert events[:3] == ["start", "ready", "clock"]
    assert obs._session_state["tc_procs"][slug]["video_started_monotonic"] == 100.0


def test_android_recording_alive_check_uses_exact_pid(monkeypatch):
    obs = _obs()
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(obs.subprocess, "run", fake_run)

    assert obs._android_recording_alive("emulator-5554", 4321) is True
    assert calls == [[obs.ADB, "-s", "emulator-5554", "shell", "kill", "-0", "4321"]]


def test_ios_predicate_uses_app_ios_bundle_id(tmp_path, monkeypatch):
    obs = _obs()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "test_data.json").write_text(
        json.dumps({"app": {"ios": {"bundle_id": "com.example.DirectCloud"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(obs, "CONFIG_DIR", config_dir)

    predicate = obs._ios_log_predicate(obs._load_obs_config())

    assert '"DirectCloud"' in predicate
    assert '"com.example.DirectCloud"' in predicate


def test_ios_predicate_rejects_empty_bundle_id(tmp_path, monkeypatch):
    obs = _obs()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "test_data.json").write_text(
        json.dumps({"app": {"ios": {"bundle_id": ""}}}), encoding="utf-8"
    )
    monkeypatch.setattr(obs, "CONFIG_DIR", config_dir)

    assert obs._ios_log_predicate(obs._load_obs_config()) is None


def test_ios_log_command_collects_unfiltered_logs_when_bundle_id_is_empty(
    tmp_path, monkeypatch
):
    obs = _obs()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "test_data.json").write_text(
        json.dumps({"app": {"ios": {"bundle_id": ""}}}), encoding="utf-8"
    )
    monkeypatch.setattr(obs, "CONFIG_DIR", config_dir)

    command = obs._ios_log_command("ios-udid", obs._load_obs_config())

    assert command == [
        "xcrun", "simctl", "spawn", "ios-udid", "log", "stream",
        "--style", "compact", "--level", "info",
    ]


def test_capture_screenshot_keeps_passed_attempt_when_policy_is_always(tmp_path):
    obs = _obs()
    nodeid = "tests/generated/ios/demo/test_one.py::test_one"
    slug = obs._node_slug(nodeid)
    attempt_dir = tmp_path / "artifacts" / slug / "attempt1"
    attempt_dir.mkdir(parents=True)
    obs._session_state.update({
        "keep_policy": "always",
        "tc_procs": {
            slug: {
                "tc_dir": attempt_dir,
                "attempt_n": 1,
                "collect_errors": [],
            }
        },
    })

    class Driver:
        def save_screenshot(self, path):
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\nimage")
            return True

    path = obs.capture_screenshot(SimpleNamespace(nodeid=nodeid), Driver(), "passed")

    assert path == attempt_dir / "screenshot.png"
    assert path.read_bytes().startswith(b"\x89PNG")
    obs._session_state.clear()


def test_capture_screenshot_skips_passed_attempt_not_kept_by_policy(tmp_path):
    obs = _obs()
    nodeid = "tests/generated/android/demo/test_one.py::test_one"
    slug = obs._node_slug(nodeid)
    attempt_dir = tmp_path / "artifacts" / slug / "attempt1"
    attempt_dir.mkdir(parents=True)
    obs._session_state.update({
        "keep_policy": "on_failure",
        "tc_procs": {
            slug: {
                "tc_dir": attempt_dir,
                "attempt_n": 1,
                "collect_errors": [],
            }
        },
    })

    class Driver:
        def save_screenshot(self, path):
            raise AssertionError("unkept attempts must not capture a screenshot")

    assert obs.capture_screenshot(
        SimpleNamespace(nodeid=nodeid), Driver(), "passed"
    ) is None
    assert not (attempt_dir / "screenshot.png").exists()
    obs._session_state.clear()


def test_android_device_screenshot_uses_adb_exec_out(tmp_path, monkeypatch):
    obs = _obs()
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=b"\x89PNG\r\n\x1a\nimage", stderr=b"")

    monkeypatch.setattr(obs.subprocess, "run", fake_run)
    path = tmp_path / "screenshot.png"

    assert obs._capture_device_screenshot("android", "emulator-5554", "emulator", path)
    assert path.read_bytes().startswith(b"\x89PNG")
    assert calls == [[obs.ADB, "-s", "emulator-5554", "exec-out", "screencap", "-p"]]


def test_ios_simulator_device_screenshot_uses_simctl(tmp_path, monkeypatch):
    obs = _obs()
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        Path(args[-1]).write_bytes(b"\x89PNG\r\n\x1a\nimage")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(obs.subprocess, "run", fake_run)
    path = tmp_path / "screenshot.png"

    assert obs._capture_device_screenshot("ios", "ios-udid", "simulator", path)
    assert calls == [["xcrun", "simctl", "io", "ios-udid", "screenshot", str(path)]]


def test_stop_adds_native_screenshot_for_kept_driverless_attempt(tmp_path, monkeypatch):
    obs = _obs()
    nodeid = "tests/generated/android/obs_demo/test_failure.py::test_failure"
    slug = obs._node_slug(nodeid)
    artifact_dir = tmp_path / "artifacts"
    attempt_dir = artifact_dir / slug / "attempt1"
    attempt_dir.mkdir(parents=True)
    obs._session_state.update({
        "run_id": "run_android_20260917_120000_001",
        "platform": "android",
        "mode": "emulator",
        "udid": "emulator-5554",
        "device_name": "Android Emulator",
        "artifact_dir": artifact_dir,
        "keep_policy": "on_failure",
        "config": {"video": {"android": {}}, "limits": {"syslog_max_mb": 20}},
        "manifest": {"started_at": "2026-09-17T12:00:00"},
        "tc_procs": {slug: {
            "tc_dir": attempt_dir,
            "attempt_n": 1,
            "started_at": "2026-09-17T12:00:00",
            "collect_errors": [],
            "video_proc": None,
            "video_pid": None,
            "log_proc": None,
            "log_file": None,
        }},
    })

    def fake_capture(platform, udid, mode, path):
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\nimage")
        return True

    monkeypatch.setattr(obs, "_capture_device_screenshot", fake_capture, raising=False)

    obs.stop(SimpleNamespace(nodeid=nodeid), "failed")

    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    screenshot = manifest["entries"][0]["attempts"][0]["screenshot"]
    assert screenshot["path"].endswith("attempt1/screenshot.png")
    assert screenshot["source"] == "device_capture"


def test_report_outcome_prioritizes_setup_and_teardown_errors():
    conftest = importlib.import_module("tests.conftest")

    assert conftest._final_outcome({"setup": "failed"}) == "error"
    assert conftest._final_outcome({"setup": "passed", "call": "failed"}) == "failed"
    assert conftest._final_outcome(
        {"setup": "passed", "call": "passed", "teardown": "failed"}
    ) == "error"
