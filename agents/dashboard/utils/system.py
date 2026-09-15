"""
utils/system.py — 시스템 환경 확인 유틸리티.

Appium 서버 상태, Android/iOS 디바이스 목록, 포트 강제 종료.
"""
from __future__ import annotations

import os
import json
import re
import subprocess
import time
from datetime import datetime

import sys
from pathlib import Path

# shared.py 가 agents/dashboard/ 에 있으므로 같은 디렉토리 기준으로 임포트
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import (  # noqa: E402
    ADB_BIN,
    APPIUM_BIN,
    EMULATOR_BIN,
    ENV_SESSION_PATH,
    subprocess_env_for,
)


_APPIUM_DRIVER_CACHE: tuple[float, dict[str, bool]] | None = None
_APPIUM_DRIVER_CACHE_SECONDS = 15.0
_APPIUM_SESSIONS_SUPPORT: dict[tuple[int, str | None], bool] = {}


_ANDROID_RELEASE_BY_API = {
    21: "5.0",
    22: "5.1",
    23: "6.0",
    24: "7.0",
    25: "7.1",
    26: "8.0",
    27: "8.1",
    28: "9",
    29: "10",
    30: "11",
    31: "12",
    32: "12L",
    33: "13",
    34: "14",
    35: "15",
    36: "16",
}


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


def _read_ini(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    result: dict[str, str] = {}
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _android_release(config: dict[str, str]) -> str:
    source = " ".join(
        (config.get("target", ""), config.get("image.sysdir.1", ""))
    )
    match = re.search(r"android[-;](\d+)", source)
    if not match:
        return ""
    api = int(match.group(1))
    return _ANDROID_RELEASE_BY_API.get(api, str(api))


def _avd_directory(avd_name: str, avd_home: Path) -> Path:
    launcher = _read_ini(avd_home / f"{avd_name}.ini")
    absolute = launcher.get("path")
    if absolute:
        return Path(absolute).expanduser()
    relative = launcher.get("path.rel")
    if relative:
        android_home = Path(
            os.environ.get("ANDROID_USER_HOME", str(avd_home.parent))
        ).expanduser()
        return android_home / relative
    return avd_home / f"{avd_name}.avd"


def list_system_avds() -> list[dict[str, str]]:
    """Return installed AVDs with metadata used by the registration modal."""
    try:
        result = subprocess.run(
            [EMULATOR_BIN, "-list-avds"],
            capture_output=True,
            text=True,
            timeout=10,
            env=subprocess_env_for(EMULATOR_BIN),
        )
    except Exception as exc:
        raise RuntimeError(f"emulator 실행 실패: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError((_text(result.stderr) or _text(result.stdout)).strip())

    avd_home = Path(
        os.environ.get(
            "ANDROID_AVD_HOME",
            str(Path(os.environ.get("ANDROID_USER_HOME", Path.home() / ".android")) / "avd"),
        )
    ).expanduser()
    discovered = []
    for avd_name in sorted(filter(None, map(str.strip, _text(result.stdout).splitlines()))):
        config = _read_ini(_avd_directory(avd_name, avd_home) / "config.ini")
        display_name = config.get("avd.ini.displayname") or avd_name.replace("_", " ")
        discovered.append(
            {
                "avd": avd_name,
                "deviceName": display_name,
                "platformVersion": _android_release(config),
            }
        )
    return discovered


def list_system_simulators() -> list[dict[str, str]]:
    """Return available CoreSimulator devices joined to runtime versions."""
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            env=subprocess_env_for("xcrun"),
        )
    except Exception as exc:
        raise RuntimeError(f"simctl 실행 실패: {exc}") from exc
    if result.returncode != 0:
        detail = (_text(result.stderr) or _text(result.stdout)).strip()
        raise RuntimeError(detail or "simctl 실행에 실패했습니다.")
    try:
        payload = json.loads(_text(result.stdout) or "{}")
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"simctl JSON 파싱 실패: {exc}") from exc

    runtimes = {
        runtime.get("identifier"): runtime.get("version", "")
        for runtime in payload.get("runtimes", [])
        if runtime.get("identifier") and runtime.get("isAvailable", True)
    }
    simulators = []
    for runtime_id, devices in payload.get("devices", {}).items():
        if runtime_id not in runtimes:
            continue
        for device in devices:
            if not device.get("isAvailable", True):
                continue
            simulators.append(
                {
                    "deviceName": device.get("name", ""),
                    "platformVersion": runtimes[runtime_id],
                    "udid": device.get("udid", ""),
                    "state": device.get("state", "Shutdown"),
                }
            )
    return sorted(
        simulators,
        key=lambda value: (value["platformVersion"], value["deviceName"], value["udid"]),
    )


def check_appium_status() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:4723/status", timeout=2)
        return True
    except Exception:
        return False


def check_android_devices() -> list[str]:
    try:
        result = subprocess.run(
            [ADB_BIN, "devices"], capture_output=True, text=True, timeout=3
        )
        lines = result.stdout.strip().splitlines()
        return [
            ln.split("\t")[0]
            for ln in lines[1:]
            if ln.strip() and "offline" not in ln
        ]
    except Exception:
        return []


def check_ios_simulators() -> list[str]:
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "booted"],
            capture_output=True, text=True, timeout=5,
        )
        devices: list[str] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("==") and not line.startswith("--"):
                m = re.match(r"(.+?)\s+\(([0-9A-F-]+)\)\s+\(Booted\)", line)
                if m:
                    devices.append(m.group(1).strip())
        return devices
    except Exception:
        return []


def _starting_timed_out(section: dict, timeout_seconds: int) -> bool:
    if section.get("status") != "starting" or not section.get("started_at"):
        return False
    try:
        started = datetime.fromisoformat(section["started_at"])
        now = datetime.now(tz=started.tzinfo) if started.tzinfo else datetime.now()
        return (now - started).total_seconds() > timeout_seconds
    except (TypeError, ValueError):
        return False


def get_android_avd_name(serial: str) -> str:
    """Resolve one emulator serial to its exact AVD name."""
    commands = (
        [ADB_BIN, "-s", serial, "emu", "avd", "name"],
        [ADB_BIN, "-s", serial, "shell", "getprop", "ro.boot.qemu.avd_name"],
    )
    for command in commands:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=5
            )
        except Exception:
            continue
        if result.returncode != 0:
            continue
        name = next(
            (
                line.strip()
                for line in (result.stdout or "").splitlines()
                if line.strip() and line.strip() != "OK"
            ),
            "",
        )
        if name:
            return name
    return ""


def detect_android_runtime(session_section: dict) -> dict:
    """저장된 Android 상태를 실제 adb 에뮬레이터 상태와 맞춘다."""
    current = dict(session_section)
    try:
        devices_result = subprocess.run(
            [ADB_BIN, "devices"], capture_output=True, text=True, timeout=5
        )
        if devices_result.returncode != 0:
            return current
    except Exception:
        return current

    emulator_serials = []
    for line in (devices_result.stdout or "").splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0].startswith("emulator-") and parts[1] == "device":
            emulator_serials.append(parts[0])

    if not emulator_serials:
        if current.get("status") == "error":
            return current
        if current.get("status") == "starting" and current.get("avd"):
            if _starting_timed_out(current, 180):
                return {
                    **current,
                    "status": "error",
                    "error_msg": "Android 에뮬레이터 부팅 시간이 180초를 초과했습니다.",
                }
            return current
        return {
            **current,
            "status": "stopped",
            "avd": None,
            "serial": None,
            "started_at": None,
        }

    serial_avds: dict[str, str] = {}
    for candidate in emulator_serials:
        name = get_android_avd_name(candidate)
        if name:
            serial_avds[candidate] = name

    avd_name = current.get("avd")
    if avd_name:
        serial = next(
            (candidate for candidate, name in serial_avds.items() if name == avd_name),
            None,
        )
        if serial is None:
            if current.get("status") == "starting" and not _starting_timed_out(current, 180):
                return {**current, "serial": None}
            return {
                **current,
                "status": "stopped",
                "avd": None,
                "serial": None,
                "started_at": None,
            }
    else:
        serial = next((candidate for candidate in emulator_serials if serial_avds.get(candidate)), None)
        if serial is None:
            return current
        avd_name = serial_avds[serial]
    try:
        boot_result = subprocess.run(
            [ADB_BIN, "-s", serial, "shell", "getprop", "sys.boot_completed"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        booted = boot_result.returncode == 0 and (boot_result.stdout or "").strip() == "1"
    except Exception:
        return current

    if current.get("status") == "stopped" and not booted:
        return current
    if current.get("status") == "error" and not booted:
        return current

    return {
        **current,
        "status": "running" if booted else "starting",
        "avd": avd_name,
        "serial": serial,
        "error_msg": None,
    }


def detect_ios_runtime(session_section: dict) -> dict:
    """저장된 iOS 상태를 실제 CoreSimulator 상태와 맞춘다."""
    import json

    current = dict(session_section)
    if current.get("_command_pending"):
        pending_since = current.get("_command_started_at") or current.get("started_at")
        try:
            started = datetime.fromisoformat(pending_since)
            now = datetime.now(tz=started.tzinfo) if started.tzinfo else datetime.now()
            if (now - started).total_seconds() > 120:
                return {
                    **current,
                    "status": "error",
                    "error_msg": "iOS 시뮬레이터 명령 시간이 120초를 초과했습니다.",
                    "_command_pending": False,
                }
        except (TypeError, ValueError):
            pass
        return current
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "available", "--json"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if result.returncode != 0:
            return current
        payload = json.loads(result.stdout or "{}")
    except Exception:
        return current

    devices = [
        device
        for runtime_devices in payload.get("devices", {}).values()
        for device in runtime_devices
        if device.get("isAvailable", True)
    ]
    target = None
    stored_udid = current.get("udid")
    stored_name = current.get("simulator")
    if stored_udid:
        target = next((item for item in devices if item.get("udid") == stored_udid), None)
    if target is None and stored_name:
        target = next((item for item in devices if item.get("name") == stored_name), None)
    if target is None:
        target = next((item for item in devices if item.get("state") == "Booted"), None)

    if target is not None and target.get("state") == "Booted":
        return {
            **current,
            "status": "running",
            "simulator": target.get("name"),
            "udid": target.get("udid"),
            "error_msg": None,
        }
    if current.get("status") == "starting":
        if _starting_timed_out(current, 120):
            return {
                **current,
                "status": "error",
                "error_msg": "iOS 시뮬레이터 부팅 시간이 120초를 초과했습니다.",
            }
        return current
    if current.get("status") == "error":
        return current
    return {
        **current,
        "status": "stopped",
        "simulator": None,
        "udid": None,
        "started_at": None,
    }


def _http_check_appium(port: int = 4723) -> bool:
    """Appium HTTP 엔드포인트 응답 여부 확인 (내부용, 테스트에서 mock 가능)."""
    import urllib.request
    try:
        urllib.request.urlopen(f"http://localhost:{port}/status", timeout=2)
        return True
    except Exception:
        return False


def _is_process_alive(pid: int) -> bool:
    """PID가 살아있는지 확인 (내부용, 기본 process_finder)."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _fetch_appium_server_metadata(port: int) -> dict:
    """실행 중인 Appium에서 사용자 표시용 버전과 세션 수를 읽는다."""
    import json
    import urllib.error
    import urllib.request

    metadata = {"version": None, "active_sessions": 0}
    try:
        with urllib.request.urlopen(
            f"http://localhost:{port}/status", timeout=2
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        metadata["version"] = (
            payload.get("value", {}).get("build", {}).get("version")
        )
    except Exception:
        pass

    support_key = (port, metadata["version"])
    if _APPIUM_SESSIONS_SUPPORT.get(support_key) is not False:
        try:
            with urllib.request.urlopen(
                f"http://localhost:{port}/sessions", timeout=2
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            sessions = payload.get("value", [])
            if isinstance(sessions, list):
                metadata["active_sessions"] = len(sessions)
            _APPIUM_SESSIONS_SUPPORT[support_key] = True
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 405):
                _APPIUM_SESSIONS_SUPPORT[support_key] = False
        except Exception:
            pass
    return metadata


def _list_installed_appium_drivers() -> dict[str, bool]:
    """Appium CLI 출력에서 필수 드라이버 설치 여부를 확인한다."""
    global _APPIUM_DRIVER_CACHE

    now = time.monotonic()
    if _APPIUM_DRIVER_CACHE is not None:
        cached_at, cached_value = _APPIUM_DRIVER_CACHE
        if now - cached_at < _APPIUM_DRIVER_CACHE_SECONDS:
            return dict(cached_value)

    installed = {"uiautomator2": False, "xcuitest": False}
    try:
        result = subprocess.run(
            [APPIUM_BIN, "driver", "list", "--installed"],
            capture_output=True,
            text=True,
            timeout=5,
            env=subprocess_env_for(APPIUM_BIN),
        )
        if result.returncode == 0:
            output = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
            installed["uiautomator2"] = "uiautomator2" in output
            installed["xcuitest"] = "xcuitest" in output
    except Exception:
        pass
    _APPIUM_DRIVER_CACHE = (now, dict(installed))
    return dict(installed)


def _calculate_uptime_seconds(started_at: str | None) -> int | None:
    """ISO 시작 시각을 카드에 표시할 경과 초로 변환한다."""
    if not started_at:
        return None
    try:
        started = datetime.fromisoformat(started_at)
        now = datetime.now(tz=started.tzinfo) if started.tzinfo else datetime.now()
        return max(0, int((now - started).total_seconds()))
    except (TypeError, ValueError):
        return None
    except Exception:
        return False


def detect_appium_status(process_finder=None) -> dict:
    """Appium 5값 상태 감지.

    Args:
        process_finder: Callable[[int], bool] — pid를 받아 살아있는지 반환.
                        None이면 실제 os.kill(pid, 0) 사용.
                        테스트에서는 lambda pid: True/False 형태로 주입.

    Returns:
        dict with: status(stopped|starting|managed|external|error),
                   pid, port, error_msg
    """
    import json

    # env_session.json 로드
    session: dict = {}
    if ENV_SESSION_PATH.exists():
        try:
            session = json.loads(ENV_SESSION_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    appium = session.get("appium", {})
    stored_status = appium.get("status", "stopped")
    stored_pid = appium.get("pid")
    port = appium.get("port", 4723)
    error_msg = appium.get("error_msg")

    stored_started_at = appium.get("started_at")

    drivers = _list_installed_appium_drivers()

    # error 상태는 사용자 액션 전까지 자동 해소 없음
    if stored_status == "error":
        return {
            "status": "error",
            "pid": stored_pid,
            "port": port,
            "error_msg": error_msg,
            "started_at": stored_started_at,
            "version": None,
            "drivers": drivers,
            "active_sessions": 0,
            "uptime_seconds": _calculate_uptime_seconds(stored_started_at),
            "mjpeg_enabled": None,
        }

    # HTTP 도달 가능 여부 확인
    reachable = _http_check_appium(port)

    # 관리 PID 생존 여부
    _finder = process_finder if process_finder is not None else _is_process_alive
    managed_alive = False
    if stored_pid is not None:
        managed_alive = _finder(stored_pid)

    # 5값 상태 결정
    if managed_alive and reachable:
        status = "managed"
    elif managed_alive and not reachable:
        status = "starting"
    elif not managed_alive and reachable:
        status = "external"
    else:
        status = "stopped"

    if status == "stopped":
        for support_key in list(_APPIUM_SESSIONS_SUPPORT):
            if support_key[0] == port:
                _APPIUM_SESSIONS_SUPPORT.pop(support_key, None)

    if status == "starting" and stored_status == "starting":
        elapsed = _calculate_uptime_seconds(stored_started_at)
        if elapsed is not None and elapsed > 30:
            status = "error"
            error_msg = "Appium 서버 시작 시간이 30초를 초과했습니다. 로그를 확인한 뒤 다시 시도해 주세요."

    server_metadata = (
        _fetch_appium_server_metadata(port)
        if status in ("managed", "external")
        else {"version": None, "active_sessions": 0}
    )

    return {
        "status": status,
        "pid": stored_pid if managed_alive else None,
        "port": port,
        "error_msg": error_msg if status == "error" else None,
        "started_at": stored_started_at,
        "version": server_metadata["version"],
        "drivers": drivers,
        "active_sessions": server_metadata["active_sessions"],
        "uptime_seconds": (
            _calculate_uptime_seconds(stored_started_at)
            if status in ("starting", "managed")
            else None
        ),
        "mjpeg_enabled": True if status == "managed" else None,
    }


def kill_port(port: int) -> None:
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"], capture_output=True, text=True
        )
        pids = result.stdout.strip().splitlines()
        for pid in pids:
            try:
                os.kill(int(pid), 15)
            except Exception:
                pass
        if pids:
            time.sleep(0.5)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# devices.json 헬퍼 (M2.0 배열 스키마 대응)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Appium caps에 전달하지 않을 대시보드 전용 필드
_NON_APPIUM_KEYS: frozenset[str] = frozenset(
    {"default", "wifi_ip", "team_id", "label", "note"}
)


def get_default_device(platform: str, mode: str) -> dict | None:
    """config/devices.json에서 platform+mode의 default:true 항목 반환.

    배열이면 default:true 첫 번째 항목, 없으면 첫 번째 항목.
    dict(구버전 호환)이면 그대로 반환.

    platform: "android" | "ios"
    mode: "emulator" | "real_device" | "simulator"
    """
    import json as _json

    devices_path = _PROJECT_ROOT / "config" / "devices.json"
    try:
        data = _json.loads(devices_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    section = data.get(platform, {}).get(mode)
    if section is None:
        return None

    # 구버전 dict 호환
    if isinstance(section, dict):
        return section

    # 배열: default:true 첫 번째 항목
    for item in section:
        if item.get("default"):
            return item

    # fallback: 첫 번째 항목
    return section[0] if section else None


def filter_appium_caps(device: dict) -> dict:
    """devices.json 항목에서 Appium 비전달 필드를 제거한 caps dict 반환."""
    return {k: v for k, v in device.items() if k not in _NON_APPIUM_KEYS}


# ---------------------------------------------------------------------------
# 실기기 연결 상태 확인 (M3.0)
# ---------------------------------------------------------------------------

def check_android_real_devices(serials: list) -> dict:
    """adb devices 출력에서 serial 연결 여부 반환.

    Args:
        serials: Android 실기기 serial(udid) 목록.

    Returns:
        {serial: connected(bool)} — 실행 실패 시 모두 False.
    """
    if not serials:
        return {}

    connected_serials: set = set()
    try:
        result = subprocess.run(
            [ADB_BIN, "devices"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines()[1:]:
            line = line.strip()
            if line and "\t" in line and "offline" not in line:
                connected_serials.add(line.split("\t")[0])
    except Exception:
        pass

    return {
        serial: bool(serial and serial in connected_serials)
        for serial in serials
    }


def check_ios_real_devices(udids: list) -> dict:
    """xcrun devicectl list devices 또는 instruments 출력에서 udid 연결 여부 반환.

    두 명령 모두 실패해도 API는 정상 응답 (connected=False).

    Args:
        udids: iOS 실기기 udid 목록.

    Returns:
        {udid: connected(bool)} — 실행 실패 시 모두 False.
    """
    if not udids:
        return {}

    output = ""
    for cmd in (
        ["xcrun", "devicectl", "list", "devices"],
        ["xcrun", "instruments", "-s", "devices"],
    ):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=8,
            )
            if result.returncode == 0 and result.stdout.strip():
                output = result.stdout
                break
        except Exception:
            continue

    return {
        udid: bool(udid and udid in output)
        for udid in udids
    }
