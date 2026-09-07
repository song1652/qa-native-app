"""Excel test-case importer for the Appium Markdown pipeline."""
from __future__ import annotations

import re
from pathlib import Path


def _slug(text: str, fallback: str = "unnamed") -> str:
    value = re.sub(r"[/\\:*?\"<>|.,()[\]{}]", "", str(text or "").strip())
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return (value or fallback)[:60]


def _cell(row, index: int) -> str:
    value = row[index] if index < len(row) else ""
    return str(value).strip() if value is not None else ""


def _column_index(value: str, default: int) -> int:
    """Convert an Excel label such as ``B열`` to a zero-based row index."""
    match = re.fullmatch(r"([A-Z])(?:열)?", str(value or "").strip().upper())
    return ord(match.group(1)) - ord("A") if match else default


def _mapped_cell(row, mappings: dict[str, str], field: str, default: int) -> str:
    return _cell(row, _column_index(mappings.get(field, ""), default))


def _header_row(ws) -> int:
    for row_number, row in enumerate(ws.iter_rows(min_row=1, max_row=20, values_only=True), 1):
        values = [str(value or "").lower() for value in row]
        if any("scenario id" in value or "test case" in value for value in values):
            return row_number
    return 1


def _effective_platforms(sheet_name: str, platforms: list[str]) -> list[str]:
    sheet_platform = sheet_name.strip().lower()
    if sheet_platform in {"android", "ios"}:
        return [sheet_platform] if sheet_platform in platforms else []
    return platforms


def _target_path(output_root: Path, platform: str, sheet_name: str,
                 tc_number: str, summary: str) -> Path:
    sheet_slug = _slug(sheet_name, "imported")
    output_dir = output_root / platform
    if sheet_slug != platform:
        output_dir /= sheet_slug
    return output_dir / f"tc_{tc_number}_{_slug(summary)}.md"


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


def list_sheets(path: Path) -> list[dict]:
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    result = []
    try:
        for name in workbook.sheetnames:
            worksheet = workbook[name]
            header = _header_row(worksheet)
            count = sum(
                1 for row in worksheet.iter_rows(min_row=header + 1, values_only=True)
                if _cell(row, 1) and ("_" in _cell(row, 1) or _cell(row, 1).isdigit())
            )
            if count:
                result.append({"name": name, "count": count})
    finally:
        workbook.close()
    return result


def preview_sheets(path: Path, sheet_names: list[str], output_root: Path,
                   platforms: list[str], mappings: dict[str, str] | None = None) -> dict:
    """Preview generated files and validation status without writing anything."""
    import openpyxl

    if not platforms or any(platform not in {"android", "ios"} for platform in platforms):
        raise ValueError("platforms must contain android and/or ios")
    if not sheet_names:
        raise ValueError("at least one sheet is required")
    mappings = mappings or {}
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = []
    seen_targets: set[Path] = set()
    try:
        for sheet_name in sheet_names:
            if sheet_name not in workbook.sheetnames:
                raise ValueError(f"시트 '{sheet_name}'가 없습니다")
            worksheet = workbook[sheet_name]
            header = _header_row(worksheet)
            effective_platforms = _effective_platforms(sheet_name, platforms)
            for source_row, row in enumerate(
                worksheet.iter_rows(min_row=header + 1, values_only=True), header + 1
            ):
                if not any(value is not None and str(value).strip() for value in row):
                    continue
                source_id = _mapped_cell(row, mappings, "tc_id", 1)
                title = _mapped_cell(row, mappings, "title", 5)
                precondition = _mapped_cell(row, mappings, "precondition", 6)
                steps = _mapped_cell(row, mappings, "steps", 7)
                expected = _mapped_cell(row, mappings, "expected", 8)
                priority_value = _mapped_cell(row, mappings, "priority", 9)
                missing = [name for name, value in (
                    ("tc_id", source_id), ("title", title),
                    ("steps", steps), ("expected", expected),
                ) if not value]
                if missing or ("_" not in source_id and not source_id.isdigit()):
                    rows.append({
                        "tc_id": source_id,
                        "title": title,
                        "precondition": precondition,
                        "steps": steps,
                        "expected": expected,
                        "group": sheet_name,
                        "sheet": sheet_name,
                        "source_row": source_row,
                        "platform": "",
                        "status": "error",
                        "reason": "필수값 누락: " + ", ".join(missing) if missing else "TC ID 형식 오류",
                    })
                    continue
                number_match = re.search(r"(\d+)", source_id)
                tc_number = number_match.group(1).zfill(3) if number_match else str(source_row - header).zfill(3)
                for platform in effective_platforms:
                    target = _target_path(output_root, platform, sheet_name, tc_number, title)
                    content = _render_markdown(
                        platform, tc_number, title, precondition, steps, expected, priority_value
                    )
                    if target in seen_targets:
                        status = "conflict"
                    elif not target.exists():
                        status = "added"
                    elif target.read_text(encoding="utf-8") == content:
                        status = "same"
                    else:
                        status = "updated"
                    seen_targets.add(target)
                    rows.append({
                        "tc_id": source_id,
                        "title": title,
                        "precondition": precondition,
                        "steps": steps,
                        "expected": expected,
                        "group": sheet_name,
                        "sheet": sheet_name,
                        "source_row": source_row,
                        "platform": platform,
                        "status": status,
                        "reason": "동일 생성 경로 중복" if status == "conflict" else "",
                    })
    finally:
        workbook.close()
    summary = {key: sum(row["status"] == key for row in rows)
               for key in ("added", "updated", "conflict", "error", "same")}
    return {"summary": summary, "rows": rows}


def convert_sheet(path: Path, sheet_name: str, output_root: Path,
                  platforms: list[str], mappings: dict[str, str] | None = None,
                  policy: str = "overwrite") -> list[Path]:
    """Convert one Excel sheet into app-compatible tc_*.md files."""
    import openpyxl

    if not platforms or any(platform not in {"android", "ios"} for platform in platforms):
        raise ValueError("platforms must contain android and/or ios")
    if policy not in {"skip-conflict", "overwrite"}:
        raise ValueError("policy must be skip-conflict or overwrite")
    mappings = mappings or {}
    effective_platforms = _effective_platforms(sheet_name, platforms)
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if sheet_name not in workbook.sheetnames:
        workbook.close()
        raise ValueError(f"시트 '{sheet_name}'가 없습니다")

    worksheet = workbook[sheet_name]
    header = _header_row(worksheet)
    created = []
    try:
        for number, row in enumerate(
            worksheet.iter_rows(min_row=header + 1, values_only=True), 1
        ):
            source_id = _mapped_cell(row, mappings, "tc_id", 1)
            if not source_id or ("_" not in source_id and not source_id.isdigit()):
                continue
            tc_number_match = re.search(r"(\d+)", source_id)
            tc_number = tc_number_match.group(1).zfill(3) if tc_number_match else str(number).zfill(3)
            main = _cell(row, 2)
            sub = _cell(row, 3)
            detail = _cell(row, 4)
            summary = _mapped_cell(row, mappings, "title", 5) or detail or sub or main or f"Imported TC {tc_number}"
            precondition = _mapped_cell(row, mappings, "precondition", 6)
            steps = _mapped_cell(row, mappings, "steps", 7)
            expected = _mapped_cell(row, mappings, "expected", 8)
            priority_value = _mapped_cell(row, mappings, "priority", 9)
            for platform in effective_platforms:
                content = _render_markdown(
                    platform, tc_number, summary, precondition, steps, expected, priority_value
                )
                target = _target_path(output_root, platform, sheet_name, tc_number, summary)
                target.parent.mkdir(parents=True, exist_ok=True)
                if policy == "skip-conflict" and target.exists():
                    continue
                target.write_text(content, encoding="utf-8")
                created.append(target)
    finally:
        workbook.close()
    return created
