from __future__ import annotations

import _tc_connectors as conn
import _tc_library as lib
import _tc_source_watch as watch
import _tc_sources as src
from _tc_template import analyze_workbook
from _tc_xlsx_import import import_workbook
from tests.unit.tc_library.connector_fixtures import CLOUD, PAGE_ID, STORAGE_V15, setup_confluence

SUITE = "야핏무브"


def test_source_change_scan_flag_diff_and_ack(library_dir, template_xlsx, fake_web):
    profiles = analyze_workbook(template_xlsx)
    lib.save_template(SUITE, template_xlsx, profiles)
    lib.import_cases(SUITE, ["혜택"], import_workbook(template_xlsx, profiles, ["혜택"], {"혜택": "BEN"}), "t")
    setup_confluence(fake_web)
    conn.add_confluence(src.new_bundle(), f"{CLOUD}/wiki/spaces/MOVE/pages/{PAGE_ID}")
    lib.add_source_refs(SUITE, "BEN_0002", [f"conf:{PAGE_ID}@v14#§2"])

    assert watch.scan(SUITE)["changes"] == []
    setup_confluence(fake_web, version=15, storage=STORAGE_V15)
    result = watch.scan(SUITE)
    assert result["changes"] == [{"ref": f"conf:{PAGE_ID}@v14", "from": "v14", "to": "v15", "case_ids": ["BEN_0002"]}]
    assert [c["case_id"] for c in lib.filter_cases(lib.load_cases(SUITE), {"needs_review": "1"})] == ["BEN_0002"]
    assert watch.flagged(SUITE)[0]["case_ids"] == ["BEN_0002"]

    lines = watch.diff(f"conf:{PAGE_ID}@v14#§2")["lines"]
    assert {"op": "-", "text": "배너는 3초마다 자동으로 다음 배너로 이동한다."} in lines
    assert {"op": "+", "text": "배너는 5초마다 자동으로 다음 배너로 이동한다."} in lines

    case = watch.ack(SUITE, "BEN_0002")
    assert f"conf:{PAGE_ID}@v15#§2" in case["source_refs"] and "source_change" not in case["flags"]
    assert case["rev"] == 1
    assert lib.build_tree(lib.load_cases(SUITE))[0]["needs_review"] == 0
