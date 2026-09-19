"""Pure XML locator validation for Capture Studio."""

from __future__ import annotations

import xml.etree.ElementTree as ET


class CaptureLocatorValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _element_bounds(element: ET.Element) -> str:
    bounds = element.get("bounds", "")
    if bounds:
        return bounds
    x = element.get("x")
    y = element.get("y")
    width = element.get("width")
    height = element.get("height")
    if None in (x, y, width, height):
        return ""
    try:
        x1 = int(float(x))
        y1 = int(float(y))
        return f"[{x1},{y1}][{x1 + int(float(width))},{y1 + int(float(height))}]"
    except (TypeError, ValueError):
        return ""


def validate_locator_xml(
    xml_text: str,
    platform: str,
    strategy: str,
    value: str,
) -> dict:
    """Evaluate a locator against a hierarchy snapshot without Appium."""
    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:
        raise CaptureLocatorValidationError(f"XML 파싱 오류: {exc}", 500) from exc

    if platform == "ios":
        attributes = {
            "accessibility-id": "name",
            "accessibility id": "name",
            "name": "name",
            "label": "label",
            "value": "value",
            "text": "label",
        }
    else:
        attributes = {
            "resource-id": "resource-id",
            "accessibility-id": "content-desc",
            "accessibility id": "content-desc",
            "text": "text",
        }

    if strategy in attributes:
        attribute = attributes[strategy]
        matches = [element for element in root.iter() if element.get(attribute) == value]
    elif strategy == "xpath":
        try:
            matches = root.findall(value)
        except Exception as exc:
            raise CaptureLocatorValidationError(f"XPath 오류: {exc}", 400) from exc
    else:
        raise CaptureLocatorValidationError(f"지원하지 않는 strategy: {strategy}", 400)

    matched_bounds = []
    for element in matches:
        bounds = _element_bounds(element)
        if bounds:
            matched_bounds.append(bounds)
    count = len(matches)
    unique = count == 1
    return {
        "strategy": strategy,
        "value": value,
        "match_count": count,
        "unique": unique,
        "confidence": "high" if unique else ("medium" if count <= 3 else "low"),
        "matched_bounds": matched_bounds[:5],
    }
