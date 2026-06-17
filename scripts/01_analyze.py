"""
01_analyze.py — Appium page_source 기반 앱 UI 수집.

screens.json에 정의된 각 화면에 접근해 UI XML을 수집하고
state/pipeline.json의 dom_info에 저장한다.

Usage:
    python scripts/01_analyze.py [--platform android|ios] \
        [--mode emulator|real_device|simulator]
    python scripts/01_analyze.py --screen login  # 특정 화면만
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent
CONFIG_DIR = ROOT / "config"
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "pipeline.json"

# drivers 패키지를 import할 수 있도록 scripts/ 디렉토리를 경로에 추가
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"step": "init", "dom_info": {}, "screens": {}}


def save_state(state: dict):
    STATE_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _resolve_value(test_data: dict, key_path: str) -> str:
    """dot-path 키로 test_data에서 값을 조회한다.

    예: "credentials.valid.username"
        → test_data["credentials"]["valid"]["username"]
    """
    value = test_data
    for part in key_path.split("."):
        value = value[part]
    if not value:
        raise ValueError(f"test_data key '{key_path}' is empty")
    return value


def _find_element(driver, target: str):
    """target 문자열에 따라 적절한 로케이터 전략으로 요소를 찾는다.

    resource-id 형식(콜론 포함, 예: com.example:id/btn)은 AppiumBy.ID,
    그 외 accessibility id 형식은 AppiumBy.ACCESSIBILITY_ID를 사용한다.
    """
    from appium.webdriver.common.appiumby import AppiumBy

    if ":" in target:
        return driver.find_element(AppiumBy.ID, target)
    return driver.find_element(AppiumBy.ACCESSIBILITY_ID, target)


def navigate_to_screen(driver, screen_cfg: dict, test_data: dict):
    """screens.json의 actions 시퀀스를 실행해 해당 화면으로 이동."""
    actions = screen_cfg.get("actions", [])

    for action in actions:
        action_type = action["type"]
        target = action["target"]

        if action_type == "tap":
            el = _find_element(driver, target)
            el.click()
        elif action_type == "input_text":
            if "value_key" not in action:
                raise ValueError(
                    f"input_text action은 'value_key' 필드가 필요합니다: {action}"
                )
            value = _resolve_value(test_data, action["value_key"])
            el = _find_element(driver, target)
            el.clear()
            el.send_keys(value)
        else:
            raise ValueError(f"unknown action type: {action_type}")


def collect_screen_xml(driver, screen_name: str, screen_cfg: dict,
                       test_data: dict) -> str:
    """화면 이동 후 page_source XML 반환."""
    import time

    navigate_to_screen(driver, screen_cfg, test_data)
    time.sleep(1)  # 화면 안정화 대기
    return driver.page_source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default="android",
                        choices=["android", "ios"])
    parser.add_argument("--mode", default="emulator",
                        choices=["emulator", "real_device", "simulator"])
    parser.add_argument("--screen", default=None, help="특정 화면만 수집")
    args = parser.parse_args()

    screens = json.loads((CONFIG_DIR / "screens.json").read_text())
    test_data = json.loads((CONFIG_DIR / "test_data.json").read_text())
    state = load_state()

    if args.platform == "android":
        from drivers.android_driver import create_driver
    else:
        from drivers.ios_driver import create_driver

    print(f"[01_analyze] platform={args.platform} mode={args.mode}")
    driver = create_driver(mode=args.mode)

    try:
        target_screens = (
            {args.screen: screens[args.screen]} if args.screen else screens
        )
        dom_info = state.get("dom_info", {})

        for screen_name, screen_cfg in target_screens.items():
            platforms = screen_cfg.get("platform", ["android", "ios"])
            if args.platform not in platforms:
                print(f"  skip {screen_name} (not in platforms: {platforms})")
                continue

            print(f"  collecting: {screen_name}")
            xml = collect_screen_xml(driver, screen_name, screen_cfg,
                                     test_data)
            dom_info[screen_name] = {
                "platform": args.platform,
                "xml": xml,
                "description": screen_cfg.get("description", ""),
            }

        state["dom_info"] = dom_info
        state["step"] = "analyzed"
        state["platform"] = args.platform
        save_state(state)
        print(f"[01_analyze] done. {len(dom_info)} screen(s) collected.")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
