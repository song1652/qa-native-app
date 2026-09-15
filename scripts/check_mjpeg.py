"""
MJPEG 스트리밍 환경 확인 스크립트.

Capture Studio의 화면 미러링에 필요한 조건을 점검합니다.

Usage:
    python scripts/check_mjpeg.py [--port 8093]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.request


def check_appium_server() -> tuple[bool, str]:
    """Appium 서버 응답 여부 확인."""
    try:
        resp = urllib.request.urlopen("http://localhost:4723/status", timeout=3)
        return True, "Appium 서버 응답 정상"
    except Exception as exc:
        return False, f"Appium 서버 미응답: {exc}"


def check_allow_insecure_flag(port: int = 4723) -> tuple[bool, str]:
    """
    Appium 서버가 --allow-insecure=adb_screen_streaming 플래그로 실행 중인지 확인.
    직접 확인은 불가능하므로 MJPEG 포트로 HTTP 요청을 시도합니다.
    """
    try:
        resp = urllib.request.urlopen(f"http://localhost:{port}/", timeout=2)
        return True, f"MJPEG 포트 {port} 응답 정상 (활성 Appium 세션 필요)"
    except urllib.error.HTTPError as exc:
        # HTTP 에러도 연결은 된 것
        return True, f"MJPEG 포트 {port} 연결됨 (HTTP {exc.code})"
    except Exception as exc:
        hint = (
            f"\n  → Appium 서버를 다음 플래그와 함께 재시작하세요:\n"
            f"    appium --address 0.0.0.0 --port 4723 --allow-insecure=uiautomator2:adb_screen_streaming\n"
            f"    (Appium 3.x: 드라이버명 prefix 필수. 구버전은 adb_screen_streaming 단독 사용)"
        )
        return False, f"MJPEG 포트 {port} 미응답: {exc}{hint}"


def check_adb() -> tuple[bool, str]:
    """ADB 설치 및 디바이스 연결 확인."""
    try:
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().splitlines()
        devices = [l for l in lines[1:] if l.strip() and "offline" not in l]
        if devices:
            return True, f"ADB 디바이스 연결됨: {', '.join(d.split()[0] for d in devices)}"
        return False, "ADB 연결된 디바이스 없음 (`adb devices` 확인)"
    except FileNotFoundError:
        return False, "adb 명령어를 찾을 수 없습니다. Android SDK platform-tools를 PATH에 추가하세요."
    except Exception as exc:
        return False, f"ADB 확인 실패: {exc}"


def check_uiautomator2() -> tuple[bool, str]:
    """UiAutomator2 드라이버 설치 여부 확인."""
    try:
        result = subprocess.run(
            ["appium", "driver", "list", "--installed"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout + result.stderr
        if "uiautomator2" in output.lower():
            return True, "UiAutomator2 드라이버 설치됨"
        return False, "UiAutomator2 드라이버 미설치 (`appium driver install uiautomator2`)"
    except FileNotFoundError:
        return False, "appium 명령어를 찾을 수 없습니다."
    except Exception as exc:
        return False, f"드라이버 확인 실패: {exc}"


def print_capability_guide(mjpeg_port: int):
    print("\n──────────────────────────────────────────────")
    print("Capture Studio용 Appium capability 설정 가이드")
    print("──────────────────────────────────────────────")
    print(f"""
config/devices.json Android Emulator 섹션에 다음 capability를 추가하세요:

{{
  "mjpegServerPort": {mjpeg_port},
  "mjpegScalingFactor": 75,
  "mjpegServerScreenshotQuality": 70
}}

Appium 서버 실행 명령 (Appium 3.x):
  appium --address 0.0.0.0 --port 4723 --allow-insecure=uiautomator2:adb_screen_streaming

브라우저에서 미러링 확인 (Appium 세션 시작 후):
  http://localhost:{mjpeg_port}/
""")


def main():
    parser = argparse.ArgumentParser(description="Capture Studio MJPEG 환경 확인")
    parser.add_argument("--port", type=int, default=8093, help="MJPEG 서버 포트 (기본: 8093)")
    args = parser.parse_args()

    print("=== Capture Studio 환경 확인 ===\n")

    checks = [
        ("Appium 서버", check_appium_server),
        ("ADB 디바이스", check_adb),
        ("UiAutomator2 드라이버", check_uiautomator2),
        (f"MJPEG 포트 {args.port}", lambda: check_allow_insecure_flag(args.port)),
    ]

    all_pass = True
    for name, check_fn in checks:
        ok, msg = check_fn()
        icon = "✅" if ok else "❌"
        print(f"{icon} {name}: {msg}")
        if not ok:
            all_pass = False

    print()
    if all_pass:
        print("✅ 모든 환경 조건 충족. Capture Studio를 시작할 수 있습니다.")
    else:
        print("⚠️  일부 조건이 충족되지 않았습니다. 위 안내를 확인하세요.")
        print_capability_guide(args.port)
        sys.exit(1)


if __name__ == "__main__":
    main()
