from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
for _p in (REPO_ROOT / "agents" / "dashboard", REPO_ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))



@pytest.fixture
def template_xlsx(tmp_path: Path) -> Path:
    from tests.unit.tc_library.tc_fixtures import build_template_workbook

    return build_template_workbook(tmp_path / "야핏무브_Full.xlsx")


@pytest.fixture
def library_dir(tmp_path: Path, monkeypatch) -> Path:
    import _paths

    target = tmp_path / "state" / "tc_library"
    monkeypatch.setattr(_paths, "TC_LIBRARY_DIR", target)
    return target


@pytest.fixture(scope="module")
def browser():
    """E2E용 Chromium (모듈마다 1개). HEADED=1이면 창을 띄운다."""
    import os

    from playwright.sync_api import expect, sync_playwright

    # 대시보드 전체 테스트와 함께 돌면 느려질 수 있어 기본 5초 대신 10초까지 기다린다
    expect.set_options(timeout=10_000)
    with sync_playwright() as playwright:
        b = playwright.chromium.launch(headless=os.environ.get("HEADED") != "1")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    """새 브라우저 컨텍스트의 페이지. 테스트가 끝날 때 처리되지 않은 JS 오류가 있으면 실패시킨다."""
    context = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    p = context.new_page()
    errors: list[str] = []
    p.on("pageerror", lambda exc: errors.append(str(exc)))
    yield p
    context.close()
    assert not errors, errors

@pytest.fixture
def fake_claude(tmp_path: Path, monkeypatch):
    """가짜 claude 실행 파일을 만들고 TCS_CLAUDE_BIN으로 가리킨다. 모드는 FAKE_CLAUDE_MODE로 바꾼다."""
    source = (Path(__file__).parent / "fake_claude.py").read_text(encoding="utf-8")
    exe = tmp_path / "bin" / "claude"
    exe.parent.mkdir()
    exe.write_text(f"#!{sys.executable}\n" + source.split("\n", 1)[1], encoding="utf-8")
    exe.chmod(0o755)
    args_file = tmp_path / "claude_args.json"
    monkeypatch.setenv("TCS_CLAUDE_BIN", str(exe))
    monkeypatch.setenv("FAKE_CLAUDE_ARGS", str(args_file))
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "ok")
    return args_file

@pytest.fixture
def fake_web(monkeypatch, tmp_path):
    """네트워크 없이 원격 응답을 흉내 낸다. web.add(url, body|json=…, status=, headers=)로 등록.
    url 끝이 '*'이면 접두 일치. web.private에 넣은 호스트는 사설 IP(10.0.0.5)로 풀린다."""
    import json as _json
    from types import SimpleNamespace

    import _paths
    import _tc_fetch

    web = SimpleNamespace(routes={}, calls=[], private=set())

    def add(url, body=b"", *, json=None, status=200, headers=None):
        if json is not None:
            body = _json.dumps(json, ensure_ascii=False).encode("utf-8")
            headers = {"content-type": "application/json", **(headers or {})}
        if isinstance(body, str):
            body = body.encode("utf-8")
        web.routes[url] = (status, {k.lower(): v for k, v in (headers or {}).items()}, body)

    def transport(url, headers, max_bytes):
        web.calls.append((url, dict(headers)))
        route = web.routes.get(url) or next(
            (v for k, v in web.routes.items() if k.endswith("*") and url.startswith(k[:-1])), None)
        if route is None:
            raise OSError(f"no fake route: {url}")
        status, hdrs, body = route
        return _tc_fetch.Response(status, hdrs, body[: max_bytes + 1], url)

    web.add = add
    monkeypatch.setattr(_tc_fetch, "transport", transport)
    monkeypatch.setattr(_tc_fetch, "resolver", lambda host: ["10.0.0.5"] if host in web.private else ["93.184.216.34"])
    for name in ("CONFLUENCE_BASE_URL", "CONFLUENCE_EMAIL", "CONFLUENCE_TOKEN", "FIGMA_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(_paths, "PROJECT_ROOT", tmp_path / "project_root")
    return web
