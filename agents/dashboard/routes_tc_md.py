"""TC 스튜디오 Markdown 내보내기 API."""
from __future__ import annotations

import re

from dash_http import _read_body

_SUITE = r"(?P<suite>[^/]+)"
_RUN = r"(?P<run_id>run_[A-Za-z0-9_-]+)"

MD_ROUTES: list[tuple[str, re.Pattern, str]] = [
    (m, re.compile(p + r"\Z"), h) for m, p, h in [
        ("GET", rf"/api/tc-library/{_SUITE}/export/md/eligibility", "_tcm_eligibility"),
        ("PUT", rf"/api/tc-library/{_SUITE}/md-groups", "_tcm_save_group"),
        ("POST", rf"/api/tc-library/{_SUITE}/export/md", "_tcm_preview"),
        ("POST", rf"/api/tc-library/{_SUITE}/md-exports/{_RUN}/commit", "_tcm_commit"),
        ("POST", rf"/api/tc-library/{_SUITE}/md-exports/{_RUN}/rollback", "_tcm_rollback"),
    ]
]


def _row_view(row: dict) -> dict:
    return {"tc_id": row["tc_id"], "case_id": row.get("case_id", ""), "status": row.get("status"),
            "reason": row.get("reason", ""), "reason_code": row.get("reason_code", ""),
            "file": row["file"], "platform": row["platform"], "excluded": row.get("excluded", False),
            "before": row.get("before"), "after": row.get("after")}


class TcMdRoutesMixin:
    def _tcm_eligibility(self, suite: str):
        from _tc_md_export import eligibility
        self._tcl_json({"ok": True, **eligibility(suite)})

    def _tcm_save_group(self, suite: str):
        from _tc_md_export import save_group
        body = _read_body(self)
        cfg = save_group(suite, list(body.get("path") or []), str(body.get("group", "")), str(body.get("code", "")))
        self._tcl_json({"ok": True, "groups": cfg["groups"]})

    def _tcm_preview(self, suite: str):
        from _tc_md_export import preview
        run = preview(suite)
        self._tcl_json({"ok": True, "run_id": run["run_id"], "summary": run["summary"],
                        "rows": [_row_view(r) for r in run["rows"]]})

    def _tcm_commit(self, suite: str, run_id: str):
        from _tc_md_export import commit
        body = _read_body(self)
        skip = [str(t) for t in body.get("skip", [])]
        self._tcl_json({"ok": True, **commit(suite, run_id, skip, body.get("policy") == "overwrite")})

    def _tcm_rollback(self, suite: str, run_id: str):
        from _tc_md_export import rollback
        self._tcl_json({"ok": True, **rollback(suite, run_id)})
