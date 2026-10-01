"""Confluence·Figma 녹화 응답 (공식 REST 응답 형태를 줄인 것)."""
from __future__ import annotations

CLOUD = "https://yafit.atlassian.net"
PAGE_ID = "48213377"
STORAGE_V14 = ('<h1>8.6.0 배너 개편</h1><h2>배너 롤링 규칙</h2><p>배너는 3초마다 자동으로 다음 배너로 이동한다.</p>'
               '<h2>배너 선택 동작</h2><p>배너 선택 시 설정된 링크로 이동한다.</p>')
STORAGE_V15 = STORAGE_V14.replace("3초마다", "5초마다")


def cloud_page(version: int = 14, storage: str = STORAGE_V14, page_id: str = PAGE_ID, title: str = "8.6.0 혜택 탭 상단 배너 개편"):
    return {"id": page_id, "title": title, "version": {"number": version}, "body": {"storage": {"value": storage}}}


def setup_confluence(web, *, version: int = 14, storage: str = STORAGE_V14):
    import _tc_credentials as creds
    creds.save("confluence", {"base_url": CLOUD, "email": "qa@yafit.com", "token": "secret-token"})
    web.add(f"{CLOUD}/wiki/api/v2/pages/{PAGE_ID}?body-format=storage", json=cloud_page(version, storage))
    web.add(f"{CLOUD}/wiki/api/v2/pages/{PAGE_ID}", json={"id": PAGE_ID, "version": {"number": version}})


FIGMA_KEY = "Qx7aR2abc"
FIGMA_NODE = {
    "name": "야핏무브 8.6.0", "version": "4410", "lastModified": "2026-09-20T00:00:00Z",
    "nodes": {"12:345": {"document": {
        "id": "12:345", "name": "혜택_상단배너", "type": "FRAME", "children": [
            {"id": "12:346", "name": "title", "type": "TEXT", "characters": "혜택"},
            {"id": "12:347", "name": "fallback", "type": "TEXT", "characters": "혜택을 준비하고 있어요"},
            {"id": "12:348", "name": "Banner", "type": "INSTANCE", "transitionNodeID": "20:1",
             "componentProperties": {"State#1": {"type": "VARIANT", "value": "Default"}}},
        ]}}},
}


def setup_figma(web, *, version: str = "4410"):
    import _tc_credentials as creds
    creds.save("figma", {"token": "figd_secret"})
    node = dict(FIGMA_NODE, version=version)
    web.add(f"https://api.figma.com/v1/files/{FIGMA_KEY}/nodes?ids=12%3A345&depth=6", json=node)
    web.add(f"https://api.figma.com/v1/images/{FIGMA_KEY}?ids=12%3A345&format=png&scale=1",
            json={"images": {"12:345": "https://figma-alpha-api.s3.us-west-2.amazonaws.com/images/abc"}})
    web.add("https://figma-alpha-api.s3.us-west-2.amazonaws.com/images/abc", b"\x89PNG\r\n\x1a\nfake")
    web.add(f"https://api.figma.com/v1/files/{FIGMA_KEY}?depth=1", json={"name": node["name"], "version": version})


FIGMA_URL = f"https://www.figma.com/design/{FIGMA_KEY}/Yafit?node-id=12-345&t=abc"
