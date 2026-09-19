"""Capture hierarchy locator validation domain tests."""

import pytest

from agents.dashboard.utils.capture_validation import (
    CaptureLocatorValidationError,
    validate_locator_xml,
)


ANDROID_XML = """<hierarchy>
  <node resource-id="wifi" text="Wi-Fi" bounds="[0,10][100,50]" />
  <node resource-id="duplicate" text="Same" bounds="[0,60][100,100]" />
  <node resource-id="duplicate" text="Same" bounds="[0,110][100,150]" />
</hierarchy>"""

IOS_XML = """<AppiumAUT>
  <XCUIElementTypeButton name="Settings" label="Settings" x="10" y="20" width="30" height="40" />
</AppiumAUT>"""


def test_android_locator_reports_unique_match_and_bounds():
    result = validate_locator_xml(ANDROID_XML, "android", "resource-id", "wifi")

    assert result == {
        "strategy": "resource-id",
        "value": "wifi",
        "match_count": 1,
        "unique": True,
        "confidence": "high",
        "matched_bounds": ["[0,10][100,50]"],
    }


def test_ios_accessibility_locator_converts_geometry_to_android_bounds_format():
    result = validate_locator_xml(IOS_XML, "ios", "accessibility-id", "Settings")

    assert result["matched_bounds"] == ["[10,20][40,60]"]
    assert result["unique"] is True


def test_xpath_and_duplicate_matches_have_medium_confidence():
    result = validate_locator_xml(ANDROID_XML, "android", "xpath", ".//*[@text='Same']")

    assert result["match_count"] == 2
    assert result["confidence"] == "medium"


def test_invalid_strategy_and_malformed_xml_raise_typed_errors():
    with pytest.raises(CaptureLocatorValidationError) as strategy_error:
        validate_locator_xml(ANDROID_XML, "android", "css", "node")
    assert strategy_error.value.status_code == 400
    assert strategy_error.value.message == "지원하지 않는 strategy: css"

    with pytest.raises(CaptureLocatorValidationError) as xml_error:
        validate_locator_xml("<broken>", "android", "text", "value")
    assert xml_error.value.status_code == 500
    assert xml_error.value.message.startswith("XML 파싱 오류:")
