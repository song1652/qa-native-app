"""pytest conftest — 실패 시 Appium driver screenshot 자동 캡처 + TC 실행 관측성."""
import sys
from pathlib import Path
from typing import Optional

import pytest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    # --import-mode=importlib does not guarantee that the repository root is
    # importable, while generated artifacts intentionally reuse scripts/*.
    sys.path.insert(0, str(ROOT))

# 관측 헬퍼 import (기기 없어도 안전하게 로드)
try:
    import tests._observability as _obs  # type: ignore[import]
    _OBS_AVAILABLE = True
except Exception:
    _OBS_AVAILABLE = False


def pytest_sessionstart(session):
    """관측: manifest 초기화."""
    if _OBS_AVAILABLE:
        try:
            _obs.session_start(session.config)
        except Exception as e:
            print(f"\n[conftest] obs session_start error: {e}")


def pytest_runtest_setup(item):
    """관측: tests/generated/ TC에 한해 영상·로그 프로세스 시작."""
    if _OBS_AVAILABLE:
        try:
            _obs.start(item)
        except Exception as e:
            print(f"\n[conftest] obs start error: {e}")


# 프로세스 전역 — teardown 훅에서 stop() 호출 시 스크린샷 경로 전달용
_last_screenshot: dict = {}  # {nodeid: Path}

# pytest phase별 outcome. setup/teardown 실패는 관측 결과에서 error로 보존한다.
_phase_outcomes: dict = {}  # {nodeid: {setup|call|teardown: outcome}}


def _final_outcome(phases: dict) -> str:
    if phases.get("setup") == "failed" or phases.get("teardown") == "failed":
        return "error"
    if "call" in phases:
        return phases["call"]
    if phases.get("setup") == "skipped":
        return "skipped"
    return "unknown"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    phases = _phase_outcomes.setdefault(item.nodeid, {})
    phases[report.when] = report.outcome

    # ── call 단계: 스크린샷 + outcome 기록 ───────────────────
    if report.when == "call":
        driver = None
        if hasattr(item, "instance") and item.instance is not None:
            driver = getattr(item.instance, "driver", None)

        if driver is not None and _OBS_AVAILABLE:
            try:
                obs_screenshot = _obs.capture_screenshot(item, driver, report.outcome)
                if obs_screenshot is not None:
                    _last_screenshot[item.nodeid] = obs_screenshot
            except Exception as exc:
                print(f"\n[conftest] obs screenshot failed: {exc}")

    # ── teardown 단계: 관측 프로세스 종료 ─────────────────────
    if report.when == "teardown" and _OBS_AVAILABLE:
        try:
            final_outcome = _final_outcome(_phase_outcomes.pop(item.nodeid, {}))
            shot_path: Optional[Path] = _last_screenshot.pop(item.nodeid, None)
            _obs.stop(item, final_outcome, shot_path)
        except Exception as e:
            print(f"\n[conftest] obs stop error: {e}")


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """관측: finished_at 기록."""
    if _OBS_AVAILABLE:
        try:
            _obs.session_finish(session.config)
        except Exception as e:
            print(f"\n[conftest] obs session_finish error: {e}")
