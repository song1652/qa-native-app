"""FastAPI entrypoint for the TC Studio HTTP contract.

The reference route handlers are called through a small request adapter so their
URL and response shapes stay compatible while the app uses FastAPI.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import Response, JSONResponse
from starlette.concurrency import run_in_threadpool

_ROOT = Path(__file__).resolve().parents[3]
for _path in (_ROOT / "scripts", _ROOT / "agents" / "dashboard"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from routes_tc_library import TcLibraryRoutesMixin  # noqa: E402
from routes_tc_authoring import TcAuthoringRoutesMixin  # noqa: E402
from routes_tc_connectors import TcConnectorRoutesMixin  # noqa: E402
from routes_tc_md import TcMdRoutesMixin  # noqa: E402

router = APIRouter()


class _Adapter(TcLibraryRoutesMixin, TcAuthoringRoutesMixin, TcConnectorRoutesMixin, TcMdRoutesMixin):
    def __init__(self, path: str, headers: dict[str, str], body: bytes):
        self.path = path
        self.headers = headers
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status = 200
        self.response_headers: dict[str, str] = {}
        self.content = b""

    def _serve_bytes(self, content: bytes, media_type: str, status: int = 200):
        self.status = status
        self.content = content
        self.response_headers["Content-Type"] = media_type

    def send_response(self, status: int):
        self.status = status

    def send_header(self, name: str, value: str):
        self.response_headers[name] = value

    def end_headers(self):
        pass


def _dispatch(path: str, headers: dict[str, str], body: bytes, method: str) -> Response:
    handler = _Adapter(path, headers, body)
    handler._tcl_dispatch(method)
    content = handler.wfile.getvalue() or handler.content
    return Response(content=content, status_code=handler.status, headers=handler.response_headers)


@router.api_route("/api/tc-library", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/api/tc-library/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def tc_library_api(request: Request, path: str = ""):
    origin = request.headers.get("origin")
    allowed_origins = {f"{request.url.scheme}://{request.url.netloc}"}
    if request.url.hostname in {"localhost", "127.0.0.1"}:
        port = request.url.port
        allowed_origins.update(f"{request.url.scheme}://{host}:{port}" for host in ("localhost", "127.0.0.1"))
    if origin and origin not in allowed_origins:
        return JSONResponse({"ok": False, "error": "origin not allowed", "code": "FORBIDDEN"}, status_code=403)
    length = request.headers.get("content-length", "0")
    try:
        if int(length) > 25 * 1024 * 1024:
            return JSONResponse({"ok": False, "error": "요청이 너무 큽니다", "code": "PAYLOAD_TOO_LARGE"}, status_code=413)
    except ValueError:
        return JSONResponse({"ok": False, "error": "invalid content length", "code": "INVALID_BODY"}, status_code=400)
    body = await request.body()
    if len(body) > 25 * 1024 * 1024:
        return JSONResponse({"ok": False, "error": "요청이 너무 큽니다", "code": "PAYLOAD_TOO_LARGE"}, status_code=413)
    headers = dict(request.headers)
    if actor := request.headers.get("x-tc-actor"):
        headers["X-TC-Actor"] = actor
    headers["Content-Length"] = str(len(body))
    path_text = request.url.path + ("?" + request.url.query if request.url.query else "")
    return await run_in_threadpool(_dispatch, path_text, headers, body, request.method)
