"""Runtime surface resolver for native and optional Playwright WebView steps."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By


class SurfaceNotFound(RuntimeError):
    pass


@dataclass
class ResolvedElement:
    surface: str
    element: object

    def click(self):
        return self.element.click()

    def clear(self):
        if self.surface == "webview":
            return self.element.fill("")
        return self.element.clear()

    def send_keys(self, value):
        if self.surface == "webview":
            return self.element.fill(value)
        return self.element.send_keys(value)

    def is_displayed(self) -> bool:
        return self.element.is_visible() if self.surface == "webview" else self.element.is_displayed()

    def get_attribute(self, name: str):
        if self.surface == "webview" and name == "value":
            return self.element.input_value()
        return self.element.get_attribute(name)


class HybridSession:
    """Prefer native Appium; inspect WebView only when one actually exists."""

    def __init__(self, driver, cdp_url: str | None = None):
        self.driver = driver
        self.cdp_url = cdp_url or os.getenv("PLAYWRIGHT_WEBVIEW_CDP_URL", "")
        self._playwright = self._browser = None
        self._adb_forward_port = None

    @property
    def webview_contexts(self) -> list[str]:
        return [str(context) for context in self.driver.contexts
                if str(context).upper().startswith("WEBVIEW")]

    def _web_page(self):
        if not self.webview_contexts:
            raise SurfaceNotFound("현재 화면에 WEBVIEW context가 없습니다")
        if not self.cdp_url:
            self._connect_android_webview_cdp()
        if not self.cdp_url:
            raise SurfaceNotFound("WebView는 감지됐지만 PLAYWRIGHT_WEBVIEW_CDP_URL이 없습니다")
        if self._browser is None:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.connect_over_cdp(
                self.cdp_url, no_defaults=True
            )
        pages = [page for context in self._browser.contexts for page in context.pages]
        if not pages:
            raise SurfaceNotFound("Playwright가 연결할 WebView page를 찾지 못했습니다")
        return pages[0]

    def _connect_android_webview_cdp(self) -> None:
        """현재 Android 앱의 WebView devtools socket을 로컬 포트로 연결한다."""
        package = getattr(self.driver, "current_package", "")
        adb = shutil.which("adb")
        if not package or not adb:
            return
        try:
            pid = subprocess.run(
                [adb, "shell", "pidof", package], capture_output=True,
                text=True, check=True, timeout=5,
            ).stdout.strip().split()[0]
            socket_name = f"webview_devtools_remote_{pid}"
            port = subprocess.run(
                [adb, "forward", "tcp:0", f"localabstract:{socket_name}"],
                capture_output=True, text=True, check=True, timeout=5,
            ).stdout.strip()
            if port.isdigit():
                self._adb_forward_port = port
                self.cdp_url = f"http://127.0.0.1:{port}"
        except (IndexError, OSError, subprocess.SubprocessError):
            return

    def _find_appium_webview(self, spec: dict, timeout: float):
        strategy, value = spec.get("strategy", "css"), spec.get("value", "")
        selectors = {
            "css": (By.CSS_SELECTOR, value),
            "test_id": (By.CSS_SELECTOR, f'[data-testid="{value}"]'),
            "label": (By.CSS_SELECTOR, f'[aria-label="{value}"]'),
            "placeholder": (By.CSS_SELECTOR, f'[placeholder="{value}"]'),
            "text": (By.XPATH, f'//*[normalize-space()="{value}"]'),
            "role": (By.CSS_SELECTOR, f'[role="{spec.get("role", value)}"]'),
        }
        by, selector = selectors.get(strategy, selectors["css"])
        self.driver.switch_to.context(self.webview_contexts[0])
        return WebDriverWait(self.driver, timeout).until(
            lambda driver: driver.find_element(by, selector)
        )

    @staticmethod
    def _web_locator(page, spec: dict):
        strategy, value = spec.get("strategy", "css"), spec.get("value", "")
        if strategy == "role":
            return page.get_by_role(spec.get("role", value), name=spec.get("name"))
        if strategy == "label": return page.get_by_label(value)
        if strategy == "test_id": return page.get_by_test_id(value)
        if strategy == "placeholder": return page.get_by_placeholder(value)
        if strategy == "text": return page.get_by_text(value, exact=True)
        return page.locator(value)

    def find(self, native_by, native_value: str, *, surface: str = "auto",
             webview: dict | None = None, timeout: float = 10) -> ResolvedElement:
        if surface not in {"auto", "native", "webview"}:
            raise ValueError(f"지원하지 않는 surface: {surface}")
        native_error = None
        if surface != "webview":
            try:
                if getattr(self.driver, "current_context", "NATIVE_APP") != "NATIVE_APP":
                    self.driver.switch_to.context("NATIVE_APP")
                element = WebDriverWait(self.driver, timeout).until(
                    lambda driver: driver.find_element(native_by, native_value)
                )
                return ResolvedElement("native", element)
            except Exception as exc:
                native_error = exc
                if surface == "native":
                    raise
        if not self.webview_contexts:
            raise SurfaceNotFound(f"native 요소를 찾지 못했고 WebView도 없습니다: {native_value}") from native_error
        web_spec = webview or {"strategy": "text", "value": native_value}
        try:
            locator = self._web_locator(self._web_page(), web_spec)
            locator.wait_for(state="visible", timeout=int(timeout * 1000))
            return ResolvedElement("webview", locator)
        except SurfaceNotFound:
            element = self._find_appium_webview(web_spec, timeout)
            return ResolvedElement("webview_appium", element)

    def capture_webviews(self) -> list[dict]:
        """감지된 WebView DOM을 수집한다. CDP가 없으면 Appium context로 수집한다."""
        contexts = self.webview_contexts
        if not contexts:
            return []
        try:
            page = self._web_page()
            return [{"context": contexts[0], "html": page.content(),
                     "url": page.url, "title": page.title(),
                     "source": "playwright_cdp"}]
        except Exception as cdp_error:
            cdp_message = str(cdp_error).splitlines()[0]
        original = getattr(self.driver, "current_context", "NATIVE_APP")
        snapshots = []
        try:
            for context in contexts:
                self.driver.switch_to.context(context)
                snapshots.append({"context": context,
                                  "html": self.driver.page_source,
                                  "source": "appium_webview_context"})
        except Exception as appium_error:
            snapshots.append({
                "context": contexts[0], "html": "", "source": "unavailable",
                "error": (
                    f"Playwright CDP: {cdp_message}; "
                    f"Appium context: {str(appium_error).splitlines()[0]}"
                ),
            })
        finally:
            try:
                self.driver.switch_to.context(original)
            except Exception:
                pass
        return snapshots

    def close(self):
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        if self._adb_forward_port:
            adb = shutil.which("adb")
            if adb:
                subprocess.run(
                    [adb, "forward", "--remove", f"tcp:{self._adb_forward_port}"],
                    capture_output=True, check=False,
                )
            self._adb_forward_port = None
        self._browser = self._playwright = None
