"""
routes/api.py — 일반 GET 엔드포인트.

/api/state, /api/status, /api/reports, /api/generated, /api/testcase,
/api/screenshots, /api/tc-folders, /api/import/files, /api/import/sheets,
/api/check/mjpeg, /api/check/appium, /reports/{path}, /screenshots/{path}, /
"""
from __future__ import annotations

import sys
from html import escape as html_escape
from pathlib import Path

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

# shared 및 utils는 agents/dashboard/ 에 있으므로 부모 디렉토리를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import (  # noqa: E402
    HERE,
    GENERATED_DIR,
    IMPORT_DIR,
    PROJECT_ROOT,
    REPORTS_DIR,
    SCREENSHOTS_DIR,
    TESTCASES_DIR,
    _process_lock,
    _running,
)
from utils.state import (  # noqa: E402
    is_capture_active,
    list_generated,
    list_import_files,
    list_reports,
    list_screenshots,
    list_tc_folders,
    load_capture_session,
    read_state,
)
from utils.system import (  # noqa: E402
    check_android_devices,
    check_appium_status,
    check_ios_simulators,
)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index():
    # 개발 중 수정사항 즉시 반영을 위해 매 요청마다 파일 읽기
    html = (HERE / "dashboard.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/api/state")
async def get_state():
    return JSONResponse(read_state())


@router.get("/api/status")
async def get_status(platform: str | None = None):
    appium_ok = check_appium_status()
    state = read_state()
    resolved_platform = platform or state.get("platform", "android")
    if resolved_platform == "ios":
        devices = check_ios_simulators()
    else:
        devices = check_android_devices()
    with _process_lock:
        running_steps = [s for s, p in _running.items() if p.poll() is None]
    return JSONResponse({
        "appium": appium_ok,
        "devices": devices,
        "device_count": len(devices),
        "running_steps": running_steps,
        "platform": resolved_platform,
        "capture_active": is_capture_active(),
    })


@router.get("/api/reports")
async def get_reports():
    return JSONResponse(list_reports())


@router.get("/api/generated")
async def get_generated(platform: str | None = None):
    if platform is not None and platform not in ("android", "ios"):
        return JSONResponse({"ok": False, "error": "invalid platform"}, status_code=400)
    return JSONResponse(list_generated(platform))


@router.get("/api/testcase")
async def get_testcase(platform: str = "", file: str = ""):
    if platform not in ("android", "ios") or not file:
        return JSONResponse(
            {"ok": False, "error": "platform과 file이 필요합니다"}, status_code=400
        )
    from urllib.parse import unquote
    generated_file = unquote(file)
    generated_path = (GENERATED_DIR / platform / generated_file).resolve()
    generated_root = (GENERATED_DIR / platform).resolve()
    if (
        not generated_path.is_relative_to(generated_root)
        or generated_path.suffix != ".py"
        or generated_path.name.startswith(".")
        or not generated_path.is_file()
    ):
        return JSONResponse(
            {"ok": False, "error": "유효하지 않은 생성 테스트 파일입니다"}, status_code=400
        )
    testcase_path = (
        TESTCASES_DIR / platform / generated_path.relative_to(generated_root)
    ).with_suffix(".md").resolve()
    testcase_root = (TESTCASES_DIR / platform).resolve()
    if not testcase_path.is_relative_to(testcase_root) or not testcase_path.is_file():
        return JSONResponse(
            {"ok": False, "error": "대응하는 Markdown TC를 찾을 수 없습니다"}, status_code=404
        )
    return JSONResponse({
        "ok": True,
        "platform": platform,
        "file": str(testcase_path.relative_to(testcase_root)),
        "content": testcase_path.read_text(encoding="utf-8"),
    })


@router.get("/api/screenshots")
async def get_screenshots():
    return JSONResponse(list_screenshots())


@router.get("/api/tc-folders")
async def get_tc_folders(platform: str | None = None):
    if platform is not None and platform not in ("android", "ios"):
        return JSONResponse({"ok": False, "error": "invalid platform"}, status_code=400)
    return JSONResponse({"folders": list_tc_folders(platform)})


@router.get("/api/import/files")
async def get_import_files():
    return JSONResponse({"files": list_import_files()})


@router.get("/api/import/sheets")
async def get_import_sheets(file: str = ""):
    filename = file
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
        from import_excel import list_sheets
        return JSONResponse({"ok": True, "sheets": list_sheets(source)})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.get("/reports/{name:path}")
async def serve_report(name: str):
    if ".." in name:
        return Response(status_code=403)
    fpath = REPORTS_DIR / name
    if not fpath.is_file():
        fname = html_escape(name, quote=True)
        body = (
            "<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
            "<style>body{display:flex;align-items:center;justify-content:center;"
            "height:100vh;margin:0;font-family:Inter,-apple-system,sans-serif;"
            "background:#08071b;color:#b8b3d0}.box{text-align:center;padding:32px;"
            "border:1px solid rgba(140,120,220,.12);border-radius:16px;"
            "background:rgba(18,16,42,.55);backdrop-filter:blur(12px)}"
            ".icon{font-size:44px;margin-bottom:16px}.title{font-size:16px;"
            "font-weight:600;color:#f0eff5;margin-bottom:8px}.sub{font-size:12px;"
            "color:rgba(184,179,208,.5);font-family:monospace;word-break:break-all;"
            "max-width:320px}</style></head><body><div class='box'>"
            "<div class='icon'>🗑️</div><div class='title'>리포트가 삭제되었습니다</div>"
            f"<div class='sub'>{fname}</div></div></body></html>"
        )
        return HTMLResponse(content=body, status_code=404)
    return FileResponse(str(fpath), media_type="text/html")


@router.get("/screenshots/{name:path}")
async def serve_screenshot(name: str):
    if ".." in name:
        return Response(status_code=403)
    fpath = SCREENSHOTS_DIR / name
    if not fpath.is_file():
        return Response(status_code=404)
    ext = fpath.suffix.lower().lstrip(".")
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }.get(ext, "image/png")
    return FileResponse(str(fpath), media_type=mime)


@router.get("/api/check/mjpeg")
async def check_mjpeg(port: int = 8093):
    """MJPEG 스트리밍 서버 응답 여부 확인."""
    import urllib.request
    try:
        req = urllib.request.urlopen(f"http://localhost:{port}/", timeout=2)
        return JSONResponse({"ok": True, "port": port, "status": req.status})
    except Exception as exc:
        return JSONResponse({"ok": False, "port": port, "error": str(exc)})


@router.get("/api/check/appium")
async def check_appium():
    """Appium 서버 상태 확인."""
    ok = check_appium_status()
    session = load_capture_session()
    # 세션이 active 상태일 때만 session_id 반환
    active_sid = session.get("session_id", "") if (ok and session.get("active")) else ""
    return JSONResponse({
        "ok": ok,
        "capture_session_id": active_sid,
    })
