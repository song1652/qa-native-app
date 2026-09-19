"""
05_execute.py — pytest + Appium 실행.

Usage:
    python scripts/05_execute.py [--platform android|ios] [--no-report] [--only-failed]
                                  [--report] [--record]
"""
import argparse
import importlib.util
import json
import os
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
STATE_DIR = ROOT / "state"


def _find_adb() -> str:
    import shutil
    import os
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
STATE_FILE = STATE_DIR / "pipeline.json"
TESTS_DIR = ROOT / "tests" / "generated"
JUNIT_XML = STATE_DIR / "pytest_report.xml"
JSON_REPORT = STATE_DIR / "pytest_report.json"
REPORTS_DIR = ROOT / "tests" / "reports"


def _pytest_html_options(report_path: Path) -> list[str]:
    """Return pytest-html flags only when its plugin is installed."""
    if importlib.util.find_spec("pytest_html") is None:
        return []
    return [f"--html={report_path}", "--self-contained-html"]


def check_appium_server() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:4723/status", timeout=3)
        return True
    except Exception:
        return False


def check_android_device() -> bool:
    result = subprocess.run([ADB, "devices"], capture_output=True, text=True)
    lines = result.stdout.strip().splitlines()
    connected = [ln for ln in lines[1:] if ln.strip() and "offline" not in ln]
    return len(connected) > 0


def _get_device_id() -> str:
    result = subprocess.run([ADB, "devices"], capture_output=True, text=True)
    for line in result.stdout.strip().splitlines()[1:]:
        if line.strip() and "offline" not in line:
            return line.split()[0]
    return ""


def _start_screen_recording(device_id: str) -> int | None:
    subprocess.run(
        [ADB, "-s", device_id, "shell", "rm", "-f", "/sdcard/qa_record.mp4"],
        capture_output=True,
    )
    result = subprocess.run(
        [
            ADB,
            "-s",
            device_id,
            "shell",
            "screenrecord --time-limit 300 /sdcard/qa_record.mp4 "
            ">/dev/null 2>&1 & echo $!",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode == 0:
        for line in reversed(result.stdout.splitlines()):
            if line.strip().isdigit():
                return int(line.strip())
    return None


def _valid_recording(path: Path) -> bool:
    try:
        data = path.read_bytes()
        idx = data.find(b"mvhd")
        if idx < 4 or idx + 24 > len(data):
            return False
        version = data[idx + 4]
        if version == 0:
            timescale = struct.unpack(">I", data[idx + 16:idx + 20])[0]
            duration = struct.unpack(">I", data[idx + 20:idx + 24])[0]
        elif version == 1 and idx + 36 <= len(data):
            timescale = struct.unpack(">I", data[idx + 24:idx + 28])[0]
            duration = struct.unpack(">Q", data[idx + 28:idx + 36])[0]
        else:
            return False
        return bool(timescale and duration)
    except (OSError, struct.error):
        return False


def _stop_and_pull_recording(pid: int,
                              device_id: str,
                              local_path: Path) -> bool:
    subprocess.run(
        [ADB, "-s", device_id, "shell", "kill", "-2", str(pid)],
        capture_output=True,
        timeout=10,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        alive = subprocess.run(
            [ADB, "-s", device_id, "shell", "kill", "-0", str(pid)],
            capture_output=True,
            timeout=10,
        )
        if alive.returncode != 0:
            break
        time.sleep(0.2)
    else:
        subprocess.run(
            [ADB, "-s", device_id, "shell", "kill", "-9", str(pid)],
            capture_output=True,
            timeout=10,
        )
    time.sleep(0.5)
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [ADB, "-s", device_id, "pull", "/sdcard/qa_record.mp4", str(local_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0 or not _valid_recording(local_path):
            local_path.unlink(missing_ok=True)
            print(f"[05_execute] WARNING: screen recording invalid — {result.stderr.strip()}")
            return False
        print(f"[05_execute] Screen recording saved: {local_path}")
        return True
    finally:
        subprocess.run(
            [ADB, "-s", device_id, "shell", "rm", "-f", "/sdcard/qa_record.mp4"],
            capture_output=True,
        )


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _classname_to_filepath(classname: str) -> str:
    """JUnit classname (dot-separated) → relative file path with .py suffix.

    Example: tests.generated.android.tc_001_login → tests/generated/android/tc_001_login.py
    """
    return classname.replace(".", "/") + ".py"


def _has_json_report_plugin() -> bool:
    """pytest-json-report 패키지 설치 여부 확인."""
    try:
        import importlib.util
        return importlib.util.find_spec("pytest_jsonreport") is not None
    except Exception:
        return False


def _has_rerun_plugin() -> bool:
    """pytest-rerunfailures 패키지 설치 여부 확인."""
    try:
        import importlib.util
        return importlib.util.find_spec("pytest_rerunfailures") is not None
    except Exception:
        return False


def _pytest_rerun_options(disabled: bool) -> list[str]:
    """Return the existing retry policy unless one-attempt mode is requested."""
    if disabled or not _has_rerun_plugin():
        return []
    return ["--reruns", "2", "--reruns-delay", "5"]


def parse_json_report(json_path: Path) -> dict:
    """Parse pytest-json-report JSON and return execute_results dict.

    Returns:
        {
            "errors": [{"file": str, "test": str, "error": str}],
            "passed": [str],
            "summary": {"total": int, "passed": int, "failed": int}
        }
    """
    errors = []
    passed = []

    if not json_path.exists():
        print(f"[05_execute] WARNING: JSON report not found at {json_path}")
        return {"errors": errors, "passed": passed,
                "summary": {"total": 0, "passed": 0, "failed": 0}}

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[05_execute] WARNING: Failed to parse JSON report: {exc}")
        return {"errors": errors, "passed": passed,
                "summary": {"total": 0, "passed": 0, "failed": 0}}

    seen_files: dict = {}

    for test in data.get("tests", []):
        nodeid = test.get("nodeid", "")
        outcome = test.get("outcome", "")

        # nodeid 형식: tests/generated/android/tc_001_login.py::test_func
        if "::" in nodeid:
            filepath, test_name = nodeid.split("::", 1)
            # 클래스 메서드인 경우 마지막 부분만 test name으로 사용
            test_name = test_name.split("::")[-1]
        else:
            filepath = nodeid
            test_name = ""

        if outcome in ("failed", "error"):
            call_info = test.get("call") or test.get("setup") or {}
            crash_message = (call_info.get("crash") or {}).get("message", "")
            if not crash_message:
                longrepr = call_info.get("longrepr", "") or ""
                # longrepr의 첫 줄은 "self = <ClassName object at 0x...>"이므로
                # "E   " 접두 실제 실패 라인을 찾아 사용한다.
                error_line = next(
                    (
                        ln.strip()[2:].strip()
                        for ln in longrepr.splitlines()
                        if ln.strip().startswith("E ") or ln.strip() == "E"
                    ),
                    "",
                )
                crash_message = error_line or (longrepr.splitlines()[-1] if longrepr else "Unknown error")
            errors.append({"file": filepath, "test": test_name, "error": crash_message})
            seen_files[filepath] = False
        elif outcome == "passed":
            if filepath not in seen_files:
                seen_files[filepath] = True
                passed.append(f"{filepath}::{test_name}" if test_name else filepath)

    # summary fallback to summary block in JSON report
    summary_block = data.get("summary", {})
    total = summary_block.get("total", len(seen_files))
    failed_count = summary_block.get("failed", 0) + summary_block.get("error", 0)
    passed_count = summary_block.get("passed", total - failed_count)

    return {
        "errors": errors,
        "passed": passed,
        "summary": {"total": total, "passed": passed_count, "failed": failed_count},
    }


def parse_junit_xml(xml_path: Path) -> dict:
    """Parse JUnit XML and return execute_results dict.

    Returns:
        {
            "errors": [{"file": str, "error": str}],
            "passed": [str],
            "summary": {"total": int, "passed": int, "failed": int}
        }
    """
    errors = []
    passed = []

    if not xml_path.exists():
        print(f"[05_execute] WARNING: JUnit XML not found at {xml_path}")
        return {"errors": errors, "passed": passed,
                "summary": {"total": 0, "passed": 0, "failed": 0}}

    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
    except ET.ParseError as exc:
        print(f"[05_execute] WARNING: Failed to parse JUnit XML: {exc}")
        return {"errors": errors, "passed": passed,
                "summary": {"total": 0, "passed": 0, "failed": 0}}

    # Support both <testsuites><testsuite> and bare <testsuite>
    if root.tag == "testsuites":
        testsuites = root.findall("testsuite")
    elif root.tag == "testsuite":
        testsuites = [root]
    else:
        testsuites = root.findall(".//testsuite")

    seen_files: dict = {}  # filepath -> bool (True = all passed so far)

    for testsuite in testsuites:
        for testcase in testsuite.findall("testcase"):
            classname = testcase.get("classname", "")
            name = testcase.get("name", "")
            filepath = _classname_to_filepath(classname) if classname else ""

            failure = testcase.find("failure")
            error_el = testcase.find("error")

            if failure is not None or error_el is not None:
                msg_el = failure if failure is not None else error_el
                msg = (msg_el.get("message") or msg_el.text or "").strip()
                first_line = msg.splitlines()[0] if msg else "Unknown error"
                errors.append({"file": filepath, "test": name, "error": first_line})
                seen_files[filepath] = False
            else:
                # Only mark as passed if no prior failure for this file
                if filepath not in seen_files:
                    seen_files[filepath] = True

    for filepath, all_passed in seen_files.items():
        if all_passed:
            passed.append(filepath)

    total = len(seen_files)
    failed_count = sum(1 for v in seen_files.values() if not v)
    passed_count = total - failed_count

    return {
        "errors": errors,
        "passed": passed,
        "summary": {"total": total, "passed": passed_count, "failed": failed_count},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default="android", choices=["android", "ios"])
    parser.add_argument("--tc-dir", default=None,
                        help="tests/generated/{platform}/ 하위 폴더명 (미지정 시 전체 실행)")
    parser.add_argument("--test-file", default=None,
                        help="tests/generated/{platform}/ 기준 단일 생성 파일 경로")
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--only-failed", action="store_true")
    parser.add_argument(
        "--no-rerun", action="store_true",
        help="Disable pytest-rerunfailures and execute each test exactly once",
    )
    parser.add_argument("--record", action="store_true",
                        help="Record emulator screen during test run (requires --report)")
    parser.add_argument("--mode", default=None,
                        choices=["emulator", "real_device", "simulator"],
                        help="런타임 디바이스 모드 오버라이드 (DEVICE_MODE env)")
    parser.add_argument("--udid", default=None,
                        help="런타임 디바이스 UDID 오버라이드 (DEVICE_UDID env)")
    args = parser.parse_args()
    # PRD §4-1: report_stamp 재사용 — run_id와 리포트 파일명이 같은 타임스탬프를 공유
    report_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    platform = args.platform

    # run_id 발급 (QA_RUN_ID가 이미 설정된 경우 — pipeline.py에서 발급 — 재사용)
    run_id = os.environ.get("QA_RUN_ID", "").strip() or f"run_{platform}_{report_stamp}"

    # 디바이스 연결 가드
    if args.platform == "android":
        if not check_android_device():
            print("[05_execute] ERROR: Android device/emulator not connected.")
            print("  Run: adb devices")
            sys.exit(1)

    if not check_appium_server():
        print("[05_execute] ERROR: Appium server not running.")
        print("  Run: appium --address 0.0.0.0 --port 4723")
        sys.exit(1)

    state = load_state()

    # 플랫폼 전환 시 이전 실행 아티팩트 초기화
    prev_platform = state.get("platform")
    if prev_platform and prev_platform != platform:
        print(f"[05_execute] 플랫폼 전환 감지: {prev_platform} → {platform}")

    test_dir = TESTS_DIR / platform
    if args.tc_dir:
        test_dir = test_dir / args.tc_dir
        print(f"[05_execute] TC 폴더 지정: {test_dir.relative_to(ROOT)}")

    if not test_dir.exists():
        print(f"[05_execute] No tests found at {test_dir}")
        sys.exit(1)

    if args.test_file:
        candidate = (TESTS_DIR / platform / args.test_file).resolve()
        if candidate.suffix != ".py" or not candidate.is_file() or not candidate.is_relative_to((TESTS_DIR / platform).resolve()):
            print(f"[05_execute] Invalid test file: {args.test_file}")
            sys.exit(1)
        test_target = candidate
    else:
        test_target = test_dir

    use_json_report = _has_json_report_plugin()
    cmd = [
        sys.executable, "-m", "pytest", str(test_target), "-v",
        f"--junit-xml={JUNIT_XML}",
    ]
    if use_json_report:
        cmd += [
            "--json-report",
            f"--json-report-file={JSON_REPORT}",
        ]
        print("[05_execute] Using pytest-json-report for result parsing.")

    # Appium 세션 초기화 실패(setup error) 자동 재시도 — 5초 대기 후 최대 2회
    rerun_options = _pytest_rerun_options(args.no_rerun)
    if rerun_options:
        cmd += rerun_options
        print("[05_execute] pytest-rerunfailures: setup 실패 시 최대 2회 재시도 (5초 대기)")
    elif args.no_rerun:
        print("[05_execute] 단일 실행 모드: 실패 재시도 비활성화")

    if args.only_failed:
        cmd.append("--lf")

    if not args.no_report:
        report_dir = ROOT / "tests" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_name = f"report_{platform}_{report_stamp}.html"
        html_options = _pytest_html_options(report_dir / report_name)
        cmd += html_options
        if not html_options:
            print("[05_execute] pytest-html not installed; using built-in report generator only.")

    # Screen recording
    rec_pid = None
    rec_device_id = None
    video_path = None
    if args.record and platform == "android":
        device_id = _get_device_id()
        if device_id:
            rec_device_id = device_id
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            video_path = REPORTS_DIR / "recordings" / f"test_run_{ts}.mp4"
            print(f"[05_execute] Starting screen recording on {device_id} ...")
            rec_pid = _start_screen_recording(device_id)
        else:
            print("[05_execute] WARNING: --record skipped, no device found")

    run_env = os.environ.copy()
    # QA_RUN_ID · QA_OBS_KEEP 주입 (pytest subprocess에 전달)
    run_env["QA_RUN_ID"] = run_id
    run_env["QA_PLATFORM"] = platform
    run_env.setdefault("QA_OBS_KEEP", "on_failure")
    if rec_pid is not None:
        # A device can run only one screenrecord encoder reliably. The legacy
        # whole-run recorder and per-TC collector must never compete.
        run_env["QA_OBS_DISABLE"] = "1"
    print(f"[05_execute] QA_RUN_ID={run_id}")

    if args.mode:
        run_env['DEVICE_MODE'] = args.mode
        print(f"[05_execute] DEVICE_MODE={args.mode}")
    if args.udid:
        run_env['DEVICE_UDID'] = args.udid
        print(f"[05_execute] DEVICE_UDID={args.udid}")

    print(f"[05_execute] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT, env=run_env)

    if rec_pid is not None and rec_device_id is not None:
        _stop_and_pull_recording(rec_pid, rec_device_id, video_path)
        if video_path and video_path.exists():
            state["video_path"] = str(video_path)

    # Parse results: JSON report preferred, JUnit XML as fallback
    if use_json_report and JSON_REPORT.exists():
        print("[05_execute] Parsing JSON report results...")
        report_data = parse_json_report(JSON_REPORT)
    else:
        print("[05_execute] Parsing JUnit XML results...")
        report_data = parse_junit_xml(JUNIT_XML)
    execute_results = {
        "exit_code": result.returncode,
        "errors": report_data["errors"],
        "passed": report_data["passed"],
        "summary": report_data["summary"],
    }

    state["step"] = "executed"
    state["execute_results"] = execute_results
    # Keep legacy field for backwards compatibility
    state["last_exit_code"] = result.returncode
    # PRD §4-1: last_run_id 기록 — 리포트·대시보드가 역참조
    state["last_run_id"] = run_id
    save_state(state)

    summary = report_data["summary"]
    print(
        f"[05_execute] Results: "
        f"{summary['passed']} passed, "
        f"{summary['failed']} failed / "
        f"{summary['total']} total"
    )

    # HTML report — --no-report 플래그가 없으면 자동 생성
    if not args.no_report:
        _generate_html_report(state, platform, video_path, report_stamp)

    sys.exit(result.returncode)


def _generate_html_report(state: dict, platform: str,
                           video_path: "Path | None" = None,
                           report_stamp: str | None = None):
    """Generate HTML report using report_html.parse_pipeline_to_groups + build_report."""
    import importlib.util
    report_html_path = Path(__file__).parent / "report_html.py"
    spec = importlib.util.spec_from_file_location("report_html", report_html_path)
    report_html = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report_html)

    groups_data = report_html.parse_pipeline_to_groups(state)

    execute_results = state.get("execute_results", {})
    summary_raw = execute_results.get("summary", {})
    summary = {
        "passed": summary_raw.get("passed", 0),
        "failed": summary_raw.get("failed", 0),
        "error": 0,
        "skipped": 0,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    rel_video: "str | None" = None
    if video_path and video_path.exists():
        try:
            rel_video = str(video_path.relative_to(REPORTS_DIR))
        except ValueError:
            rel_video = str(video_path)

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subtitle = f"{platform.upper()} Test Report"
    html_content = report_html.build_report(
        groups_data, summary, created_at, subtitle,
        video_path=rel_video, platform=platform,
    )

    stamp = report_stamp or datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    report_path = REPORTS_DIR / f"report_{platform}_{stamp}.html"
    report_path.write_text(html_content, encoding="utf-8")
    print(f"[05_execute] HTML report saved: {report_path}")

    state["report_path"] = str(report_path)
    save_state(state)


if __name__ == "__main__":
    main()
