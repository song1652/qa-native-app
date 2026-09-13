"""
utils/system.py — 시스템 환경 확인 유틸리티.

Appium 서버 상태, Android/iOS 디바이스 목록, 포트 강제 종료.
"""
from __future__ import annotations

import os
import re
import subprocess
import time

import sys
from pathlib import Path

# shared.py 가 agents/dashboard/ 에 있으므로 같은 디렉토리 기준으로 임포트
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import ADB_BIN  # noqa: E402


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
