"""pytest conftest — 실패 시 Appium driver screenshot 자동 캡처."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCREENSHOTS_JSON = ROOT / "state" / "screenshots.json"


def _screenshots_dir(nodeid: str) -> Path:
    # nodeid: tests/generated/{platform}/...
    parts = Path(nodeid.split("::")[0]).parts
    try:
        gen_idx = next(i for i, p in enumerate(parts) if p == "generated")
        platform = parts[gen_idx + 1] if len(parts) > gen_idx + 1 else "unknown"
    except StopIteration:
        platform = "unknown"
    d = ROOT / "reports" / "screenshots" / platform
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_screenshots() -> dict:
    if SCREENSHOTS_JSON.exists():
        try:
            return json.loads(SCREENSHOTS_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_screenshots(data: dict):
    SCREENSHOTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when != "call" or report.outcome != "failed":
        return

    # driver는 테스트 인스턴스의 self.driver 에서 가져온다
    driver = None
    if hasattr(item, "instance") and item.instance is not None:
        driver = getattr(item.instance, "driver", None)

    if driver is None:
        return

    screenshots_dir = _screenshots_dir(item.nodeid)

    safe_name = item.nodeid.replace("/", "_").replace("::", "__").replace(" ", "_")
    screenshot_path = screenshots_dir / f"{safe_name}.png"

    try:
        driver.save_screenshot(str(screenshot_path))
    except Exception as exc:
        print(f"\n[conftest] screenshot failed: {exc}")
        return

    # state/screenshots.json 에 nodeid → 상대경로 매핑 저장
    data = _load_screenshots()
    try:
        rel = str(screenshot_path.relative_to(ROOT / "reports"))
    except ValueError:
        rel = str(screenshot_path)
    data[item.nodeid] = rel
    _save_screenshots(data)
    print(f"\n[conftest] screenshot saved: {screenshot_path}")
