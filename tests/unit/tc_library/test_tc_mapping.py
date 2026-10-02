from __future__ import annotations

import openpyxl
import pytest

from _tc_library import LibraryError
from _tc_template import analyze_with_mapping
from _tc_xlsx_import import import_workbook


def _other_format(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "로그인"
    ws.append(["ID", "제목", "절차", "기대 결과", "우선"])
    ws.append(["L-1", "로그인 성공", "1. 아이디 입력\n2. 로그인 선택", "홈으로 이동한다.", "P0"])
    path = tmp_path / "other.xlsx"
    wb.save(path)
    return path


def test_custom_mapping_reads_other_format(tmp_path):
    path = _other_format(tmp_path)
    profiles = analyze_with_mapping(path, {"header_row": 1, "columns": {"feature": "B", "steps": "C", "expected": "D", "priority": "E"}})
    case = import_workbook(path, profiles, ["로그인"], {"로그인": "LOG"})[0]
    assert (case["case_id"], case["path"][0], case["feature"], case["steps"], case["priority"]) == \
        ("LOG_0001", "로그인", "로그인 성공", ["아이디 입력", "로그인 선택"], "P0")
    assert profiles["로그인"].warnings


def test_custom_mapping_requires_core_columns(tmp_path):
    with pytest.raises(LibraryError) as exc:
        analyze_with_mapping(_other_format(tmp_path), {"columns": {"feature": "B"}})
    assert exc.value.code == "MAPPING_INCOMPLETE"
