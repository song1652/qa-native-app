"""
routes/import_studio.py — Import Studio 엔드포인트.

/api/import/convert, /api/import/preview, /api/import/upload
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import IMPORT_DIR, PROJECT_ROOT, TESTCASES_DIR  # noqa: E402

router = APIRouter()


@router.post("/api/import/convert")
async def post_import_convert(request: Request):
    body      = await request.json()
    filename  = str(body.get("file", "")).strip()
    sheet     = str(body.get("sheet", "")).strip()
    platforms = body.get("platforms", ["android", "ios"])
    mappings  = body.get("mappings", {})
    policy    = body.get("policy", "skip-conflict")

    if (
        not filename or not sheet or not isinstance(platforms, list)
        or not isinstance(mappings, dict)
        or any(not isinstance(v, str) for v in mappings.values())
        or policy not in ("skip-conflict", "overwrite")
    ):
        return JSONResponse(
            {"ok": False, "error": "file, sheet, platforms, mappings가 필요합니다"},
            status_code=400,
        )
    if filename != Path(filename).name or not filename.endswith(".xlsx"):
        return JSONResponse(
            {"ok": False, "error": "허용되지 않은 Excel 파일명입니다"}, status_code=400
        )
    source = (IMPORT_DIR / filename).resolve()
    if not source.is_file() or not source.is_relative_to(IMPORT_DIR.resolve()):
        return JSONResponse(
            {"ok": False, "error": "Excel 파일을 찾을 수 없습니다"}, status_code=404
        )
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from import_excel import convert_sheet
        created = convert_sheet(source, sheet, TESTCASES_DIR, platforms, mappings, policy)
        return JSONResponse({
            "ok": True,
            "count": len(created),
            "files": [str(p.relative_to(PROJECT_ROOT)) for p in created],
        })
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.post("/api/import/preview")
async def post_import_preview(request: Request):
    body      = await request.json()
    filename  = str(body.get("file", "")).strip()
    sheets    = body.get("sheets", [])
    platforms = body.get("platforms", ["android", "ios"])
    mappings  = body.get("mappings", {})

    if (
        not filename or not isinstance(sheets, list) or not sheets
        or any(not isinstance(s, str) for s in sheets)
        or not isinstance(platforms, list) or not isinstance(mappings, dict)
        or any(not isinstance(v, str) for v in mappings.values())
    ):
        return JSONResponse(
            {"ok": False, "error": "file, sheets, platforms, mappings가 필요합니다"},
            status_code=400,
        )
    if filename != Path(filename).name or not filename.endswith(".xlsx"):
        return JSONResponse(
            {"ok": False, "error": "허용되지 않은 Excel 파일명입니다"}, status_code=400
        )
    source = (IMPORT_DIR / filename).resolve()
    if not source.is_file() or not source.is_relative_to(IMPORT_DIR.resolve()):
        return JSONResponse(
            {"ok": False, "error": "Excel 파일을 찾을 수 없습니다"}, status_code=404
        )
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from import_excel import preview_sheets
        result = preview_sheets(source, sheets, TESTCASES_DIR, platforms, mappings)
        return JSONResponse({"ok": True, **result})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.post("/api/import/upload")
async def post_import_upload(request: Request):
    body     = await request.json()
    filename = str(body.get("name", "")).strip()
    encoded  = str(body.get("data", "")).strip()

    if filename != Path(filename).name or not filename.lower().endswith(".xlsx"):
        return JSONResponse(
            {"ok": False, "error": "xlsx 파일만 업로드할 수 있습니다"}, status_code=400
        )
    if not encoded or len(encoded) > 30 * 1024 * 1024:
        return JSONResponse(
            {"ok": False, "error": "파일 크기는 20MB 이하이어야 합니다"}, status_code=400
        )
    try:
        content = base64.b64decode(encoded, validate=True)
    except Exception:
        return JSONResponse(
            {"ok": False, "error": "파일 데이터가 올바르지 않습니다"}, status_code=400
        )
    if len(content) > 20 * 1024 * 1024:
        return JSONResponse(
            {"ok": False, "error": "파일 크기는 20MB 이하이어야 합니다"}, status_code=400
        )
    (IMPORT_DIR / filename).write_bytes(content)
    return JSONResponse({"ok": True, "file": filename, "size": len(content)})
