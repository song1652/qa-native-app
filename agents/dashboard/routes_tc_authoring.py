"""routes_tc_authoring.py — TC 스튜디오 생성·검토 API (PRD F1.1~F1.2, F1.5~F1.6, F3, F4, F5.5~F5.7, F5.10).

라우트 표는 routes_tc_library.ROUTES 앞에 붙는다 (`/api/tc-library/{suite}`보다 먼저 맞아야 한다).
작업 진행은 SSE 대신 GET /api/tc-library/jobs/{id} 폴링(1.5초)으로 본다 (Phase 2 결정 Y3).
"""
from __future__ import annotations

import re
from pathlib import Path

from dash_http import _read_body, _read_raw_body
from routes_tc_import_admin import ADMIN_ROUTES, TcImportAdminRoutesMixin

_SUITE = r"(?P<suite>[^/]+)"
_CASE = r"(?P<case_id>[\w-]+)"
_BUNDLE = r"(?P<bundle_id>src_[0-9a-f]{12})"
_JOB = r"(?P<job_id>job_[0-9a-f]{12})"
MAX_SOURCE_BYTES = 25 * 1024 * 1024

AUTHORING_ROUTES: list[tuple[str, re.Pattern, str]] = [
    (m, re.compile(p + r"\Z"), h) for m, p, h in [
        ("GET", rf"/api/tc-library/{_SUITE}/authoring-context", "_tca_context"),
        ("GET", r"/api/tc-library/import/mapping-profiles", "_tca_mapping_profiles"),
        ("POST", r"/api/tc-library/sources", "_tca_new_bundle"),
        ("GET", rf"/api/tc-library/sources/{_BUNDLE}", "_tca_bundle"),
        ("POST", rf"/api/tc-library/sources/{_BUNDLE}/file", "_tca_add_file"),
        ("POST", rf"/api/tc-library/sources/{_BUNDLE}/paste", "_tca_add_paste"),
        ("DELETE", rf"/api/tc-library/sources/{_BUNDLE}/(?P<source_id>s\d\d)", "_tca_remove_source"),
        ("GET", rf"/api/tc-library/sources/{_BUNDLE}/excerpt", "_tca_excerpt"),
        ("GET", r"/api/tc-library/profiles", "_tca_profiles"),
        ("POST", r"/api/tc-library/profiles/style-from-xlsx", "_tca_style_from_xlsx"),
        ("PUT", r"/api/tc-library/profiles/(?P<name>[^/]+)", "_tca_save_profile"),
        ("GET", rf"/api/tc-library/jobs/{_JOB}", "_tca_job"),
        ("POST", rf"/api/tc-library/jobs/{_JOB}/cancel", "_tca_cancel_job"),
        ("POST", rf"/api/tc-library/{_SUITE}/jobs", "_tca_start_job"),
        ("GET", rf"/api/tc-library/{_SUITE}/coverage", "_tca_coverage"),
        ("POST", rf"/api/tc-library/{_SUITE}/cases/{_CASE}/resolve-duplicate", "_tca_resolve_duplicate"),
    ]
]


AUTHORING_ROUTES[:0] = ADMIN_ROUTES


class TcAuthoringRoutesMixin(TcImportAdminRoutesMixin):
    """_tcl_dispatch가 부른다. 응답 도우미는 TcLibraryRoutesMixin의 _tcl_json·_tcl_actor를 쓴다."""

    # ── 소스 묶음 ─────────────────────────────────────────────────
    def _tca_new_bundle(self):
        from _tc_sources import new_bundle
        self._tcl_json({"ok": True, "bundle_id": new_bundle()}, 201)

    def _tca_bundle(self, bundle_id: str):
        from _tc_sources import load_bundle
        self._tcl_json({"ok": True, **load_bundle(bundle_id)})

    def _tca_add_file(self, bundle_id: str):
        from _tc_sources import add_file
        filename = Path(self._tcl_query.get("filename", "")).name
        entry = add_file(bundle_id, filename, _read_raw_body(self, MAX_SOURCE_BYTES))
        self._tcl_json({"ok": True, "source": entry}, 201)

    def _tca_add_paste(self, bundle_id: str):
        from _tc_sources import add_paste
        body = _read_body(self)
        self._tcl_json({"ok": True, "source": add_paste(bundle_id, str(body.get("text", "")))}, 201)

    def _tca_remove_source(self, bundle_id: str, source_id: str):
        from _tc_sources import remove_source
        remove_source(bundle_id, source_id)
        self._tcl_json({"ok": True})

    def _tca_excerpt(self, bundle_id: str):
        from _tc_sources import excerpt
        self._tcl_json({"ok": True, **excerpt(bundle_id, self._tcl_query.get("ref", ""))})

    # ── 작성 프로필 ───────────────────────────────────────────────
    def _tca_profiles(self):
        from _tc_profiles import list_profiles
        self._tcl_json({"ok": True, "profiles": list_profiles()})

    def _tca_style_from_xlsx(self):
        """본문 = xlsx 원본 바이트. 기존 TC의 문체 → 프로필 초안 (저장하지 않는다. 화면에서 고쳐 저장)."""
        import tempfile
        from _tc_library import LibraryError
        from _tc_profiles import style_from_cases
        from _tc_template import analyze_workbook
        from _tc_xlsx_import import import_workbook
        from routes_tc_library import MAX_XLSX_BYTES
        data = _read_raw_body(self, MAX_XLSX_BYTES)
        if not data.startswith(b"PK"):
            raise LibraryError("xlsx 형식이 아닙니다", "UNSUPPORTED_FILE")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "style.xlsx"
            path.write_bytes(data)
            try:
                profiles = analyze_workbook(path)
                cases = import_workbook(path, profiles, list(profiles), {}) if profiles else []
            except Exception as exc:
                raise LibraryError(f"엑셀을 읽을 수 없습니다: {exc}", "UNREADABLE_XLSX") from exc
        if not profiles:
            raise LibraryError("기준 양식 헤더(대분류·기능·Step·Expected Result)를 찾지 못했습니다", "NO_SHEETS")
        self._tcl_json({"ok": True, **style_from_cases(cases)})

    def _tca_save_profile(self, name: str):
        from _tc_profiles import save_profile
        self._tcl_json({"ok": True, "profile": save_profile(name, _read_body(self))})

    def _tca_mapping_profiles(self):
        """Import Studio에 저장된 매핑 프로필을 TC 스튜디오 열 매핑으로 바꿔 돌려준다 (G0)."""
        self._tci_profiles()

    # ── 생성 작업 ─────────────────────────────────────────────────
    def _tca_start_job(self, suite: str):
        from _tc_generate import create_job, start_background
        from _tc_library import suite_dir
        suite_dir(suite)
        body = _read_body(self)
        target = {"sheet": str(body.get("sheet", "")), "path": list(body.get("path") or [])}
        if "platforms" in body:
            target["platforms"] = [p for p in body["platforms"] if p in ("android", "ios")]
        job = create_job(suite, bundle_id=str(body.get("bundle_id", "")), target=target,
                         profile=str(body.get("profile", "기본")), mode=str(body.get("mode", "new")),
                         case_id=str(body.get("case_id", "")), note=str(body.get("note", "")),
                         only_refs=[str(r) for r in body.get("only_refs") or []])
        start_background(job["job_id"])
        self._tcl_json({"ok": True, "job": job}, 202)

    def _tca_job(self, job_id: str):
        from _tc_generate import get_job, invalid_drafts, log_tail
        self._tcl_json({"ok": True, "job": get_job(job_id), "log": log_tail(job_id),
                        "invalid": invalid_drafts(job_id)})

    def _tca_context(self, suite: str):
        from _tc_generate import latest_job
        self._tcl_json({"ok": True, "job": latest_job(suite)})

    def _tca_cancel_job(self, job_id: str):
        from _tc_generate import cancel_job
        self._tcl_json({"ok": True, "job": cancel_job(job_id)})

    # ── 검토 ──────────────────────────────────────────────────────
    def _tca_coverage(self, suite: str):
        from _tc_profiles import get_profile
        from _tc_review import coverage_gaps
        q = self._tcl_query
        gaps = coverage_gaps(suite, q.get("sheet", ""), [p for p in q.get("path", "").split("/") if p],
                             get_profile(q.get("profile", "기본")))
        self._tcl_json({"ok": True, "features": gaps})

    def _tca_resolve_duplicate(self, suite: str, case_id: str):
        from _tc_review import resolve_duplicate
        body = _read_body(self)
        result = resolve_duplicate(suite, case_id, int(body["rev"]), str(body["action"]), self._tcl_actor(),
                                   str(body.get("target_case_id", "")), int(body.get("target_rev", 0)))
        self._tcl_json({"ok": True, **result})
