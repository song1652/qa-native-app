from __future__ import annotations

import pytest

import _tc_sources as src
from tests.unit.tc_library.source_fixtures import PRD_MD, make_docx, make_pdf


def test_markdown_file_is_stored_with_sections_and_version(library_dir):
    bundle = src.new_bundle()
    entry = src.add_file(bundle, "prd.md", PRD_MD.encode())

    assert entry["kind"] == "file" and entry["ref"].startswith("file:") and entry["sections"] == 3
    assert entry["version"] == entry["sha256"][:12]
    sections = src.split_sections(src.read_text(bundle, entry["source_id"]))
    assert [s["anchor"] for s in sections] == ["§1", "§2", "§3"]
    assert sections[1]["title"] == "배너 롤링 규칙"
    assert src.excerpt(bundle, entry["ref"] + "#§3")["markdown"].startswith("배너 선택 시")


def test_pdf_pages_become_sections_and_blank_pages_warn(library_dir):
    bundle = src.new_bundle()
    entry = src.add_file(bundle, "spec.pdf", make_pdf(["Banner rotates every 3 seconds.", ""]))

    assert entry["pages"] == 2
    assert entry["warnings"] == ["텍스트 없는 쪽 1개 (스캔 PDF OCR 미지원)"]
    assert "Banner rotates every 3 seconds." in src.read_text(bundle, entry["source_id"])


def test_docx_headings_and_tables_become_markdown(library_dir):
    bundle = src.new_bundle()
    entry = src.add_file(bundle, "spec.docx", make_docx())
    text = src.read_text(bundle, entry["source_id"])

    assert "# 배너 롤링 규칙" in text and "## 배너 선택 동작" in text
    assert "| 배너 1개 | 인디케이터 미노출 |" in text


def test_rejects_bad_type_magic_size_and_duplicates(library_dir, monkeypatch):
    bundle = src.new_bundle()
    for name, data, code in [("a.exe", b"MZ", "UNSUPPORTED_FILE"),
                             ("a.pdf", b"hello", "UNSUPPORTED_FILE"),
                             ("a.docx", b"PK\x03\x04junk", "UNSUPPORTED_FILE"),
                             ("a.txt", b"\xff\xfe\x00bad", "UNSUPPORTED_FILE")]:
        with pytest.raises(src.SourceError) as exc:
            src.add_file(bundle, name, data)
        assert exc.value.code == code, name
    monkeypatch.setattr(src, "MAX_DOCX_UNCOMPRESSED", 10)
    with pytest.raises(src.SourceError) as exc:
        src.add_file(bundle, "big.docx", make_docx())
    assert exc.value.code == "DOCX_TOO_LARGE"
    with pytest.raises(src.SourceError) as exc:
        src.add_paste(bundle, "가" * (src.MAX_PASTE_BYTES // 2))
    assert exc.value.status == 413
    src.add_paste(bundle, "배너는 3초마다 이동한다.")
    with pytest.raises(src.SourceError) as exc:
        src.add_paste(bundle, "배너는 3초마다 이동한다.")
    assert exc.value.code == "SOURCE_EXISTS"


def test_remove_source_and_invalid_bundle_id(library_dir):
    bundle = src.new_bundle()
    first = src.add_paste(bundle, "붙여넣은 기획")
    second = src.add_paste(bundle, "두 번째 기획")
    src.remove_source(bundle, first["source_id"])
    third = src.add_paste(bundle, "세 번째 기획")          # 지운 번호를 다시 쓰지 않는다
    assert [s["source_id"] for s in src.load_bundle(bundle)["sources"]] == [second["source_id"], "s03"]
    assert src.read_text(bundle, second["source_id"]) == "두 번째 기획"
    assert third["source_id"] == "s03"
    with pytest.raises(src.SourceError):
        src.load_bundle("../etc")


def test_removed_source_keeps_file_for_existing_drafts(library_dir):
    """목록에서 뺀 소스도 이미 만든 초안의 원문 발췌가 계속 동작한다 (파일을 지우면 근거가 사라진다)."""
    bundle = src.new_bundle()
    entry = src.add_file(bundle, "prd.md", PRD_MD.encode())
    src.remove_source(bundle, entry["source_id"])

    manifest = src.load_bundle(bundle)
    assert manifest["sources"] == []
    assert [r["source_id"] for r in manifest["removed"]] == [entry["source_id"]]
    assert src.excerpt(bundle, entry["ref"] + "#§3")["markdown"].startswith("배너 선택 시")
    assert src.find_source(entry["ref"])[0] == bundle
    with pytest.raises(src.SourceError) as exc:
        src.remove_source(bundle, entry["source_id"])
    assert exc.value.code == "SOURCE_NOT_FOUND"

    again = src.add_file(bundle, "prd.md", PRD_MD.encode())       # 같은 문서를 다시 넣을 수 있다
    manifest = src.load_bundle(bundle)
    assert [s["source_id"] for s in manifest["sources"]] == [again["source_id"]] != [entry["source_id"]]
    assert manifest["removed"] == []
