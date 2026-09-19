"""
Runtime collector for per-test execution observability.

수집 헬퍼: session_start, start, stop, session_finish
보존 정책: _should_keep
API 계약 테스트는 tests/observability/test_api_contracts.py에 분리되어 있습니다.

Usage (헬퍼):
    conftest.py에서 import하여 pytest 훅에서 호출합니다.

"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from agents.dashboard.utils.artifact_retention import purge_old_runs as _purge_old_runs

from .manifest import (
    append_attempt as _append_attempt,
    find_entry as _find_entry,
    load_manifest as _load_manifest,
    mp4_duration_seconds as _mp4_duration_seconds,
    node_slug as _node_slug,
    save_manifest as _save_manifest,
    should_keep as _should_keep,
    truncate_syslog as _truncate_syslog,
    validate_mp4 as _validate_mp4,
)

ROOT = Path(__file__).parents[2]
CONFIG_DIR = ROOT / "config"
STATE_DIR = ROOT / "state"
RUNS_DIR = STATE_DIR / "runs"


# ─── adb 경로 ────────────────────────────────────────────────────
def _find_adb() -> str:
    import shutil
    candidates = [
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
        "/usr/local/bin/adb",
        shutil.which("adb") or "",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return "adb"


ADB = _find_adb()


# ─── 설정 로더 ───────────────────────────────────────────────────
def _load_obs_config() -> dict:
    defaults: dict = {
        "enabled": True,
        "keep": "on_failure",
        "video": {
            "android": {
                "bit_rate": 2000000,
                "time_limit_sec": 180,
                "min_duration_sec": 1.0,
            },
            "ios": {"codec": "h264"},
        },
        "syslog": {
            "android": {"buffers": "all", "format": "threadtime"},
            "ios": {
                "level": "info",
                "predicate": (
                    'processImagePath CONTAINS[c] "{bundle_suffix}"'
                    ' OR subsystem CONTAINS[c] "{bundle_id}"'
                ),
            },
        },
        "retention": {"max_runs": 20, "max_total_mb": 2048},
        "limits": {"syslog_max_mb": 20},
    }
    cfg_path = CONFIG_DIR / "observability.json"
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            def merge(dst: dict, src: dict) -> None:
                for key, value in src.items():
                    if isinstance(value, dict) and isinstance(dst.get(key), dict):
                        merge(dst[key], value)
                    else:
                        dst[key] = value
            merge(defaults, data)
        except Exception:
            pass
    return defaults


def _effective_keep(config: dict) -> str:
    value = os.environ.get("QA_OBS_KEEP", "").strip() or str(
        config.get("keep", "on_failure")
    )
    return value if value in {"on_failure", "always", "never"} else "on_failure"


def _collection_disabled(config: Optional[dict] = None) -> bool:
    cfg = config or _load_obs_config()
    return bool(os.environ.get("QA_OBS_DISABLE")) or not bool(cfg.get("enabled", True))


# ─── 기기 식별 ───────────────────────────────────────────────────
def _first_online_adb_device() -> str:
    """adb devices에서 첫 번째 온라인 기기 serial 반환."""
    try:
        r = subprocess.run([ADB, "devices"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                return parts[0]
    except Exception:
        pass
    return ""


def _start_android_recording(udid: str, remote: str, config: dict) -> Optional[int]:
    """Start screenrecord detached on-device and return its exact remote PID."""
    subprocess.run(
        [ADB, "-s", udid, "shell", "rm", "-f", remote],
        capture_output=True,
        timeout=10,
    )
    bit_rate = max(1, int(config.get("bit_rate", 2000000)))
    time_limit = max(1, int(config.get("time_limit_sec", 180)))
    # adb shell joins additional argv before invoking the device shell, so a
    # positional-parameter sh -c command loses its quoting.  Send one complete
    # remote command instead and quote the only path component explicitly.
    command = (
        f"screenrecord --bit-rate {bit_rate} --time-limit {time_limit} "
        f"{shlex.quote(remote)} >/dev/null 2>&1 & echo $!"
    )
    result = subprocess.run(
        [ADB, "-s", udid, "shell", command],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return None
    for line in reversed(result.stdout.splitlines()):
        if line.strip().isdigit():
            return int(line.strip())
    return None


def _stop_android_recording(udid: str, pid: int, timeout_sec: float = 8.0) -> bool:
    """Gracefully stop only the recorder started for this attempt."""
    # screenrecord finalizes the MP4 moov atom on SIGINT. SIGTERM leaves an
    # unreadable file on Android/emulators.
    subprocess.run(
        [ADB, "-s", udid, "shell", "kill", "-2", str(pid)],
        capture_output=True,
        timeout=10,
    )
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        alive = subprocess.run(
            [ADB, "-s", udid, "shell", "kill", "-0", str(pid)],
            capture_output=True,
            timeout=10,
        )
        if alive.returncode != 0:
            return True
        time.sleep(0.2)
    subprocess.run(
        [ADB, "-s", udid, "shell", "kill", "-9", str(pid)],
        capture_output=True,
        timeout=10,
    )
    return False


def _android_recording_alive(udid: str, pid: int) -> bool:
    result = subprocess.run(
        [ADB, "-s", udid, "shell", "kill", "-0", str(pid)],
        capture_output=True,
        timeout=10,
    )
    return result.returncode == 0


def _minimum_recording_delay(
    started_monotonic: float, minimum_sec: float, *, now: Optional[float] = None
) -> float:
    """Return the remaining time needed before a recorder can finalize safely."""
    current = time.monotonic() if now is None else now
    return max(0.0, round(float(minimum_sec) - (current - started_monotonic), 3))


def _resolve_target_device(platform: str) -> Tuple[str, str]:
    """(udid, device_name) 반환. 실패 시 ('', '')."""
    udid = os.environ.get("DEVICE_UDID", "").strip()
    mode = os.environ.get("DEVICE_MODE", "").strip() or (
        "simulator" if platform == "ios" else "emulator"
    )
    devices: list = []
    try:
        cfg = json.loads((CONFIG_DIR / "devices.json").read_text(encoding="utf-8"))
        raw = cfg.get(platform, {}).get(mode, [])
        devices = [raw] if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    except Exception:
        pass

    if udid:
        m = next((d for d in devices if d.get("udid") == udid), None)
        return udid, (m or {}).get("deviceName", "")
    d = next((x for x in devices if x.get("default")), devices[0] if devices else {})
    resolved = d.get("udid", "")
    if platform == "android" and not resolved:
        resolved = _first_online_adb_device()
    return resolved, d.get("deviceName", "")


# ─── 아티팩트 디렉토리 해석 ──────────────────────────────────────
def _gen_run_id(platform: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    return f"run_{platform}_{stamp}"


def _artifact_dir(run_id: Optional[str] = None) -> Tuple[Path, str]:
    """(artifact_dir, run_id) 반환. PRD §3-1 해석 순서 4단계."""
    # 1. QA_ARTIFACT_DIR
    art_env = os.environ.get("QA_ARTIFACT_DIR", "").strip()
    if art_env:
        rid = run_id or os.environ.get("QA_RUN_ID", "").strip() or _gen_run_id("unknown")
        d = Path(art_env)
        d.mkdir(parents=True, exist_ok=True)
        return d, rid

    # 2. QA_RUN_DIR/artifacts
    run_dir_env = os.environ.get("QA_RUN_DIR", "").strip()
    if run_dir_env:
        rid = run_id or os.environ.get("QA_RUN_ID", "").strip() or _gen_run_id("unknown")
        d = Path(run_dir_env) / "artifacts"
        d.mkdir(parents=True, exist_ok=True)
        return d, rid

    # 3. state/runs/{QA_RUN_ID}/artifacts
    rid = run_id or os.environ.get("QA_RUN_ID", "").strip()
    if rid:
        d = RUNS_DIR / rid / "artifacts"
        d.mkdir(parents=True, exist_ok=True)
        return d, rid

    # 4. 자동 발급
    platform = os.environ.get("QA_PLATFORM", "unknown").strip()
    rid = _gen_run_id(platform)
    d = RUNS_DIR / rid / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d, rid


def _ios_log_predicate(config: dict) -> Optional[str]:
    try:
        test_data = json.loads(
            (CONFIG_DIR / "test_data.json").read_text(encoding="utf-8")
        )
        bundle_id = str(
            test_data.get("app", {}).get("ios", {}).get("bundle_id", "")
        ).strip()
    except Exception:
        bundle_id = ""
    if not bundle_id:
        return None
    template = config.get("syslog", {}).get("ios", {}).get(
        "predicate",
        'processImagePath CONTAINS[c] "{bundle_suffix}"'
        ' OR subsystem CONTAINS[c] "{bundle_id}"',
    )
    return template.format(
        bundle_id=bundle_id, bundle_suffix=bundle_id.rsplit(".", 1)[-1]
    )


def _ios_log_command(udid: str, config: dict) -> list[str]:
    ios_log = config.get("syslog", {}).get("ios", {})
    command = [
        "xcrun", "simctl", "spawn", udid, "log", "stream",
        "--style", "compact", "--level", str(ios_log.get("level", "info")),
    ]
    predicate = _ios_log_predicate(config)
    if predicate:
        command += ["--predicate", predicate]
    return command


def _app_id(platform: str) -> str:
    try:
        data = json.loads((CONFIG_DIR / "test_data.json").read_text(encoding="utf-8"))
        app = data.get("app", {}).get(platform, {})
        return str(app.get("package" if platform == "android" else "bundle_id", ""))
    except Exception:
        return ""


# ─── run 보존 정리 ───────────────────────────────────────────────
def purge_old_runs(max_runs: int = 20, max_total_mb: int = 2048) -> dict:
    """Compatibility wrapper around the production retention service."""
    return _purge_old_runs(RUNS_DIR, max_runs=max_runs, max_total_mb=max_total_mb)


# ─── 세션 전역 상태 ──────────────────────────────────────────────
_session_state: dict = {}


def _is_observable(nodeid: str) -> bool:
    """수집 대상 TC 판별. tests/generated/ 하위만 대상."""
    if os.environ.get("QA_OBS_DISABLE"):
        return False
    return nodeid.startswith("tests/generated/")


# ─── 4개 훅 함수 ─────────────────────────────────────────────────

def session_start(config) -> None:  # noqa: ARG001
    """Reset process-local state; filesystem initialization is lazy."""
    _session_state.clear()


def _ensure_session() -> bool:
    """Initialize a run only when the first generated test starts."""
    if _session_state:
        return True
    obs_config = _load_obs_config()
    keep_policy = _effective_keep(obs_config)
    if _collection_disabled(obs_config) or keep_policy == "never":
        return False
    try:
        run_id = os.environ.get("QA_RUN_ID", "").strip()
        platform = os.environ.get("QA_PLATFORM", "android").strip()
        mode = os.environ.get("DEVICE_MODE", "").strip() or (
            "simulator" if platform == "ios" else "emulator"
        )
        udid, device_name = _resolve_target_device(platform)

        artifact_dir, run_id = _artifact_dir(run_id or None)

        # Android screenrecord probe (F-4)
        video_ok = True
        video_unavailable_reason = ""
        if platform == "android" and udid:
            try:
                r = subprocess.run(
                    [ADB, "-s", udid, "shell", "screenrecord", "--help"],
                    capture_output=True, text=True, timeout=10,
                )
                video_ok = "--bit-rate" in (r.stdout + r.stderr)
                if not video_ok:
                    first_line = (r.stderr or r.stdout or "unsupported").splitlines()[0][:200]
                    video_unavailable_reason = first_line
            except Exception as e:
                video_ok = False
                video_unavailable_reason = str(e)[:200]
        elif platform == "android":
            video_ok = False
            video_unavailable_reason = "no_device"

        manifest = _load_manifest(artifact_dir)
        # healing 재실행에서 이어붙이기 — run_id가 같으면 기존 manifest 유지
        if not manifest or manifest.get("run_id") != run_id:
            manifest = {
                "run_id": run_id,
                "platform": platform,
                "mode": mode,
                "udid": udid,
                "device_name": device_name,
                "app_id": _app_id(platform),
                "keep_policy": keep_policy,
                "started_at": datetime.now().isoformat(),
                "finished_at": None,
                "entries": [],
            }
        if video_unavailable_reason:
            manifest["video_unavailable"] = video_unavailable_reason

        _save_manifest(artifact_dir, manifest)

        _session_state.clear()
        _session_state.update({
            "run_id": run_id,
            "platform": platform,
            "mode": mode,
            "udid": udid,
            "device_name": device_name,
            "keep_policy": keep_policy,
            "artifact_dir": artifact_dir,
            "video_ok": video_ok,
            "config": obs_config,
            "manifest": manifest,
            "tc_procs": {},
        })
        return True
    except Exception as e:
        print(f"[obs] session_start error: {e}", file=sys.stderr)
        return False


def start(item) -> None:
    """pytest_runtest_setup 훅에서 호출. 영상·로그 프로세스 시작."""
    if not _is_observable(item.nodeid):
        return
    if not _ensure_session():
        return
    try:
        slug = _node_slug(item.nodeid)
        artifact_dir: Path = _session_state["artifact_dir"]
        platform = _session_state["platform"]
        udid = _session_state["udid"]
        video_ok = _session_state["video_ok"]
        mode = _session_state.get("mode", "")
        obs_config = _session_state["config"]

        manifest = _load_manifest(artifact_dir)
        previous = _find_entry(manifest, slug)
        if previous and isinstance(previous.get("attempts"), list):
            attempt_n = len(previous["attempts"]) + 1
        else:
            attempt_n = int((previous or {}).get("attempt_count", 0)) + 1
        tc_dir = artifact_dir / slug / f"attempt{attempt_n}"
        tc_dir.mkdir(parents=True, exist_ok=True)

        collect_errors: list = []
        video_proc = None
        video_pid = None
        video_started_monotonic = None
        log_proc = None
        log_file = None

        # ── Android 영상 ─────────────────────────────────────
        if platform == "android":
            if not udid:
                collect_errors.append("no_device")
            elif not video_ok:
                collect_errors.append("video_unsupported")
            else:
                remote = "/sdcard/qa_obs_{}.mp4".format(
                    hashlib.sha1(slug.encode()).hexdigest()[:12]
                )
                try:
                    video_cfg = obs_config.get("video", {}).get("android", {})
                    for start_try in range(2):
                        video_pid = _start_android_recording(udid, remote, video_cfg)
                        time.sleep(0.4)
                        if video_pid is not None and _android_recording_alive(udid, video_pid):
                            # Launch/probe latency is not encoded footage. Measure the
                            # minimum duration only after screenrecord is confirmed alive.
                            video_started_monotonic = time.monotonic()
                            break
                        video_pid = None
                        video_started_monotonic = None
                        if start_try == 0:
                            time.sleep(0.5)
                    if video_pid is None:
                        collect_errors.append("video_start_failed")
                except Exception:
                    collect_errors.append("video_start_failed")
                    video_pid = None

        # ── iOS 영상 (시뮬레이터만) ───────────────────────────
        elif platform == "ios":
            if mode == "real_device":
                collect_errors.append("ios_real_device_unsupported")
            elif not udid:
                collect_errors.append("no_device")
            else:
                local_video = tc_dir / "video.mp4"
                try:
                    subprocess.run(["xcrun", "--version"], capture_output=True, timeout=5)
                    video_proc = subprocess.Popen(
                        ["xcrun", "simctl", "io", udid,
                         "recordVideo",
                         "--codec={}".format(
                             obs_config.get("video", {}).get("ios", {}).get("codec", "h264")
                         ),
                         "--force", str(local_video)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )
                    time.sleep(0.3)
                    if video_proc.poll() is not None:
                        collect_errors.append("video_start_failed")
                        video_proc = None
                except FileNotFoundError:
                    collect_errors.append("simctl_not_found")
                    video_proc = None
                except Exception:
                    collect_errors.append("video_start_failed")
                    video_proc = None

        # ── Android 로그 ─────────────────────────────────────
        if platform == "android":
            if udid and "no_device" not in collect_errors:
                syslog_path = tc_dir / "syslog.txt"
                try:
                    android_log = obs_config.get("syslog", {}).get("android", {})
                    log_file = open(syslog_path, "w", encoding="utf-8", errors="replace")
                    log_proc = subprocess.Popen(
                        [ADB, "-s", udid, "logcat",
                         "-b", str(android_log.get("buffers", "all")),
                         "-v", str(android_log.get("format", "threadtime")), "-T", "1"],
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                    )
                    time.sleep(0.2)
                    if log_proc.poll() is not None:
                        collect_errors.append("syslog_start_failed")
                        try:
                            log_file.close()
                        except Exception:
                            pass
                        log_file = None
                        log_proc = None
                except Exception:
                    collect_errors.append("syslog_start_failed")
                    if log_file:
                        try:
                            log_file.close()
                        except Exception:
                            pass
                    log_file = None
                    log_proc = None

        # ── iOS 로그 (시뮬레이터만) ───────────────────────────
        elif platform == "ios":
            if (mode != "real_device"
                    and udid
                    and "no_device" not in collect_errors
                    and "simctl_not_found" not in collect_errors):
                syslog_path = tc_dir / "syslog.txt"
                try:
                    log_file = open(syslog_path, "w", encoding="utf-8", errors="replace")
                    log_proc = subprocess.Popen(
                        _ios_log_command(udid, obs_config),
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                    )
                    time.sleep(0.2)
                    if log_proc.poll() is not None:
                        collect_errors.append("syslog_start_failed")
                        try:
                            log_file.close()
                        except Exception:
                            pass
                        log_file = None
                        log_proc = None
                except FileNotFoundError:
                    collect_errors.append("simctl_not_found")
                    if log_file:
                        try:
                            log_file.close()
                        except Exception:
                            pass
                    log_file = None
                    log_proc = None
                except Exception:
                    collect_errors.append("syslog_start_failed")
                    if log_file:
                        try:
                            log_file.close()
                        except Exception:
                            pass
                    log_file = None
                    log_proc = None

        _session_state["tc_procs"][slug] = {
            "video_proc": video_proc,
            "video_pid": video_pid,
            "video_started_monotonic": video_started_monotonic,
            "log_proc": log_proc,
            "log_file": log_file,
            "started_at": datetime.now().isoformat(),
            "collect_errors": collect_errors,
            "tc_dir": tc_dir,
            "attempt_n": attempt_n,
            "nodeid": item.nodeid,
        }
    except Exception as e:
        print(f"[obs] start error: {e}", file=sys.stderr)


def capture_screenshot(item, driver, outcome: str) -> Optional[Path]:
    """Capture the final call-phase screen for an attempt that will be kept."""
    if not _is_observable(item.nodeid) or not _session_state:
        return None
    slug = _node_slug(item.nodeid)
    tc_info = _session_state.get("tc_procs", {}).get(slug)
    if tc_info is None:
        return None
    keep = _should_keep(
        _session_state.get("keep_policy", "on_failure"),
        outcome,
        int(tc_info.get("attempt_n", 1)),
    )
    if not keep:
        return None
    path = Path(tc_info["tc_dir"]) / "screenshot.png"
    try:
        saved = driver.save_screenshot(str(path))
        if saved is False or not path.is_file() or path.stat().st_size == 0:
            raise OSError("empty screenshot")
        return path
    except Exception:
        tc_info.setdefault("collect_errors", []).append("screenshot_capture_failed")
        path.unlink(missing_ok=True)
        return None


def _capture_device_screenshot(
    platform: str, udid: str, mode: str, path: Path
) -> bool:
    """Capture a screenshot without Appium for driverless observable tests."""
    if not udid:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if platform == "android":
            result = subprocess.run(
                [ADB, "-s", udid, "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=20,
            )
            if result.returncode == 0 and result.stdout.startswith(b"\x89PNG"):
                path.write_bytes(result.stdout)
        elif platform == "ios" and mode != "real_device":
            result = subprocess.run(
                ["xcrun", "simctl", "io", udid, "screenshot", str(path)],
                capture_output=True,
                timeout=20,
            )
            if result.returncode != 0:
                path.unlink(missing_ok=True)
        else:
            return False
        if path.is_file() and path.stat().st_size > 0:
            return True
    except Exception:
        pass
    path.unlink(missing_ok=True)
    return False


def stop(item, outcome: str, screenshot_path: Optional[Path] = None) -> None:
    """pytest_runtest_makereport when=='teardown' 훅에서 호출.

    프로세스 종료 → 보존 정책 적용 → manifest 갱신.
    """
    if not _is_observable(item.nodeid):
        return
    if not _session_state:
        return
    slug = _node_slug(item.nodeid)
    tc_info = _session_state.get("tc_procs", {}).get(slug)
    if tc_info is None:
        return

    try:
        platform = _session_state["platform"]
        udid = _session_state["udid"]
        artifact_dir: Path = _session_state["artifact_dir"]
        keep_policy = _session_state["keep_policy"]
        obs_config = _session_state["config"]
        tc_dir: Path = tc_info["tc_dir"]
        attempt_count = int(tc_info.get("attempt_n", 1))
        started_at_str = tc_info.get("started_at", datetime.now().isoformat())
        collect_errors = list(tc_info.get("collect_errors", []))

        finished_at = datetime.now()
        try:
            duration_sec = (finished_at - datetime.fromisoformat(started_at_str)).total_seconds()
        except Exception:
            duration_sec = 0.0

        keep = _should_keep(keep_policy, outcome, attempt_count)
        failure_offset_sec: Optional[float] = (
            round(duration_sec, 1) if outcome in ("failed", "error") else None
        )

        # ── Android 영상 teardown ─────────────────────────────
        video_info = None
        video_proc = tc_info.get("video_proc")
        video_pid = tc_info.get("video_pid")

        if platform == "android" and video_pid is not None:
            try:
                video_cfg = obs_config.get("video", {}).get("android", {})
                started_monotonic = tc_info.get("video_started_monotonic")
                if started_monotonic is not None:
                    settle_delay = _minimum_recording_delay(
                        float(started_monotonic),
                        float(video_cfg.get("min_duration_sec", 1.0)),
                    )
                    if settle_delay:
                        time.sleep(settle_delay)
                if not _stop_android_recording(udid, int(video_pid)):
                    collect_errors.append("video_stop_timeout")
                time.sleep(0.5)
            except Exception:
                collect_errors.append("video_stop_failed")
                try:
                    subprocess.run(
                        [ADB, "-s", udid, "shell", "kill", "-9", str(video_pid)],
                        capture_output=True,
                        timeout=10,
                    )
                except Exception:
                    pass

            if keep and udid:
                local_video = tc_dir / "video.mp4"
                remote = "/sdcard/qa_obs_{}.mp4".format(
                    hashlib.sha1(slug.encode()).hexdigest()[:12]
                )
                try:
                    # 기기 파일 크기 확인 — 0바이트면 pull 생략 (초기화 중 종료된 screenrecord)
                    sz_r = subprocess.run(
                        [ADB, "-s", udid, "shell", "stat", "-c", "%s", remote],
                        capture_output=True, text=True, timeout=10,
                    )
                    remote_bytes = int(sz_r.stdout.strip()) if sz_r.returncode == 0 else 0
                    if remote_bytes == 0:
                        collect_errors.append("video_pull_failed")
                    else:
                        r = subprocess.run(
                            [ADB, "-s", udid, "pull", remote, str(local_video)],
                            capture_output=True, timeout=30,
                        )
                        if r.returncode != 0 or not local_video.exists():
                            collect_errors.append("video_pull_failed")
                            if local_video.exists():
                                local_video.unlink(missing_ok=True)
                        elif not _validate_mp4(local_video):
                            collect_errors.append("video_invalid")
                            local_video.unlink(missing_ok=True)
                        else:
                            video_info = {
                                "path": f"{slug}/attempt{attempt_count}/video.mp4",
                                "bytes": local_video.stat().st_size,
                                "source": "adb_screenrecord",
                                "truncated": duration_sec >= float(
                                    obs_config.get("video", {}).get("android", {}).get(
                                        "time_limit_sec", 180
                                    )
                                ),
                            }
                except Exception:
                    collect_errors.append("video_pull_failed")

            # 기기에서 항상 삭제
            try:
                remote = "/sdcard/qa_obs_{}.mp4".format(
                    hashlib.sha1(slug.encode()).hexdigest()[:12]
                )
                subprocess.run(
                    [ADB, "-s", udid, "shell", "rm", "-f", remote],
                    capture_output=True, timeout=10,
                )
            except Exception:
                pass

        # ── iOS 영상 teardown ─────────────────────────────────
        elif platform == "ios" and video_proc is not None:
            local_video = tc_dir / "video.mp4"
            try:
                video_proc.send_signal(signal.SIGINT)  # SIGTERM 아님! moov atom 기록 필요
                video_proc.wait(timeout=10)
            except (subprocess.TimeoutExpired, Exception):
                try:
                    video_proc.kill()
                    video_proc.wait()
                except Exception:
                    pass

            if keep and _validate_mp4(local_video):
                video_info = {
                    "path": f"{slug}/attempt{attempt_count}/video.mp4",
                    "bytes": local_video.stat().st_size,
                    "source": "simctl_recordVideo",
                    "truncated": False,
                }
            elif keep and local_video.exists():
                collect_errors.append("video_invalid")
                local_video.unlink(missing_ok=True)
            elif not keep:
                try:
                    local_video.unlink(missing_ok=True)
                except Exception:
                    pass

        # ── 로그 teardown ─────────────────────────────────────
        syslog_info = None
        log_proc = tc_info.get("log_proc")
        log_file = tc_info.get("log_file")

        if log_proc is not None:
            try:
                log_proc.terminate()
                try:
                    log_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    log_proc.kill()
                    log_proc.wait()
            except Exception:
                pass
            finally:
                if log_file:
                    try:
                        log_file.close()
                    except Exception:
                        pass
                    log_file = None

            syslog_path = tc_dir / "syslog.txt"
            if keep and syslog_path.exists():
                max_mb = int(obs_config.get("limits", {}).get("syslog_max_mb", 20))
                truncated = _truncate_syslog(syslog_path, max_mb * 1024 * 1024)
                if truncated and "syslog_truncated" not in collect_errors:
                    collect_errors.append("syslog_truncated")
                syslog_bytes = syslog_path.stat().st_size if syslog_path.exists() else 0
                source = "adb_logcat" if platform == "android" else "simctl_log_stream"
                syslog_info = {
                    "path": f"{slug}/attempt{attempt_count}/syslog.txt",
                    "bytes": syslog_bytes,
                    "source": source,
                    "truncated": truncated,
                }
            elif not keep:
                try:
                    (tc_dir / "syslog.txt").unlink(missing_ok=True)
                except Exception:
                    pass
        elif log_file:
            try:
                log_file.close()
            except Exception:
                pass

        # ── 스크린샷 ──────────────────────────────────────────
        screenshot_info = None
        screenshot_source = "appium_driver"
        if keep and screenshot_path is None:
            native_path = tc_dir / "screenshot.png"
            if _capture_device_screenshot(
                platform, udid, _session_state.get("mode", ""), native_path
            ):
                screenshot_path = native_path
                screenshot_source = "device_capture"
            elif "screenshot_capture_failed" not in collect_errors:
                collect_errors.append("screenshot_capture_failed")
        if keep and screenshot_path is not None:
            sp = Path(screenshot_path)
            if sp.exists():
                try:
                    rel = str(sp.relative_to(artifact_dir))
                    screenshot_info = {
                        "path": rel,
                        "bytes": sp.stat().st_size,
                        "source": screenshot_source,
                        "external": False,
                    }
                except ValueError:
                    try:
                        rel = str(sp.relative_to(ROOT))
                    except ValueError:
                        rel = str(sp)
                    screenshot_info = {
                        "path": rel,
                        "bytes": sp.stat().st_size,
                        "source": "pytest_failure_hook",
                        "external": True,
                    }

        # ── manifest 갱신 ─────────────────────────────────────
        manifest = _load_manifest(artifact_dir)
        if not manifest:
            manifest = {
                "run_id": _session_state["run_id"],
                "platform": platform,
                "mode": _session_state.get("mode", ""),
                "udid": udid,
                "device_name": _session_state.get("device_name", ""),
                "app_id": _app_id(platform),
                "keep_policy": keep_policy,
                "started_at": _session_state.get("manifest", {}).get(
                    "started_at", datetime.now().isoformat()
                ),
                "finished_at": None,
                "entries": [],
            }

        new_attempt = {
            "n": attempt_count,
            "outcome": outcome,
            "started_at": started_at_str,
            "finished_at": finished_at.isoformat(),
            "duration_sec": round(duration_sec, 1),
            "kept": keep,
            "failure_offset_sec": failure_offset_sec,
            "video": video_info,
            "syslog": syslog_info,
            "screenshot": screenshot_info,
            "network": None,
            "collect_errors": collect_errors,
        }

        _append_attempt(manifest, item.nodeid, slug, new_attempt)
        try:
            (tc_dir / "meta.json").write_text(
                json.dumps(new_attempt, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            collect_errors.append("manifest_write_failed")

        _save_manifest(artifact_dir, manifest)
        _session_state["manifest"] = manifest
        _session_state["tc_procs"].pop(slug, None)

    except Exception as e:
        print(f"[obs] stop error: {e}", file=sys.stderr)
        # 좀비 프로세스 방지 — 예외 경로에서도 반드시 종료
        video_pid = tc_info.get("video_pid")
        udid = _session_state.get("udid", "")
        if video_pid is not None and udid:
            try:
                subprocess.run(
                    [ADB, "-s", udid, "shell", "kill", "-9", str(video_pid)],
                    capture_output=True,
                    timeout=10,
                )
            except Exception:
                pass
        for key in ("video_proc", "log_proc"):
            proc = tc_info.get(key)
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass
        if tc_info.get("log_file"):
            try:
                tc_info["log_file"].close()
            except Exception:
                pass
        _session_state.get("tc_procs", {}).pop(slug, None)


def session_finish(config) -> None:  # noqa: ARG001
    """pytest_sessionfinish 훅에서 호출. finished_at 기록."""
    if os.environ.get("QA_OBS_DISABLE"):
        return
    if not _session_state:
        return
    try:
        artifact_dir: Path = _session_state["artifact_dir"]
        manifest = _load_manifest(artifact_dir)
        if manifest:
            manifest["finished_at"] = datetime.now().isoformat()
            _save_manifest(artifact_dir, manifest)
    except Exception as e:
        print(f"[obs] session_finish error: {e}", file=sys.stderr)
