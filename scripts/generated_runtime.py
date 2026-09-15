"""Compatibility runtime for generated Appium tests.

Older generated artifacts import these helpers so device configuration and app
start-state behavior can evolve without rewriting the recorded test steps.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from selenium.webdriver.support.ui import WebDriverWait


CAPTURE_TEMPLATE_VERSION = 2
_NON_APPIUM_KEYS = frozenset({"default", "wifi_ip", "team_id", "label", "note"})


def select_device(path: Path, platform: str, mode: str) -> dict:
    """Return the default device from both legacy dict and current list schemas."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    section = data.get(platform, {}).get(mode)
    if isinstance(section, dict):
        return section
    if isinstance(section, list):
        return next((item for item in section if item.get("default")), section[0] if section else {})
    return {}


def appium_capabilities(device: dict) -> dict:
    """Remove dashboard-only metadata before handing capabilities to Appium."""
    return {key: value for key, value in device.items() if key not in _NON_APPIUM_KEYS}


def reset_to_start(driver, platform: str, app_id: str, app_activity: str = "") -> None:
    """Restore the app's native root state before every test and every retry."""
    try:
        if driver.current_context != "NATIVE_APP":
            driver.switch_to.context("NATIVE_APP")
    except Exception:
        pass

    if platform == "android":
        try:
            foreground = driver.current_package
            if foreground and foreground != app_id:
                driver.terminate_app(foreground)
        except Exception:
            pass

    try:
        driver.terminate_app(app_id)
    except Exception:
        pass
    time.sleep(0.3)
    driver.activate_app(app_id)

    if platform == "android" and app_activity:
        try:
            driver.execute_script(
                "mobile: startActivity",
                {"intent": f"{app_id}/{app_activity}", "wait": True, "stop": True},
            )
        except Exception:
            driver.activate_app(app_id)
    time.sleep(1.0)


def find_with_wait(driver, by, value, timeout: float = 15):
    """Wait for a generated locator instead of racing the app transition."""
    return WebDriverWait(driver, timeout).until(lambda current: current.find_element(by, value))
