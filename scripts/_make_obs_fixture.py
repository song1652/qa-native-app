"""
관측성 데모 픽스처 데이터 생성기.
실제 기기 없이 state/runs/ 아래 성공/실패 TC 아티팩트를 만들어
대시보드에서 증거 패널을 바로 볼 수 있게 한다.
"""
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
RUNS_DIR = ROOT / "state" / "runs"


def make_fixture():
    stamp = datetime.now()
    run_id = "run_android_{}_{}".format(
        stamp.strftime("%Y%m%d"),
        stamp.strftime("%H%M%S") + "_" + str(stamp.microsecond // 1000).zfill(3),
    )
    art_dir = RUNS_DIR / run_id / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)

    # ─── TC 정의 ──────────────────────────────────────────────────
    tcs = [
        {
            "nodeid": "tests/generated/android/settings/tc_settings_battery.py::test_settings_battery",
            "slug": "tests_generated_android_settings_tc_settings_battery.py__test_settings_battery",
            "outcome": "failed",
            "attempt_count": 3,
            "duration_sec": 41.6,
            "failure_offset_sec": 39.1,
        },
        {
            "nodeid": "tests/generated/android/settings/tc_settings_location.py::test_settings_location",
            "slug": "tests_generated_android_settings_tc_settings_location.py__test_settings_location",
            "outcome": "passed",
            "attempt_count": 1,
            "duration_sec": 18.3,
            "failure_offset_sec": None,
        },
        {
            "nodeid": "tests/generated/android/settings/tc_settings_wifi.py::test_settings_wifi",
            "slug": "tests_generated_android_settings_tc_settings_wifi.py__test_settings_wifi",
            "outcome": "failed",
            "attempt_count": 1,
            "duration_sec": 22.7,
            "failure_offset_sec": 21.2,
        },
        {
            "nodeid": "tests/generated/android/settings/tc_settings_display.py::test_settings_display",
            "slug": "tests_generated_android_settings_tc_settings_display.py__test_settings_display",
            "outcome": "passed",
            "attempt_count": 1,
            "duration_sec": 11.4,
            "failure_offset_sec": None,
        },
        {
            "nodeid": "tests/generated/android/settings/tc_settings_sound.py::test_settings_sound",
            "slug": "tests_generated_android_settings_tc_settings_sound.py__test_settings_sound",
            "outcome": "error",
            "attempt_count": 2,
            "duration_sec": 5.2,
            "failure_offset_sec": 4.8,
        },
    ]

    entries = []
    t = stamp

    for tc in tcs:
        slug = tc["slug"]
        tc_dir = art_dir / slug
        tc_dir.mkdir(parents=True, exist_ok=True)

        outcome = tc["outcome"]
        keep = outcome in ("failed", "error") or tc["attempt_count"] > 1

        started_at = t
        finished_at = t + timedelta(seconds=tc["duration_sec"])
        t = finished_at + timedelta(seconds=2)

        video_info = None
        syslog_info = None

        if keep:
            # ── 더미 syslog 생성 ────────────────────────────────
            syslog_path = tc_dir / "syslog.txt"
            lines = _make_fake_logcat(tc["nodeid"], outcome)
            syslog_path.write_text("\n".join(lines), encoding="utf-8")
            syslog_info = {
                "path": f"{slug}/syslog.txt",
                "bytes": syslog_path.stat().st_size,
                "source": "adb_logcat",
                "truncated": False,
            }

            # ── 더미 video (1KB 헤더만 있는 mp4) ─────────────────
            video_path = tc_dir / "video.mp4"
            _make_fake_mp4(video_path)
            video_info = {
                "path": f"{slug}/video.mp4",
                "bytes": video_path.stat().st_size,
                "source": "adb_screenrecord",
                "truncated": False,
            }

        # ── 스크린샷 (실패 TC만) ─────────────────────────────────
        screenshot_info = None
        if outcome in ("failed", "error"):
            shot_dir = ROOT / "reports" / "screenshots" / "android"
            shot_dir.mkdir(parents=True, exist_ok=True)
            safe_name = tc["nodeid"].replace("/", "_").replace("::", "__")
            shot_path = shot_dir / f"{safe_name}.png"
            _make_fake_png(shot_path)
            screenshot_info = {
                "path": f"reports/screenshots/android/{safe_name}.png",
                "external": True,
            }

        entries.append({
            "nodeid": tc["nodeid"],
            "slug": slug,
            "outcome": outcome,
            "attempt_count": tc["attempt_count"],
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_sec": tc["duration_sec"],
            "kept": keep,
            "failure_offset_sec": tc["failure_offset_sec"],
            "video": video_info,
            "syslog": syslog_info,
            "screenshot": screenshot_info,
            "network": None,
            "collect_errors": [],
        })

    manifest = {
        "run_id": run_id,
        "platform": "android",
        "mode": "emulator",
        "udid": "emulator-5554",
        "device_name": "Android Emulator",
        "keep_policy": "on_failure",
        "started_at": stamp.isoformat(),
        "finished_at": t.isoformat(),
        "entries": entries,
    }

    tmp = art_dir / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(art_dir / "manifest.json")

    print(f"[fixture] run_id: {run_id}")
    print(f"[fixture] artifact_dir: {art_dir}")
    print(f"[fixture] entries: {len(entries)} TC ({sum(1 for e in entries if e['outcome']=='passed')} pass / {sum(1 for e in entries if e['outcome'] in ('failed','error'))} fail)")
    return run_id


def _make_fake_logcat(nodeid: str, outcome: str) -> list:
    """그럴싸한 adb logcat 더미 라인 생성."""
    pkg = "com.example.app"
    lines = []
    lines.append("--------- beginning of main")
    lines.append("--------- beginning of system")
    for i in range(30):
        lines.append(f"09-17 14:31:{i:02d}.{i*31%1000:03d}  1234  5678 I {pkg}: Navigating screen {i+1}")
        lines.append(f"09-17 14:31:{i:02d}.{i*17%1000+200:03d}  1234  5678 D ViewRootImpl: ViewRoot draw (frame {i})")
    if outcome in ("failed", "error"):
        lines.append(f"09-17 14:31:39.100  1234  5678 E {pkg}: AssertionError: Expected element 'battery_level' to be visible")
        lines.append(f"09-17 14:31:39.102  1234  5678 E AndroidRuntime: FATAL EXCEPTION: appium-worker")
        lines.append(f"09-17 14:31:39.103  1234  5678 E AndroidRuntime: Process: {pkg}, PID: 1234")
        lines.append(f"09-17 14:31:39.104  1234  5678 E AndroidRuntime:   at org.junit.Assert.fail(Assert.java:89)")
        lines.append(f"09-17 14:31:39.105  1234  5678 E AndroidRuntime:   at {pkg}.BatteryTest.testBatteryLevel(BatteryTest.java:42)")
        lines.append(f"09-17 14:31:39.200  1234  5678 W {pkg}: Test failed after 39.1s")
    else:
        lines.append(f"09-17 14:31:18.300  1234  5678 I {pkg}: Test passed successfully")
        lines.append(f"09-17 14:31:18.301  1234  5678 I {pkg}: All assertions verified")
    return lines


def _make_fake_mp4(path: Path) -> None:
    """재생 불가능하지만 MIME 타입 감지 가능한 최소 MP4 헤더."""
    # ftyp + mdat box — 브라우저 video player가 invalid codec으로 표시하지만
    # 파일 자체는 존재해서 API /video 엔드포인트 테스트 가능
    header = (
        b"\x00\x00\x00\x18ftypisom"
        b"\x00\x00\x02\x00isomiso2mp41"
        b"\x00\x00\x00\x08mdat"
        + b"\x00" * 512
    )
    path.write_bytes(header)


def _make_fake_png(path: Path) -> None:
    """최소 1x1 PNG 파일."""
    # PNG 시그니처 + IHDR + IDAT + IEND
    png_1x1 = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR length + type
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # width=1, height=1
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,  # bit depth, color type
        0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT
        0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
        0x00, 0x00, 0x02, 0x00, 0x01, 0xE2, 0x21, 0xBC,
        0x33, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,  # IEND
        0x44, 0xAE, 0x42, 0x60, 0x82,
    ])
    path.write_bytes(png_1x1)


if __name__ == "__main__":
    run_id = make_fixture()
    print(f"\n대시보드에서 확인: http://localhost:8000")
    print(f"API: http://localhost:8000/api/run_artifacts/{run_id}")
