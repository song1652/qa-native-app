"""
03_lint.py — 생성된 테스트 파일에 flake8 실행, 결과를 pipeline.json에 저장.

state/pipeline.json의 generated_tests 목록을 읽어 각 파일에 flake8을 실행한다.
전체 통과 시 step: "linted", 하나라도 실패 시 step: "lint_failed" + exit code 1.

Usage:
    python scripts/03_lint.py [--platform android|ios]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "pipeline.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {
        "step": "init",
        "dom_info": {},
        "generated_tests": [],
        "lint_results": {},
        "execute_results": {},
    }


def save_state(state: dict):
    STATE_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_flake8(file_path: str) -> tuple:
    """flake8을 파일에 실행하고 (passed: bool, output: str)을 반환한다."""
    result = subprocess.run(
        [sys.executable, "-m", "flake8", file_path],
        capture_output=True,
        text=True,
    )
    passed = result.returncode == 0
    output = (result.stdout + result.stderr).strip()
    return passed, output


def main():
    parser = argparse.ArgumentParser(
        description="생성된 테스트 파일 flake8 lint 검사"
    )
    parser.add_argument(
        "--platform", default="android", choices=["android", "ios"]
    )
    args = parser.parse_args()

    print(f"[03_lint] platform={args.platform}")

    state = load_state()
    generated_tests = state.get("generated_tests", [])

    if not generated_tests:
        print("[03_lint] WARNING: generated_tests가 비어 있습니다."
              " 먼저 02_generate.py를 실행하세요.")
        sys.exit(1)

    print(f"[03_lint] {len(generated_tests)}개 파일 검사 시작")

    passed_files = []
    failed_files = []

    for file_path in generated_tests:
        path = Path(file_path)
        if not path.exists():
            print(f"  missing: {file_path}")
            failed_files.append({"file": file_path, "errors": "File not found"})
            continue

        ok, output = run_flake8(file_path)
        if ok:
            passed_files.append(file_path)
            print(f"  pass: {path.name}")
        else:
            failed_files.append({"file": file_path, "errors": output})
            print(f"  FAIL: {path.name}")
            for line in output.splitlines():
                print(f"        {line}")

    state["lint_results"] = {
        "passed": passed_files,
        "failed": failed_files,
    }

    if failed_files:
        state["step"] = "lint_failed"
        save_state(state)
        print(
            f"[03_lint] FAILED — {len(failed_files)} 파일 오류,"
            f" {len(passed_files)} 파일 통과"
        )
        sys.exit(1)
    else:
        state["step"] = "linted"
        save_state(state)
        print(
            f"[03_lint] done — {len(passed_files)} 파일 모두 통과"
        )


if __name__ == "__main__":
    main()
