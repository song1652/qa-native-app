from unittest.mock import Mock
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from hybrid_runtime import HybridSession, SurfaceNotFound


class FakeDriver:
    contexts = ["NATIVE_APP"]

    def __init__(self, element=None):
        self.element = element

    def find_element(self, by, value):
        if self.element is None:
            raise LookupError(value)
        return self.element


def test_native_is_used_without_webview_or_playwright():
    element = Mock()
    resolved = HybridSession(FakeDriver(element)).find("id", "username", timeout=0)
    assert resolved.surface == "native"
    assert resolved.element is element


def test_missing_native_and_webview_fails_without_guessing():
    with pytest.raises(SurfaceNotFound, match="WebView도 없습니다"):
        HybridSession(FakeDriver()).find("id", "missing", timeout=0)


def test_explicit_webview_requires_detected_context():
    with pytest.raises(SurfaceNotFound, match="WebView도 없습니다"):
        HybridSession(FakeDriver()).find(
            "id", "username", surface="webview", webview={"strategy": "label", "value": "아이디"}
        )
