"""공통 locator 레지스트리와 Inspector 스타일 XML 후보 탐색 유틸리티."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent.parent
REGISTRY_FILE = ROOT / "config" / "locators.json"

STRATEGIES = {"ID", "ACCESSIBILITY_ID", "XPATH", "ANDROID_UIAUTOMATOR",
              "IOS_PREDICATE", "IOS_CLASS_CHAIN"}


def normalize_locator(raw: object) -> dict:
    """Markdown/레거시 문자열 또는 명시적 객체를 Appium locator로 정규화."""
    if isinstance(raw, dict):
        strategy = str(raw.get("strategy", "")).upper()
        value = str(raw.get("value", ""))
        result = dict(raw)
    else:
        value = str(raw or "").strip()
        strategy = ""
        if "=" in value:
            prefix, candidate = value.split("=", 1)
            aliases = {
                "accessibility_id": "ACCESSIBILITY_ID",
                "id": "ID",
                "xpath": "XPATH",
                "android_uiautomator": "ANDROID_UIAUTOMATOR",
                "ios_predicate": "IOS_PREDICATE",
                "ios_class_chain": "IOS_CLASS_CHAIN",
            }
            strategy = aliases.get(prefix.strip().lower(), "")
            if strategy:
                value = candidate.strip()
        result = {}

    if not strategy:
        if value.startswith("//") or value.startswith("/"):
            strategy = "XPATH"
        elif ":id/" in value or (":" in value and "/" in value):
            strategy = "ID"
        else:
            strategy = "ACCESSIBILITY_ID"
    if strategy not in STRATEGIES:
        raise ValueError(f"지원하지 않는 locator strategy: {strategy}")
    result.update({"strategy": strategy, "value": value})
    return result


def load_registry(path: Path = REGISTRY_FILE) -> dict:
    if not path.exists():
        return {"schema_version": 1, "targets": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("targets", {}), dict):
        raise ValueError(f"잘못된 locator registry 형식: {path}")
    return data


def save_registry(registry: dict, path: Path = REGISTRY_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def target_ref(tc_slug: str, selector_key: str) -> str:
    return f"{tc_slug}.{selector_key}"


def resolve_target(registry: dict, tc_slug: str, selector_key: str,
                   platform: str, fallback: object = "") -> dict:
    """TC별 키를 우선하고, 기존 공통 키를 다음으로 조회한다."""
    targets = registry.get("targets", {})
    entry = targets.get(target_ref(tc_slug, selector_key),
                        targets.get(selector_key, {}))
    if isinstance(entry, dict) and platform in entry:
        return normalize_locator(entry[platform])
    return normalize_locator(fallback)


_ATTR_MAP = {
    "resource-id": "ID", "content-desc": "ACCESSIBILITY_ID",
    "name": "ACCESSIBILITY_ID", "label": "ACCESSIBILITY_ID",
    "text": "XPATH", "value": "XPATH", "hint": "XPATH",
}


def collect_candidates(xml_text: str) -> list[dict]:
    """Appium Inspector가 보여주는 주요 native 속성을 후보로 추출."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    candidates = []
    for node in root.iter():
        attrs = {key: value.strip() for key, value in node.attrib.items()
                 if value and value.strip()}
        for attr, strategy in _ATTR_MAP.items():
            value = attrs.get(attr, "")
            if not value:
                continue
            candidates.append({"attr": attr, "strategy": strategy,
                               "value": value, "class": attrs.get("class", ""),
                               "resource_id": attrs.get("resource-id", "")})
    return candidates


def _score(original: str, candidate: str) -> int:
    original = original.lower().strip()
    candidate = candidate.lower().strip()
    if not original or not candidate:
        return 0
    if original == candidate:
        return 100
    if original in candidate or candidate in original:
        return 60
    tokens = {t for t in re.split(r"[^a-z0-9가-힣]+", original) if len(t) > 2}
    return 20 if tokens and any(t in candidate for t in tokens) else 0


def find_unique_candidate(original: dict, xml_text: str) -> dict:
    """고유하고 충분히 강한 후보만 반환한다. 애매하면 빈 dict."""
    original = normalize_locator(original)
    candidates = collect_candidates(xml_text)
    ranked = []
    for candidate in candidates:
        score = _score(original["value"], candidate["value"])
        if score:
            ranked.append((score, candidate))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < 60:
        return {}
    best_score = ranked[0][0]
    best_values = {(item[1]["strategy"], item[1]["value"])
                   for item in ranked if item[0] == best_score}
    if len(best_values) != 1:
        return {}
    best = dict(ranked[0][1])
    best["confidence"] = "high" if best_score >= 100 else "medium"
    return best
