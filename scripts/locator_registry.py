"""공통 locator 레지스트리와 Inspector 스타일 XML 후보 탐색 유틸리티."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).parent.parent
REGISTRY_FILE = ROOT / "config" / "locators.json"

STRATEGIES = {"ID", "ACCESSIBILITY_ID", "XPATH", "ANDROID_UIAUTOMATOR",
              "IOS_PREDICATE", "IOS_CLASS_CHAIN"}
SURFACES = {"auto", "native", "webview"}
WEB_STRATEGIES = {"role", "label", "test_id", "placeholder", "text", "css"}


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
    surface = str(result.get("surface", "auto")).lower()
    if surface not in SURFACES:
        raise ValueError(f"지원하지 않는 locator surface: {surface}")
    webview = result.get("webview")
    if webview is not None:
        if not isinstance(webview, dict):
            raise ValueError("webview locator는 객체여야 합니다")
        web_strategy = str(webview.get("strategy", "css")).lower()
        if web_strategy not in WEB_STRATEGIES:
            raise ValueError(f"지원하지 않는 webview locator strategy: {web_strategy}")
        webview = dict(webview, strategy=web_strategy)
    result.update({"strategy": strategy, "value": value, "surface": surface})
    if webview is not None:
        result["webview"] = webview
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


class _HTMLCandidates(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        mappings = [
            ("data-testid", "test_id"), ("aria-label", "label"),
            ("placeholder", "placeholder"), ("id", "css"),
        ]
        for attr, strategy in mappings:
            value = values.get(attr, "").strip()
            if value:
                selector = f"#{value}" if attr == "id" else value
                self.items.append({"attr": attr, "strategy": strategy,
                                   "value": selector})
        role = values.get("role", "").strip()
        if role:
            self.items.append({"attr": "role", "strategy": "role",
                               "role": role, "value": role})


def find_unique_web_candidate(original: dict, html_text: str) -> dict:
    """WebView HTML에서 의미 기반 locator의 고유 후보만 반환한다."""
    parser = _HTMLCandidates()
    try:
        parser.feed(html_text)
    except Exception:
        return {}
    original_value = str(original.get("value", ""))
    ranked = [(_score(original_value, item["value"]), item)
              for item in parser.items]
    ranked = [item for item in ranked if item[0] >= 60]
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        return {}
    best_score = ranked[0][0]
    best = [item for score, item in ranked if score == best_score]
    if len(best) != 1:
        return {}
    return dict(best[0], confidence="high" if best_score == 100 else "medium")
