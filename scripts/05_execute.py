"""
05_execute.py — pytest + Appium 실행.

Usage:
    python scripts/05_execute.py [--platform android|ios] [--no-report] [--only-failed]
                                  [--report] [--record]
"""
import argparse
import json
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
SCREENSHOTS_JSON = ROOT / "state" / "screenshots.json"


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


def _start_screen_recording(device_id: str) -> "subprocess.Popen":
    subprocess.run(
        [ADB, "-s", device_id, "shell", "rm", "-f", "/sdcard/qa_record.mp4"],
        capture_output=True,
    )
    return subprocess.Popen(
        [ADB, "-s", device_id, "shell", "screenrecord",
         "--time-limit", "300", "/sdcard/qa_record.mp4"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop_and_pull_recording(proc: "subprocess.Popen",
                              device_id: str,
                              local_path: Path) -> bool:
    proc.terminate()
    time.sleep(2)  # flush buffer
    local_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [ADB, "-s", device_id, "pull", "/sdcard/qa_record.mp4", str(local_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not local_path.exists():
        print(f"[05_execute] WARNING: screen recording pull failed — {result.stderr.strip()}")
        return False
    print(f"[05_execute] Screen recording saved: {local_path}")
    return True


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


def _load_screenshots_map() -> dict:
    """state/screenshots.json → {nodeid: relative_path} 매핑 반환."""
    if SCREENSHOTS_JSON.exists():
        try:
            return json.loads(SCREENSHOTS_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _inject_screenshots(errors: list) -> list:
    """errors[] 각 항목에 screenshot 필드를 추가한다.

    conftest.py가 저장한 screenshots.json을 읽어 nodeid 기반으로 매핑한다.
    nodeid 형식: tests/generated/android/tc_001.py::TestFoo::test_bar
    errors[].test 는 pytest testcase name (test_bar 부분).
    """
    shots = _load_screenshots_map()
    if not shots:
        return errors

    result = []
    for entry in errors:
        entry = dict(entry)
        test_name = entry.get("test", "")
        filepath = entry.get("file", "")
        matched = ""
        # nodeid에 filepath와 test_name이 모두 포함된 항목 탐색
        for nodeid, rel_path in shots.items():
            if filepath.replace("/", "_") in nodeid or test_name in nodeid:
                matched = rel_path
                break
        entry["screenshot"] = matched
        result.append(entry)
    return result


def _has_json_report_plugin() -> bool:
    """pytest-json-report 패키지 설치 여부 확인."""
    try:
        import importlib.util
        return importlib.util.find_spec("pytest_jsonreport") is not None
    except Exception:
        return False


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
            longrepr = call_info.get("longrepr", "") or ""
            first_line = longrepr.splitlines()[0] if longrepr else "Unknown error"
            errors.append({"file": filepath, "test": test_name, "error": first_line})
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
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--only-failed", action="store_true")
    parser.add_argument("--record", action="store_true",
                        help="Record emulator screen during test run (requires --report)")
    args = parser.parse_args()

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
    platform = args.platform

    # 플랫폼 전환 시 이전 실행 아티팩트 초기화
    prev_platform = state.get("platform")
    if prev_platform and prev_platform != platform:
        print(f"[05_execute] 플랫폼 전환 감지: {prev_platform} → {platform}")
        if SCREENSHOTS_JSON.exists():
            SCREENSHOTS_JSON.write_text("{}", encoding="utf-8")
            print("[05_execute] screenshots.json 초기화 완료")

    test_dir = TESTS_DIR / platform
    if args.tc_dir:
        test_dir = test_dir / args.tc_dir
        print(f"[05_execute] TC 폴더 지정: {test_dir.relative_to(ROOT)}")

    if not test_dir.exists():
        print(f"[05_execute] No tests found at {test_dir}")
        sys.exit(1)

    use_json_report = _has_json_report_plugin()
    cmd = [
        "python", "-m", "pytest", str(test_dir), "-v",
        f"--junit-xml={JUNIT_XML}",
    ]
    if use_json_report:
        cmd += [
            "--json-report",
            f"--json-report-file={JSON_REPORT}",
        ]
        print("[05_execute] Using pytest-json-report for result parsing.")

    if args.only_failed:
        cmd.append("--lf")

    if not args.no_report:
        report_dir = ROOT / "tests" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        cmd += [f"--html={report_dir}/report_{platform}.html", "--self-contained-html"]

    # Screen recording
    rec_proc = None
    video_path = None
    if args.record and platform == "android":
        device_id = _get_device_id()
        if device_id:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            video_path = REPORTS_DIR / "recordings" / f"test_run_{ts}.mp4"
            print(f"[05_execute] Starting screen recording on {device_id} ...")
            rec_proc = _start_screen_recording(device_id)
        else:
            print("[05_execute] WARNING: --record skipped, no device found")

    print(f"[05_execute] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)

    if rec_proc is not None:
        device_id = _get_device_id()
        _stop_and_pull_recording(rec_proc, device_id, video_path)
        if video_path and video_path.exists():
            state["video_path"] = str(video_path)

    # Parse results: JSON report preferred, JUnit XML as fallback
    if use_json_report and JSON_REPORT.exists():
        print("[05_execute] Parsing JSON report results...")
        report_data = parse_json_report(JSON_REPORT)
    else:
        print("[05_execute] Parsing JUnit XML results...")
        report_data = parse_junit_xml(JUNIT_XML)
    errors_with_shots = _inject_screenshots(report_data["errors"])
    execute_results = {
        "exit_code": result.returncode,
        "errors": errors_with_shots,
        "passed": report_data["passed"],
        "summary": report_data["summary"],
    }

    state["step"] = "executed"
    state["execute_results"] = execute_results
    # Keep legacy field for backwards compatibility
    state["last_exit_code"] = result.returncode
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
        _generate_html_report(state, platform, video_path)

    sys.exit(result.returncode)


def _generate_html_report(state: dict, platform: str,
                           video_path: "Path | None" = None):
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
        video_path=rel_video, platform=platform
    )

    report_path = REPORTS_DIR / f"report_{platform}.html"
    report_path.write_text(html_content, encoding="utf-8")
    print(f"[05_execute] HTML report saved: {report_path}")

    state["report_path"] = str(report_path)
    save_state(state)


if __name__ == "__main__":
    main()
