"""routes_tc_connectors.py — TC 스튜디오 원격 소스·자격증명·출처 변경 API (PRD F1.3, F1.4, F5.9, §7).

라우트 표는 routes_tc_library.ROUTES 맨 앞에 붙는다.
자격증명 응답에는 토큰이 절대 들어가지 않는다 (_tc_credentials.status()).
"""
from __future__ import annotations

import re

from dash_http import _read_body

_SUITE = r"(?P<suite>[^/]+)"
_CASE = r"(?P<case_id>[\w-]+)"
_BUNDLE = r"(?P<bundle_id>src_[0-9a-f]{12})"

CONNECTOR_ROUTES: list[tuple[str, re.Pattern, str]] = [
    (m, re.compile(p + r"\Z"), h) for m, p, h in [
        ("GET", r"/api/tc-library/credentials", "_tcc_credentials"),
        ("PUT", r"/api/tc-library/credentials/(?P<kind>confluence|figma)", "_tcc_save_credentials"),
        ("POST", rf"/api/tc-library/sources/{_BUNDLE}/url", "_tcc_add_url"),
        ("POST", rf"/api/tc-library/sources/{_BUNDLE}/confluence", "_tcc_add_confluence"),
        ("POST", rf"/api/tc-library/sources/{_BUNDLE}/figma", "_tcc_add_figma"),
        ("GET", rf"/api/tc-library/sources/{_BUNDLE}/assets/(?P<name>[^/]+)", "_tcc_asset"),
        ("GET", r"/api/tc-library/source-diff", "_tcc_diff"),
        ("POST", rf"/api/tc-library/{_SUITE}/source-changes/scan", "_tcc_scan"),
        ("GET", rf"/api/tc-library/{_SUITE}/source-changes", "_tcc_flagged"),
        ("POST", rf"/api/tc-library/{_SUITE}/cases/{_CASE}/ack-source", "_tcc_ack"),
    ]
]


class TcConnectorRoutesMixin:
    """_tcl_dispatch가 부른다. 응답은 TcLibraryRoutesMixin의 _tcl_json을 쓴다."""

    def _tcc_credentials(self):
        from _tc_credentials import status
        self._tcl_json({"ok": True, **status()})

    def _tcc_save_credentials(self, kind: str):
        from _tc_credentials import save
        self._tcl_json({"ok": True, **save(kind, _read_body(self))})

    def _tcc_add_url(self, bundle_id: str):
        from _tc_connectors import add_url
        body = _read_body(self)
        self._tcl_json({"ok": True, "source": add_url(bundle_id, str(body.get("url", "")).strip())}, 201)

    def _tcc_add_confluence(self, bundle_id: str):
        from _tc_connectors import add_confluence
        body = _read_body(self)
        entries = add_confluence(bundle_id, str(body.get("url", "")).strip(), children=bool(body.get("children")))
        self._tcl_json({"ok": True, "sources": entries}, 201)

    def _tcc_add_figma(self, bundle_id: str):
        from _tc_connectors import add_figma
        body = _read_body(self)
        self._tcl_json({"ok": True, "source": add_figma(bundle_id, str(body.get("url", "")).strip())}, 201)

    def _tcc_asset(self, bundle_id: str, name: str):
        from urllib.parse import unquote
        from _tc_sources import asset_path
        content = asset_path(bundle_id, unquote(name)).read_bytes()
        self._serve_bytes(content, "image/png")

    def _tcc_diff(self):
        from _tc_source_watch import diff
        self._tcl_json({"ok": True, **diff(self._tcl_query.get("ref", ""))})

    def _tcc_scan(self, suite: str):
        from _tc_library import suite_dir
        from _tc_source_watch import scan
        suite_dir(suite)
        self._tcl_json({"ok": True, **scan(suite)})

    def _tcc_flagged(self, suite: str):
        from _tc_source_watch import flagged
        self._tcl_json({"ok": True, "changes": flagged(suite)})

    def _tcc_ack(self, suite: str, case_id: str):
        from _tc_library import with_issues
        from _tc_source_watch import ack
        self._tcl_json({"ok": True, "case": with_issues(ack(suite, case_id))})
