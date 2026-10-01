"""엑셀 TC 템플릿 분석 — 헤더 위치·컬럼·드롭다운·No. 수식 (PRD F2.1~F2.3, F2.6)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "source_tc_id": ("tc_id", "tc id", "scenario id", "test scenario id"),
    "tags": ("tags", "태그"),
    "no": ("no.", "no"),
    "l1": ("대분류", "main category"),
    "l2": ("중분류", "sub category"),
    "l3": ("소분류", "detail category"),
    "feature": ("기능", "tc summary", "tc summuery"),
    "precondition": ("사전 조건", "사전조건", "precondition"),
    "steps": ("test step", "test steps", "step", "steps", "테스트 절차"),
    "expected": ("expected result", "기대결과", "기대 결과"),
    "priority": ("우선순위",),
    "env": ("환경", "test result"),
    "note": ("기타", "비고"),
}
REQUIRED_COLUMNS = ("l1", "feature", "steps", "expected")


def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


@dataclass
class TemplateProfile:
    sheet: str
    header_row: int
    data_start_row: int
    columns: dict[str, int]                 # field → 1-based column
    result_columns: dict[str, int] = field(default_factory=dict)   # 플랫폼 → column
    validations: dict[str, list[str]] = field(default_factory=dict)  # field → 목록 값
    no_formula: str | None = None            # "=IF(H{r}<>\"\",ROW(B{r})-12, \"\")"
    style_row: int = 0
    warnings: list[str] = field(default_factory=list)
    excluded_columns: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TemplateProfile":
        return cls(**data)


def _match_field(value) -> str | None:
    text = _norm(value)
    for key, aliases in HEADER_ALIASES.items():
        if text in aliases:
            return key
    return None


def detect_header_row(ws, max_scan: int = 40) -> int | None:
    """필수 헤더 4개(대분류·기능·Test Step·Expected Result)가 모두 있는 첫 행.

    요약 표(구분/COUNT/Pass…)는 필수 헤더가 없어서 자연히 건너뛴다 (명세 피드백 #4).
    """
    for row in ws.iter_rows(min_row=1, max_row=max_scan):
        found = {_match_field(c.value) for c in row}
        if all(key in found for key in REQUIRED_COLUMNS):
            return row[0].row
    return None


def analyze_sheet(ws) -> TemplateProfile | None:
    from _tc_model import platform_key
    header_row = detect_header_row(ws)
    if header_row is None:
        return None
    columns: dict[str, int] = {}
    for cell in ws[header_row]:
        key = _match_field(cell.value)
        if key and key not in columns:
            columns[key] = cell.column

    result_columns: dict[str, int] = {}
    sub_row = header_row + 1
    if "env" in columns:
        col = columns["env"]
        while col <= ws.max_column:
            label = ws.cell(sub_row, col).value
            header_here = ws.cell(header_row, col).value
            if not label or (col != columns["env"] and header_here):
                break
            result_columns[str(label).strip()] = col
            col += 1
    for label in [k for k in result_columns if _norm(k) == "test level"]:
        columns.setdefault("priority", result_columns.pop(label))   # 결과 아래 칸의 Test Level = 우선순위
    if not result_columns:
        for cell in ws[header_row]:
            if platform_key(cell.value):
                result_columns[str(cell.value).strip()] = cell.column
    data_start = sub_row + 1 if "env" in columns and result_columns else sub_row

    validations: dict[str, list[str]] = {}
    col_to_field = {c: f for f, c in columns.items()}
    for platform_col in result_columns.values():
        col_to_field[platform_col] = "execution_result"
    for dv in ws.data_validations.dataValidation:
        if dv.type != "list" or not dv.formula1:
            continue
        first = min(r.min_col for r in dv.sqref.ranges)
        key = col_to_field.get(first)
        if key:
            validations[key] = [v.strip() for v in dv.formula1.strip('"').split(",")]

    no_formula = None
    if "no" in columns:
        value = ws.cell(data_start, columns["no"]).value
        if isinstance(value, str) and value.startswith("="):
            no_formula = re.sub(rf"(?<=[A-Z]){data_start}(?!\d)", "{r}", value)

    warnings = []
    if getattr(ws, "_images", None):
        warnings.append(f"이미지 {len(ws._images)}개는 다시 저장하면 사라질 수 있습니다")
    if getattr(ws, "_charts", None):
        warnings.append(f"차트 {len(ws._charts)}개는 다시 저장하면 사라질 수 있습니다")
    if "priority" in validations and validations["priority"] != ["P0", "P1", "P2", "P3"]:
        warnings.append("우선순위 드롭다운을 내보낼 때 P0~P3으로 넓힙니다")

    return TemplateProfile(
        sheet=ws.title, header_row=header_row, data_start_row=data_start,
        excluded_columns=[cell.column for cell in ws[header_row] if _norm(cell.value) == "auto"],
        columns=columns, result_columns=result_columns, validations=validations,
        no_formula=no_formula, style_row=data_start, warnings=warnings,
    )


def analyze_workbook(path: Path) -> dict[str, TemplateProfile]:
    import openpyxl

    wb = openpyxl.load_workbook(str(path))
    try:
        profiles = {}
        for ws in wb.worksheets:
            profile = analyze_sheet(ws)
            if profile:
                profiles[ws.title] = profile
        return profiles
    finally:
        wb.close()


def _letter(col: str) -> int:
    from openpyxl.utils import column_index_from_string

    return column_index_from_string(col.replace("열", "").strip().upper())


# Import Studio 매핑 프로필의 필드 → TC 스튜디오 필드
IMPORT_STUDIO_FIELDS = {"title": "feature", "steps": "steps", "expected": "expected",
                        "precondition": "precondition", "priority": "priority", "group": "l1",
                        "tc_id": "source_tc_id", "source_tc_id": "source_tc_id", "tags": "tags",
                        "l1": "l1", "l2": "l2", "l3": "l3"}


def mapping_from_import_profile(mappings: dict[str, str]) -> dict[str, str]:
    """Import Studio 프로필 {"title": "B열", …} → {"feature": "B", …} 원본 ID·태그도 보존한다."""
    return {IMPORT_STUDIO_FIELDS[k]: v.replace("열", "").strip().upper()
            for k, v in mappings.items() if k in IMPORT_STUDIO_FIELDS and v}


def profile_from_mapping(ws, mapping: dict) -> TemplateProfile:
    """다른 양식 직접 매핑 (Phase 2 G0). mapping: {"header_row": 1, "columns": {"feature": "B", …},
    "result_columns": {"And": "K"}}. 대분류 열이 없으면 시트 이름을 대분류로 쓴다."""
    columns = {field: _letter(col) for field, col in mapping.get("columns", {}).items() if col and field != "auto"}
    missing = [f for f in ("feature", "steps", "expected") if f not in columns]
    if missing:
        from _tc_library import LibraryError
        raise LibraryError(f"필수 열을 지정하세요: {', '.join(missing)}", "MAPPING_INCOMPLETE")
    header_row = int(mapping.get("header_row") or 1)
    result_columns = {name: _letter(col) for name, col in (mapping.get("result_columns") or {}).items()}
    return TemplateProfile(sheet=ws.title, header_row=header_row, data_start_row=header_row + 1,
                           columns=columns, result_columns=result_columns, validations={},
                           no_formula=None, style_row=header_row + 1,
                           excluded_columns=[cell.column for cell in ws[header_row] if _norm(cell.value) == "auto"],
                           warnings=["직접 매핑한 양식입니다. 병합·요약 수식 보정 없이 값만 씁니다"])


def analyze_with_mapping(path: Path, mapping: dict) -> dict[str, TemplateProfile]:
    import openpyxl

    wb = openpyxl.load_workbook(str(path))
    try:
        return {ws.title: profile_from_mapping(ws, mapping) for ws in wb.worksheets}
    finally:
        wb.close()
