"""TC Markdown 렌더러 — TC 스튜디오 Markdown 내보내기(_tc_md_export)가 쓰는 형식.

02_generate.parse_tc_blocks가 읽는 `## 테스트 케이스 N` 블록 형식을 이 모듈 한 곳에서만 만든다.
"""
from __future__ import annotations

import re


def _slug(text: str, fallback: str = "unnamed") -> str:
    value = re.sub(r"[/\\:*?\"<>|.,()[\]{}]", "", str(text or "").strip())
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return (value or fallback)[:60]


def _render_markdown(platform: str, tc_number: str, summary: str,
                     precondition: str, steps: str, expected: str,
                     priority_value: str) -> str:
    priority = "high" if priority_value in {"BAT", "Level 1", "high", "High"} else "medium"
    step_items = [line.strip() for line in steps.splitlines() if line.strip()]
    expected_items = [line.strip() for line in expected.splitlines() if line.strip()]
    step_lines = "\n".join(
        line if re.match(r"^\d+[.)]", line) else f"{index}. {line}"
        for index, line in enumerate(step_items or ["(스텝 미기재)"], 1)
    )
    expected_lines = "\n".join(
        f"- {line.lstrip('-* ').strip()}"
        for line in (expected_items or ["기대결과 미기재"])
    )
    platform_label = "Android" if platform == "android" else "iOS"
    function_name = f"test_{_slug(summary).lower()}"
    return (
        f"---\nid: tc_{tc_number}\npriority: {priority}\n"
        f"tags: [imported]\ntype: structured\n---\n"
        f"# TC-{tc_number}: {summary}\n\n## 목적\n{summary}\n\n"
        f"## 플랫폼\n- {platform_label}\n\n"
        f"## 전제조건\n- {precondition or '앱이 실행된 상태 (precondition: app_launch)'}\n\n"
        f"## 테스트 케이스 1\n\n"
        f"### 테스트 함수명\n`{function_name}`\n\n"
        f"### 단계\n{step_lines}\n\n"
        f"### 기대결과\n{expected_lines}\n"
    )
