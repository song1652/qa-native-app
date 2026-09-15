import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from locator_registry import find_unique_web_candidate, normalize_locator


def test_legacy_locator_defaults_to_auto_surface():
    locator = normalize_locator({"strategy": "ID", "value": "app:id/login"})
    assert locator["surface"] == "auto"


def test_webview_locator_is_preserved():
    locator = normalize_locator({
        "surface": "webview",
        "strategy": "ACCESSIBILITY_ID",
        "value": "login",
        "webview": {"strategy": "label", "value": "아이디"},
    })
    assert locator["webview"] == {"strategy": "label", "value": "아이디"}


def test_invalid_surface_is_rejected():
    with pytest.raises(ValueError, match="surface"):
        normalize_locator({"surface": "desktop", "strategy": "ID", "value": "x"})


def test_webview_healing_requires_a_unique_candidate():
    duplicate = '<input aria-label="아이디"><input aria-label="아이디">'
    assert find_unique_web_candidate({"value": "아이디"}, duplicate) == {}
    unique = '<input data-testid="username"><button aria-label="로그인"></button>'
    match = find_unique_web_candidate({"value": "username"}, unique)
    assert match["strategy"] == "test_id"
    assert match["value"] == "username"
