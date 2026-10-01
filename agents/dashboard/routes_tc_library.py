"""routes_tc_library.py — TC 스튜디오 라이브러리 API (PRD F2·F5·F6, 로드맵 B8~B10).

serve.py의 do_GET/do_POST/do_PATCH/do_DELETE가 맨 앞에서 `_tcl_dispatch`를 호출한다.
경로에 변수가 있어 GET_ROUTES/POST_ROUTES 딕셔너리 대신 정규식 표를 쓴다.
설계 원칙은 routes_import.py와 같다 (serve를 import하지 않음, 경로는 _paths.X).
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote

import _paths
from dash_http import BodyTooLarge, _read_body, _read_raw_body

_SUITE = r"(?P<suite>[^/]+)"
_CASE = r"(?P<case_id>[\w-]+)"
_ID = r"(?P<item_id>[\w-]+)"
MAX_XLSX_BYTES = 25 * 1024 * 1024

ROUTES: list[tuple[str, re.Pattern, str]] = [
    (m, re.compile(p + r"\Z"), h) for m, p, h in [
        ("GET", r"/api/tc-library", "_tcl_suites"),
        ("POST", r"/api/tc-library/import/preview", "_tcl_import_preview"),
        ("POST", r"/api/tc-library/import", "_tcl_import_commit"),
        ("POST", r"/api/tc-library/import/plan", "_tcl_import_plan"),
        ("GET", r"/api/tc-library/import/runs", "_tcl_import_runs"),
        ("GET", r"/api/tc-library/import/runs/(?P<run_id>libimp_[0-9a-f]{16})", "_tcl_import_run"),
        ("POST", r"/api/tc-library/import/runs/(?P<run_id>libimp_[0-9a-f]{16})/rollback", "_tcl_import_rollback"),
        ("GET", rf"/api/tc-library/exports/{_ID}/download", "_tcl_export_download"),
        ("GET", r"/api/tc-library/trash", "_tcl_trash_list"),
        ("POST", r"/api/tc-library/trash/(?P<trash_id>trash_[0-9a-f]{12})/restore", "_tcl_trash_restore"),
        ("DELETE", r"/api/tc-library/trash/(?P<trash_id>trash_[0-9a-f]{12})", "_tcl_trash_purge"),
        ("DELETE", rf"/api/tc-library/{_SUITE}", "_tcl_delete_suite"),

        ("GET", rf"/api/tc-library/{_SUITE}/tree", "_tcl_tree"),
        ("GET", rf"/api/tc-library/{_SUITE}", "_tcl_list"),
        ("POST", rf"/api/tc-library/{_SUITE}/cases", "_tcl_create"),
        ("POST", rf"/api/tc-library/{_SUITE}/bulk", "_tcl_bulk"),
        ("POST", rf"/api/tc-library/{_SUITE}/move", "_tcl_move"),
        ("POST", rf"/api/tc-library/{_SUITE}/sheets/rename", "_tcl_rename_sheet"),
        ("POST", rf"/api/tc-library/{_SUITE}/branches", "_tcl_add_branch"),
        ("POST", rf"/api/tc-library/{_SUITE}/sheets", "_tcl_add_sheet"),
        ("POST", rf"/api/tc-library/{_SUITE}/export/xlsx", "_tcl_export_xlsx"),


        ("GET", rf"/api/tc-library/{_SUITE}/cases/{_CASE}", "_tcl_get_case"),
        ("PATCH", rf"/api/tc-library/{_SUITE}/cases/{_CASE}", "_tcl_patch_case"),
        ("DELETE", rf"/api/tc-library/{_SUITE}/cases/{_CASE}", "_tcl_delete_case"),
        ("POST", rf"/api/tc-library/{_SUITE}/cases/{_CASE}/duplicate", "_tcl_duplicate"),
        ("POST", rf"/api/tc-library/{_SUITE}/cases/{_CASE}/restore", "_tcl_restore"),
        ("POST", rf"/api/tc-library/{_SUITE}/cases/{_CASE}/revert", "_tcl_revert"),

        ("GET", rf"/api/tc-library/{_SUITE}/cases/{_CASE}/history", "_tcl_history"),
    ]
]


# 생성·검토 라우트(Phase 2)가 앞에 와야 `/api/tc-library/{suite}` 패턴에 먼저 잡히지 않는다
from routes_tc_authoring import AUTHORING_ROUTES  # noqa: E402
from routes_tc_connectors import CONNECTOR_ROUTES  # noqa: E402  (Phase 3)
from routes_tc_md import MD_ROUTES  # noqa: E402  (Phase 4)

ROUTES[:0] = MD_ROUTES + CONNECTOR_ROUTES + AUTHORING_ROUTES


class TcLibraryRoutesMixin:
    """DashboardHandler(TcLibraryRoutesMixin, …, BaseHTTPRequestHandler) 형태로 쓴다."""

    # ── 공통 ──────────────────────────────────────────────────────
    def _tcl_dispatch(self, method: str) -> bool:
        path, _, query = self.path.partition("?")
        if not path.startswith("/api/tc-library"):
            return False
        for route_method, pattern, handler in ROUTES:
            match = pattern.match(path)
            if match and route_method == method:
                params = {k: unquote(v) for k, v in match.groupdict().items()}
                self._tcl_query = {k: v[-1] for k, v in parse_qs(query, keep_blank_values=True).items()}
                try:
                    getattr(self, handler)(**params)
                except BodyTooLarge:
                    self._tcl_json({"ok": False, "error": "요청이 너무 큽니다",
                                    "code": "PAYLOAD_TOO_LARGE"}, 413)
                except Exception as exc:  # LibraryError 계열은 상태 코드를 그대로
                    from _tc_library import LibraryError, RevConflict
                    if not isinstance(exc, LibraryError):
                        raise
                    body = {"ok": False, "error": str(exc), "code": exc.code}
                    if isinstance(exc, RevConflict):
                        body["server_case"] = exc.server_case
                    self._tcl_json(body, exc.status)
                return True
        self._tcl_json({"ok": False, "error": "not found", "code": "NOT_FOUND"}, 404)
        return True

    def _tcl_json(self, payload, status: int = 200) -> None:
        self._serve_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          "application/json; charset=utf-8", status=status)

    def _tcl_actor(self) -> str:
        return self.headers.get("X-TC-Actor", "web")[:40] or "web"

    # ── 조회 ──────────────────────────────────────────────────────
    def _tcl_suites(self):
        from _tc_library import list_suites
        self._tcl_json({"ok": True, "suites": list_suites()})

    def _tcl_tree(self, suite: str):
        from _tc_library import build_tree, load_cases, load_branches
        self._tcl_json({"ok": True, "tree": build_tree(load_cases(suite), load_branches(suite))})

    def _tcl_list(self, suite: str):
        from _tc_library import filter_cases, load_cases
        items = filter_cases(load_cases(suite), self._tcl_query)
        offset = int(self._tcl_query.get("offset", 0))
        limit = min(int(self._tcl_query.get("limit", 200)), 1000)
        self._tcl_json({"ok": True, "total": len(items), "items": items[offset:offset + limit]})

    def _tcl_get_case(self, suite: str, case_id: str):
        from _tc_library import get_case, with_issues
        self._tcl_json({"ok": True, "case": with_issues(get_case(suite, case_id))})

    def _tcl_history(self, suite: str, case_id: str):
        from _tc_library import history
        self._tcl_json({"ok": True, "history": history(suite, case_id)})

    # ── 가져오기 ──────────────────────────────────────────────────
    def _tcl_import_preview(self):
        """본문 = xlsx 원본 바이트 (로드맵 Z3). ?filename= 필수."""
        from _tc_template import analyze_with_mapping, analyze_workbook
        from _tc_library import LibraryError
        filename = Path(self._tcl_query.get("filename", "")).name
        if not filename.lower().endswith(".xlsx"):
            raise LibraryError(".xlsx 파일만 가져올 수 있습니다", "UNSUPPORTED_FILE")
        data = _read_raw_body(self, MAX_XLSX_BYTES)
        if not data.startswith(b"PK"):
            raise LibraryError("xlsx 형식이 아닙니다", "UNSUPPORTED_FILE")
        preview_id = "imp_" + secrets.token_hex(6)
        upload_dir = _paths.TC_LIBRARY_DIR / "_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        xlsx = upload_dir / f"{preview_id}.xlsx"
        xlsx.write_bytes(data)
        try:
            mapping = json.loads(self._tcl_query["mapping"]) if self._tcl_query.get("mapping") else None
            if mapping is not None and not isinstance(mapping, dict):
                raise LibraryError('매핑 설정이 올바르지 않습니다', 'INVALID_MAPPING')
            profiles = analyze_with_mapping(xlsx, mapping) if mapping else analyze_workbook(xlsx)
        except LibraryError:
            xlsx.unlink(missing_ok=True)
            raise
        except Exception as exc:
            xlsx.unlink(missing_ok=True)
            raise LibraryError(f"엑셀을 읽을 수 없습니다: {exc}", "UNREADABLE_XLSX") from exc
        (upload_dir / f"{preview_id}.json").write_text(
            json.dumps({"filename": filename, "mapping": mapping}, ensure_ascii=False), encoding="utf-8")
        from _tc_xlsx_import import import_workbook
        from collections import Counter
        counts = Counter(c["sheet"] for c in import_workbook(xlsx, profiles, list(profiles), {}))  # 워크북은 한 번만 연다
        sheets = []
        for name, profile in profiles.items():
            sheets.append({"name": name, "header_row": profile.header_row,
                           "data_start_row": profile.data_start_row, "cases": counts[name],
                           "result_columns": list(profile.result_columns),
                           "warnings": profile.warnings})
        self._tcl_json({"ok": True, "preview_id": preview_id, "filename": filename,
                        "sheets": sheets})

    def _tcl_import_body(self):
        from _tc_library import LibraryError
        try:
            body = _read_body(self)
            if not isinstance(body, dict):
                raise ValueError('JSON object required')
            return body
        except (ValueError, UnicodeDecodeError) as exc:
            raise LibraryError('올바른 JSON 본문이 필요합니다', 'INVALID_JSON') from exc

    def _tcl_import_plan(self):
        from _tc_import_ops import plan_import
        self._tcl_json({"ok": True, **plan_import(self._tcl_import_body())})

    def _tcl_import_commit(self):
        from _tc_import_ops import commit_import
        self._tcl_json({"ok": True, **commit_import(self._tcl_import_body(), self._tcl_actor())})

    def _tcl_import_runs(self):
        from _tc_import_ops import list_runs, public_run
        errors = []
        self._tcl_json({"ok": True, "runs": [public_run(run, summary_only=True) for run in list_runs(errors)], "errors": errors})

    def _tcl_import_run(self, run_id: str):
        from _tc_import_ops import get_run, public_run
        self._tcl_json({"ok": True, **public_run(get_run(run_id))})

    def _tcl_import_rollback(self, run_id: str):
        from _tc_import_ops import rollback_import
        self._tcl_json({"ok": True, **rollback_import(run_id, self._tcl_actor())})

    # ── 쓰기 ──────────────────────────────────────────────────────
    def _tcl_patch_case(self, suite: str, case_id: str):
        from _tc_library import patch_case, with_issues
        body = _read_body(self)
        rev = int(body.pop("rev"))
        case = patch_case(suite, case_id, rev, body, self._tcl_actor())
        self._tcl_json({"ok": True, "case": with_issues(case)})

    def _tcl_bulk(self, suite: str):
        from _tc_library import LibraryError, bulk_patch, delete_cases
        body = _read_body(self)
        items = [{"case_id": str(i["case_id"]), "rev": int(i["rev"])} for i in body.get("items", [])]
        op = body.get("op", "set")
        if op == "delete":
            result = delete_cases(suite, items, self._tcl_actor())
        elif op == "set":
            if body.get("field") == "platform_result":
                from _tc_library import bulk_set_result
                value = body["value"]
                result = bulk_set_result(suite, items, value["platform"], value["result"], self._tcl_actor())
            else:
                result = bulk_patch(suite, items, {body["field"]: body["value"]}, self._tcl_actor())
        else:
            raise LibraryError(f"지원하지 않는 작업입니다: {op}", "INVALID_OP")
        self._tcl_json({"ok": True, **result})

    def _tcl_move(self, suite: str):
        from _tc_library import bulk_patch
        body = _read_body(self)
        items = [{"case_id": str(i["case_id"]), "rev": int(i["rev"])} for i in body.get("items", [])]
        changes = {"sheet": body["sheet"], "path": (list(body["path"]) + ["", "", ""])[:3]}
        if body.get("feature"):
            changes["feature"] = body["feature"]
        result = bulk_patch(suite, items, changes, self._tcl_actor())
        self._tcl_json({"ok": True, "moved": result["updated"], "conflicts": result["conflicts"]})

    def _tcl_create(self, suite: str):
        from _tc_library import create_case, with_issues
        body = _read_body(self)
        after = body.pop("after", None)
        case = create_case(suite, body, self._tcl_actor(), after=after)
        self._tcl_json({"ok": True, "case": with_issues(case)}, 201)

    def _tcl_duplicate(self, suite: str, case_id: str):
        from _tc_library import duplicate_case, with_issues
        self._tcl_json({"ok": True, "case": with_issues(
            duplicate_case(suite, case_id, self._tcl_actor()))}, 201)

    def _tcl_delete_case(self, suite: str, case_id: str):
        from _tc_library import delete_cases
        rev = int(self._tcl_query.get("rev", -1))
        result = delete_cases(suite, [{"case_id": case_id, "rev": rev}], self._tcl_actor())
        if result["conflicts"]:
            self._tcl_json({"ok": False, "code": "REV_CONFLICT",
                            "server_case": result["conflicts"][0]}, 409)
            return
        self._tcl_json({"ok": True, "deleted": result["deleted"]})

    # ── 스위트 삭제·휴지통 ────────────────────────────────────────
    def _tcl_delete_suite(self, suite: str):
        """?confirm=스위트이름 — 화면이 보낸 이름과 경로의 이름이 같아야 지운다."""
        from _tc_trash import delete_suite
        self._tcl_json({"ok": True, "trash": delete_suite(suite, self._tcl_query.get("confirm", ""))})

    def _tcl_trash_list(self):
        from _tc_trash import RETENTION_DAYS, list_trash
        self._tcl_json({"ok": True, "items": list_trash(), "retention_days": RETENTION_DAYS})

    def _tcl_trash_restore(self, trash_id: str):
        from _tc_trash import restore_suite
        self._tcl_json({"ok": True, "restored": restore_suite(trash_id)})

    def _tcl_trash_purge(self, trash_id: str):
        from _tc_trash import purge
        self._tcl_json({"ok": True, "purged": purge(trash_id, self._tcl_query.get("confirm", ""))})

    def _tcl_restore(self, suite: str, case_id: str):
        from _tc_library import restore_case
        self._tcl_json({"ok": True, "case": restore_case(suite, case_id, self._tcl_actor())})

    def _tcl_revert(self, suite: str, case_id: str):
        from _tc_library import revert, with_issues
        body = _read_body(self)
        case = revert(suite, case_id, str(body["history_id"]), int(body["rev"]), self._tcl_actor())
        self._tcl_json({"ok": True, "case": with_issues(case)})

    # ── 내보내기 ──────────────────────────────────────────────────
    def _tcl_export_xlsx(self, suite: str):
        from _tc_library import LibraryError, is_imported, load_cases, load_profiles, suite_dir
        from _tc_xlsx_export import export_workbook, verify_export
        body = _read_body(self)
        profiles = load_profiles(suite)
        if not profiles:
            raise LibraryError("템플릿이 없습니다. 먼저 엑셀을 가져오세요", "NO_TEMPLATE", 409)
        cases = load_cases(suite)
        scope = body.get("scope", "all")
        drop: tuple[str, ...] = ()
        if scope == "approved":
            cases = [c for c in cases if c["status"] == "approved" and not is_imported(c)]   # 사람이 승인한 것만
        elif scope == "sheets":
            keep = set(body.get("sheets", []))
            cases = [c for c in cases if c["sheet"] in keep]
            drop = tuple(s for s in profiles if s not in keep)
        elif scope == "case_ids":
            keep = set(body.get("case_ids", []))
            cases = [c for c in cases if c["case_id"] in keep]
        by_sheet: dict[str, list[dict]] = {s: [] for s in profiles if s not in drop}
        for case in cases:
            if case["sheet"] in by_sheet:
                by_sheet[case["sheet"]].append(case)
        export_id = "exp_" + secrets.token_hex(6)
        out_dir = _paths.TC_LIBRARY_DIR / "_exports"
        out = out_dir / f"{export_id}.xlsx"
        export_workbook(suite_dir(suite) / "template.xlsx", profiles, by_sheet, out,
                        history_note=str(body.get("history_note", "")), drop_sheets=drop)
        checks = verify_export(out, {s: profiles[s] for s in by_sheet}, by_sheet)
        filename = f"{suite}_Full_{date.today():%Y%m%d}.xlsx"
        (out_dir / f"{export_id}.json").write_text(
            json.dumps({"suite": suite, "filename": filename}, ensure_ascii=False), encoding="utf-8")
        self._tcl_json({"ok": True, "export_id": export_id, "filename": filename,
                        "checks": checks, "count": sum(map(len, by_sheet.values()))})

    def _tcl_export_download(self, item_id: str):
        out_dir = _paths.TC_LIBRARY_DIR / "_exports"
        path, meta = out_dir / f"{item_id}.xlsx", out_dir / f"{item_id}.json"
        if not (re.fullmatch(r"exp_[0-9a-f]{12}", item_id) and path.exists() and meta.exists()):
            self._tcl_json({"ok": False, "code": "NOT_FOUND"}, 404)
            return
        filename = json.loads(meta.read_text(encoding="utf-8"))["filename"]
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition",
                         f"attachment; filename=\"export.xlsx\"; filename*=UTF-8''{quote(filename)}")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _tcl_rename_sheet(self, suite: str):
        from _tc_library import rename_sheet
        body = _read_body(self)
        rename_sheet(suite, body.get("sheet", ""), body.get("name", ""), self._tcl_actor())
        self._tcl_json({"ok": True})

    def _tcl_add_branch(self, suite: str):
        from _tc_library import add_branch
        body = _read_body(self)
        branch = add_branch(suite, body.get('sheet', ''), body.get('path', []))
        self._tcl_json({'ok': True, 'branch': branch})

    def _tcl_add_sheet(self, suite: str):
        from _tc_library import add_sheet
        body = _read_body(self)
        add_sheet(suite, body.get('name', ''))
        self._tcl_json({'ok': True})
