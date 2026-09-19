import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent
DEMO_DIR = ROOT / "tests" / "generated" / "ios" / "obs_demo"


def test_ios_obs_demo_has_one_pass_and_two_failures(tmp_path):
    report = tmp_path / "ios_obs_demo.json"
    env = os.environ.copy()
    env["QA_OBS_DISABLE"] = "1"
    env.pop("DEVICE_UDID", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(DEMO_DIR),
            "-q",
            "--tb=no",
            "--json-report",
            f"--json-report-file={report}",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 1
    data = json.loads(report.read_text(encoding="utf-8"))
    outcomes = {
        test["nodeid"].split("::")[-1]: test["outcome"]
        for test in data["tests"]
    }
    assert outcomes == {
        "test_device_information_visible": "passed",
        "test_display_brightness_slider_exists": "failed",
        "test_wifi_toggle_state": "failed",
    }
