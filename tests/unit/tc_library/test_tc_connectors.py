from __future__ import annotations

import pytest

import _tc_connectors as conn
import _tc_credentials as creds
import _tc_generate as gen
import _tc_library as lib
import _tc_sources as src
from _tc_fetch import FetchError
from _tc_template import analyze_workbook
from _tc_xlsx_import import import_workbook
from tests.unit.tc_library.connector_fixtures import (
    CLOUD, FIGMA_KEY, FIGMA_URL, PAGE_ID, cloud_page, setup_confluence, setup_figma,
)
from tests.unit.tc_library.source_fixtures import make_pdf

SUITE = "야핏무브"


def test_public_url_html_pdf_and_text(library_dir, fake_web):
    fake_web.add("https://docs.example.com/prd", "<title>PRD</title><h1>배너</h1><p>3초마다 이동</p>",
                 headers={"Content-Type": "text/html; charset=utf-8"})
    fake_web.add("https://docs.example.com/spec.pdf", make_pdf(["Rotate every 3s"]),
                 headers={"Content-Type": "application/pdf"})
    fake_web.add("https://docs.example.com/a.bin", b"\x00", headers={"Content-Type": "application/octet-stream"})
    bundle = src.new_bundle()
    html = conn.add_url(bundle, "https://docs.example.com/prd")
    pdf = conn.add_url(bundle, "https://docs.example.com/spec.pdf")

    assert (html["kind"], html["title"], html["origin"]) == ("url", "PRD", "https://docs.example.com/prd")
    assert html["ref"].startswith("url:") and "# 배너" in src.read_text(bundle, html["source_id"])
    assert pdf["pages"] == 1
    with pytest.raises(FetchError) as exc:
        conn.add_url(bundle, "https://docs.example.com/a.bin")
    assert exc.value.code == "UNSUPPORTED_REMOTE_TYPE"
    with pytest.raises(FetchError):
        conn.add_url(bundle, "http://docs.example.com/prd")


def test_confluence_url_shapes():
    cfg = {"base_url": CLOUD}
    assert conn.parse_confluence_url(f"{CLOUD}/wiki/spaces/MOVE/pages/{PAGE_ID}/Title", cfg) == {"page_id": PAGE_ID}
    assert conn.parse_confluence_url(f"{CLOUD}/wiki/pages/viewpage.action?pageId=42", cfg) == {"page_id": "42"}
    assert conn.parse_confluence_url(f"{CLOUD}/wiki/x/AbC_1", cfg) == {"tiny": "AbC_1"}
    assert conn.parse_confluence_url(f"{CLOUD}/display/MOVE/8.6.0+Banner", cfg) == {"space": "MOVE", "title": "8.6.0 Banner"}
    for bad in ("https://evil.example.com/wiki/pages/1", f"{CLOUD}/wiki/spaces/MOVE/overview"):
        with pytest.raises(FetchError):
            conn.parse_confluence_url(bad, cfg)


def test_confluence_cloud_page_children_and_tiny_link(library_dir, fake_web):
    setup_confluence(fake_web)
    fake_web.add(f"{CLOUD}/wiki/api/v2/pages/{PAGE_ID}/children?limit=20", json={"results": [{"id": "7"}]})
    fake_web.add(f"{CLOUD}/wiki/api/v2/pages/7?body-format=storage",
                 json=cloud_page(3, "<p>하위 페이지 본문</p>", page_id="7", title="하위"))
    fake_web.add(f"{CLOUD}/wiki/x/AbC", status=302, headers={"Location": f"{CLOUD}/wiki/spaces/MOVE/pages/{PAGE_ID}/T"})
    fake_web.add(f"{CLOUD}/wiki/spaces/MOVE/pages/{PAGE_ID}/T", "<html></html>")
    bundle = src.new_bundle()

    entries = conn.add_confluence(bundle, f"{CLOUD}/wiki/spaces/MOVE/pages/{PAGE_ID}/x", children=True)
    assert [e["ref"] for e in entries] == [f"conf:{PAGE_ID}@v14", "conf:7@v3"]
    assert entries[0]["origin"] == f"{CLOUD}/wiki/pages/viewpage.action?pageId={PAGE_ID}"
    assert "## 배너 롤링 규칙" in src.read_text(bundle, entries[0]["source_id"])
    sent = dict(fake_web.calls)[f"{CLOUD}/wiki/api/v2/pages/{PAGE_ID}?body-format=storage"]
    assert sent["Authorization"].startswith("Basic ")

    other = src.new_bundle()
    assert conn.add_confluence(other, f"{CLOUD}/wiki/x/AbC")[0]["ref"] == f"conf:{PAGE_ID}@v14"


def test_confluence_dc_uses_rest_api_and_bearer(library_dir, fake_web):
    fake_web.private.add("wiki.corp.example")
    creds.save("confluence", {"base_url": "https://wiki.corp.example", "deployment": "dc", "token": "pat",
                              "allow_private": True})
    fake_web.add("https://wiki.corp.example/rest/api/content/9?expand=body.storage,version",
                 json=cloud_page(2, "<p>DC 본문</p>", page_id="9", title="DC"))
    entry = conn.add_confluence(src.new_bundle(), "https://wiki.corp.example/pages/viewpage.action?pageId=9")[0]
    assert entry["ref"] == "conf:9@v2"
    assert dict(fake_web.calls)["https://wiki.corp.example/rest/api/content/9?expand=body.storage,version"]["Authorization"] == "Bearer pat"


def test_figma_frame_outline_and_images(library_dir, fake_web):
    setup_figma(fake_web)
    bundle = src.new_bundle()
    entry = conn.add_figma(bundle, FIGMA_URL)

    assert entry["ref"] == f"figma:{FIGMA_KEY}/12:345@4410"
    assert entry["title"] == "야핏무브 8.6.0 / 혜택_상단배너"
    text = src.read_text(bundle, entry["source_id"])
    assert '- 화면 문구: "혜택을 준비하고 있어요"' in text
    assert "- 컴포넌트: Banner (State=Default)" in text and "- 이동: Banner 선택 → 20:1" in text
    assert entry["assets"] == ["01_혜택_상단배너.png"]
    assert src.asset_path(bundle, entry["assets"][0]).read_bytes().startswith(b"\x89PNG")
    assert dict(fake_web.calls)[f"https://api.figma.com/v1/images/{FIGMA_KEY}?ids=12%3A345&format=png&scale=1"]["X-Figma-Token"] == "figd_secret"
    with pytest.raises(FetchError):
        conn.parse_figma_url("https://www.figma.com/community/file/1")


def test_missing_credentials_are_reported(library_dir, fake_web):
    with pytest.raises(Exception) as exc:
        conn.add_figma(src.new_bundle(), FIGMA_URL)
    assert exc.value.code == "CREDENTIALS_MISSING"


def test_figma_text_becomes_verified_ui_text(library_dir, template_xlsx, fake_web, fake_claude):
    profiles = analyze_workbook(template_xlsx)
    lib.save_template(SUITE, template_xlsx, profiles)
    lib.import_cases(SUITE, ["혜택"], import_workbook(template_xlsx, profiles, ["혜택"], {"혜택": "BEN"}), "t")
    setup_figma(fake_web)
    bundle = src.new_bundle()
    conn.add_figma(bundle, FIGMA_URL)
    job = gen.create_job(SUITE, bundle_id=bundle, target={"sheet": "혜택", "path": ["혜택 탭", "상단 배너"]}, profile="기본")
    gen.run_job(job["job_id"])
    draft = lib.filter_cases(lib.load_cases(SUITE), {"job": job["job_id"]})[0]
    assert draft["source_refs"][0].startswith(f"figma:{FIGMA_KEY}/12:345@4410#§")
    assert all(b["verified"] for b in draft["bullets"])
