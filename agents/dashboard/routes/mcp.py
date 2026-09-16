"""
routes/mcp.py — MCP (Model Context Protocol) HTTP+SSE 서버 (JSON-RPC 2.0).

엔드포인트:
  POST /mcp          — JSON-RPC 요청 처리 (initialize, tools/list, tools/call, ...)
  GET  /mcp/sse      — SSE 스트림 (endpoint 이벤트 전송)
  GET  /mcp/status   — MCP 연결 상태 확인
"""
from __future__ import annotations

import asyncio
import json
import sys
import time as _time
import urllib.request
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import JSONResponse, StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared import PORT, get_capture_driver  # noqa: E402
from utils.state import load_capture_session, save_capture_session  # noqa: E402
from ws import broadcast_timeline_sync  # noqa: E402

router = APIRouter(tags=["mcp"])

# ── MCP 전역 상태 ──────────────────────────────────────────────
_mcp_connected: bool = False
_mcp_client_id: str | None = None

# ── 프로토콜 버전 ──────────────────────────────────────────────
_MCP_PROTOCOL_VERSION = "2024-11-05"
_SERVER_INFO = {"name": "qa-capture-studio", "version": "1.0.0"}

# ── 9개 도구 정의 ──────────────────────────────────────────────
TOOLS: list[dict] = [
    {
        "name": "device_tap",
        "description": "화면의 특정 좌표를 탭합니다",
        "inputSchema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "디바이스 X 좌표"},
                "y": {"type": "integer", "description": "디바이스 Y 좌표"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "screenshot",
        "description": "현재 화면 스크린샷을 base64로 반환합니다",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "hierarchy",
        "description": "현재 화면의 UI 요소 계층 구조(XML)를 반환합니다",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "scroll",
        "description": "화면을 스크롤합니다",
        "inputSchema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "left", "right"],
                },
                "start_x": {"type": "integer"},
                "start_y": {"type": "integer"},
                "end_x":   {"type": "integer"},
                "end_y":   {"type": "integer"},
            },
        },
    },
    {
        "name": "input_text",
        "description": "텍스트를 입력합니다",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "입력할 텍스트"},
                "mask": {
                    "type": "boolean",
                    "description": "Livetail에 마스킹 여부",
                    "default": False,
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "back",
        "description": "뒤로가기 동작을 수행합니다",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "screen_info",
        "description": "현재 세션의 플랫폼, 디바이스, 화면 크기 정보를 반환합니다",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "generate_test_case",
        "description": "현재까지 기록된 액션으로 pytest 파일을 생성합니다",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tc_id":    {"type": "string"},
                "title":    {"type": "string"},
                "tc_group": {"type": "string"},
                "expected": {"type": "string", "description": "기대결과 텍스트. 화면에 표시돼야 할 문자열로 assertion이 자동 생성됩니다"},
            },
            "required": ["tc_id", "title"],
        },
    },
    {
        "name": "clear_actions",
        "description": "타임라인 액션 배열을 초기화합니다. 새 TC 시나리오 시작 전에 호출하세요",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# ── 헬퍼 ──────────────────────────────────────────────────────

def _jsonrpc_ok(result: object, req_id) -> dict:
    return {"jsonrpc": "2.0", "result": result, "id": req_id}


def _jsonrpc_err(code: int, message: str, req_id=None) -> dict:
    return {"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": req_id}


def _mcp_session_check() -> tuple[bool, dict | None, str]:
    """활성 capture 세션과 드라이버 확인. (ok, session, error_msg)"""
    session = load_capture_session()
    if not session.get("active"):
        return False, None, "No active capture session"
    driver = get_capture_driver()
    if driver is None:
        return False, session, "Appium driver is not connected"
    return True, session, ""


def _append_mcp_action(session: dict, action: dict) -> None:
    """MCP 액션을 세션에 기록하고 저장."""
    actions = list(session.get("actions", []))
    actions.append(action)
    save_capture_session({
        **session,
        "actions": actions,
        "last_activity_at": datetime.now().isoformat(),
    })


def _sync_post_local(path: str, payload: dict) -> dict:
    """로컬 서버에 동기 HTTP POST (urllib stdlib)."""
    url = f"http://127.0.0.1:{PORT}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


# ── 도구 실행 (동기, executor에서 호출) ───────────────────────

def _exec_device_tap(args: dict, session: dict) -> dict:
    driver = get_capture_driver()
    x = int(args["x"])
    y = int(args["y"])
    t0 = _time.monotonic()
    driver.tap([(x, y)])
    ms = int((_time.monotonic() - t0) * 1000)
    action = {
        "index":     len(session.get("actions", [])) + 1,
        "action":    "tap",
        "type":      "tap",
        "device_x":  x,
        "device_y":  y,
        "source":    "mcp",
        "timestamp": datetime.now().isoformat(),
    }
    _append_mcp_action(session, action)
    broadcast_timeline_sync({
        "type": "tap", "source": "mcp",
        "platform": session.get("platform", ""),
        "summary": f"({x},{y})", "ok": True, "duration_ms": ms,
    })
    return {"ok": True, "x": x, "y": y, "duration_ms": ms}


def _exec_screenshot(args: dict, session: dict) -> dict:
    driver = get_capture_driver()
    data = driver.get_screenshot_as_base64()
    broadcast_timeline_sync({
        "type": "screenshot", "source": "mcp",
        "platform": session.get("platform", ""), "summary": "", "ok": True,
    })
    return {"image": data, "format": "png"}


def _exec_hierarchy(args: dict, session: dict) -> dict:
    driver = get_capture_driver()
    xml = driver.page_source
    broadcast_timeline_sync({
        "type": "hierarchy", "source": "mcp",
        "platform": session.get("platform", ""), "summary": "", "ok": True,
    })
    return {"xml": xml}


def _exec_scroll(args: dict, session: dict) -> dict:
    driver = get_capture_driver()
    start_x = args.get("start_x")
    start_y = args.get("start_y")
    end_x   = args.get("end_x")
    end_y   = args.get("end_y")
    direction = args.get("direction", "down")

    if start_x is not None and end_x is not None:
        driver.swipe(int(start_x), int(start_y), int(end_x), int(end_y), duration=300)
        action_type = "scroll_down" if (end_y or 0) < (start_y or 0) else "scroll_up"
    else:
        sz = driver.get_window_size()
        w, h = sz["width"], sz["height"]
        if direction == "up":
            driver.swipe(w // 2, int(h * 0.3), w // 2, int(h * 0.7), 600)
            action_type = "scroll_up"
        elif direction == "left":
            driver.swipe(int(w * 0.8), h // 2, int(w * 0.2), h // 2, 400)
            action_type = "scroll_left"
        elif direction == "right":
            driver.swipe(int(w * 0.2), h // 2, int(w * 0.8), h // 2, 400)
            action_type = "scroll_right"
        else:
            driver.swipe(w // 2, int(h * 0.7), w // 2, int(h * 0.3), 600)
            action_type = "scroll_down"

    action = {
        "index":     len(session.get("actions", [])) + 1,
        "action":    action_type,
        "type":      action_type,
        "source":    "mcp",
        "timestamp": datetime.now().isoformat(),
    }
    _append_mcp_action(session, action)
    broadcast_timeline_sync({
        "type": action_type, "source": "mcp",
        "platform": session.get("platform", ""),
        "summary": direction, "ok": True,
    })
    return {"ok": True, "direction": direction}


def _exec_input_text(args: dict, session: dict) -> dict:
    driver = get_capture_driver()
    text = str(args["text"])
    mask = bool(args.get("mask", False))
    platform = session.get("platform", "android")
    if platform == "ios":
        driver.execute_script("mobile: type", {"text": text})
    else:
        driver.switch_to.active_element.send_keys(text)

    display_val = "***" if mask else text
    action = {
        "index":       len(session.get("actions", [])) + 1,
        "action":      "input",
        "type":        "input",
        "input_value": display_val,
        "source":      "mcp",
        "timestamp":   datetime.now().isoformat(),
    }
    _append_mcp_action(session, action)
    broadcast_timeline_sync({
        "type": "input", "source": "mcp",
        "platform": session.get("platform", ""),
        "summary": display_val, "ok": True,
    })
    return {"ok": True}


def _exec_back(args: dict, session: dict) -> dict:
    driver = get_capture_driver()
    platform = session.get("platform", "android")
    if platform == "ios":
        try:
            driver.execute_script("mobile: pressButton", {"name": "back"})
        except Exception:
            driver.back()
    else:
        driver.press_keycode(4)

    action = {
        "index":     len(session.get("actions", [])) + 1,
        "action":    "back",
        "type":      "back",
        "source":    "mcp",
        "timestamp": datetime.now().isoformat(),
    }
    _append_mcp_action(session, action)
    broadcast_timeline_sync({
        "type": "back", "source": "mcp",
        "platform": session.get("platform", ""),
        "summary": "back", "ok": True,
    })
    return {"ok": True}


def _exec_screen_info(args: dict, session: dict) -> dict:
    driver = get_capture_driver()
    try:
        sz = driver.get_window_size() if driver else {}
        device_width  = sz.get("width",  session.get("device_width",  1080))
        device_height = sz.get("height", session.get("device_height", 1920))
    except Exception:
        device_width  = session.get("device_width",  1080)
        device_height = session.get("device_height", 1920)

    return {
        "platform":      session.get("platform", ""),
        "device_name":   session.get("device_name", ""),
        "device_width":  device_width,
        "device_height": device_height,
        "session_id":    session.get("session_id", ""),
        "tc_group":      session.get("tc_group", ""),
    }


def _exec_generate_test_case(args: dict, session: dict) -> dict:
    tc_id    = str(args["tc_id"]).strip()
    title    = str(args["title"]).strip()
    tc_group = str(args.get("tc_group") or session.get("tc_group") or "default").strip()
    expected = str(args.get("expected", "")).strip()
    platform = session.get("platform", "android")
    actions  = session.get("actions", [])
    _NON_EXEC = frozenset({"screenshot", "hierarchy", "generate_test_case", "clear_actions", "screen_info"})
    executable_actions = [
        a for a in actions
        if (a.get("type") or a.get("action", "")) not in _NON_EXEC
    ]
    payload  = {
        "tc_id":        tc_id,
        "title":        title,
        "tc_group":     tc_group,
        "expected":     expected,
        "platform":     platform,
        "actions":      executable_actions,
        "source_filter": "all",
        "app_pkg":      session.get("app_package", ""),
        "app_activity": session.get("app_activity", ""),
        "bundle_id":    session.get("bundle_id", ""),
    }
    result = _sync_post_local("/capture/generate_from_actions", payload)
    broadcast_timeline_sync({
        "type": "generate_test_case", "source": "mcp",
        "platform": platform,
        "summary": f"{tc_id} ({len(executable_actions)} actions)",
        "ok": result.get("ok", False),
    })
    return result


def _exec_clear_actions(args: dict, session: dict) -> dict:
    result = _sync_post_local("/capture/clear_actions", {})
    broadcast_timeline_sync({
        "type": "clear_actions", "source": "mcp",
        "summary": f"타임라인 초기화 ({result.get('cleared', 0)}개 삭제)",
        "ok": result.get("ok", False),
    })
    return result


# ── 도구 디스패처 (블로킹) ─────────────────────────────────────

_TOOL_EXECUTORS = {
    "device_tap":         _exec_device_tap,
    "screenshot":         _exec_screenshot,
    "hierarchy":          _exec_hierarchy,
    "scroll":             _exec_scroll,
    "input_text":         _exec_input_text,
    "back":               _exec_back,
    "screen_info":        _exec_screen_info,
    "generate_test_case": _exec_generate_test_case,
    "clear_actions":      _exec_clear_actions,
}


def _run_tool(name: str, args: dict) -> tuple[bool, object]:
    """도구 실행. (ok, result_or_error_str)"""
    ok, session, err_msg = _mcp_session_check()
    _no_driver_tools = {"screen_info", "generate_test_case", "clear_actions"}
    if not ok and name not in _no_driver_tools:
        return False, err_msg
    if name not in _TOOL_EXECUTORS:
        return False, f"Unknown tool: {name}"
    if session is None:
        session = {}
    try:
        result = _TOOL_EXECUTORS[name](args, session)
        return True, result
    except Exception as exc:
        return False, f"Tool execution failed: {exc}"


# ── JSON-RPC 핸들러 ────────────────────────────────────────────

async def _handle_rpc(body: dict) -> dict | None:
    """JSON-RPC 2.0 메시지 처리. notification이면 None 반환."""
    global _mcp_connected, _mcp_client_id

    method  = body.get("method", "")
    params  = body.get("params") or {}
    req_id  = body.get("id")  # notification은 id 없음

    # ── initialize ──────────────────────────────────────────────
    if method == "initialize":
        _mcp_client_id = params.get("clientInfo", {}).get("name", "unknown")
        return _jsonrpc_ok(
            {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": _SERVER_INFO,
            },
            req_id,
        )

    # ── notifications/initialized ────────────────────────────────
    if method == "notifications/initialized":
        _mcp_connected = True
        return None  # notification: 응답 없음

    # ── tools/list ──────────────────────────────────────────────
    if method == "tools/list":
        return _jsonrpc_ok({"tools": TOOLS}, req_id)

    # ── tools/call ──────────────────────────────────────────────
    if method in ("tools/call", "tools/list"):
        # 클라이언트가 실제로 툴을 사용 중 → connected 확정
        _mcp_connected = True

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments") or {}

        if tool_name not in _TOOL_EXECUTORS:
            return _jsonrpc_err(-32601, f"Method not found: {tool_name}", req_id)

        _no_driver = {"screen_info", "generate_test_case", "clear_actions"}
        if tool_name not in _no_driver:
            ok_s, session_s, err_s = _mcp_session_check()
            if not ok_s:
                return _jsonrpc_err(-32001, err_s, req_id)

        loop = asyncio.get_running_loop()
        ok, result = await loop.run_in_executor(None, _run_tool, tool_name, tool_args)
        if not ok:
            return _jsonrpc_err(-32002, str(result), req_id)
        return _jsonrpc_ok(
            {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]},
            req_id,
        )

    # ── 알 수 없는 메서드 ────────────────────────────────────────
    if req_id is not None:
        return _jsonrpc_err(-32601, f"Method not found: {method}", req_id)
    return None  # notification 형태의 알 수 없는 메서드는 무시


# ── 엔드포인트 ────────────────────────────────────────────────

@router.post("/mcp")
async def mcp_rpc(request: Request):
    """JSON-RPC 2.0 요청 처리."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            _jsonrpc_err(-32700, "Parse error"),
            status_code=200,
        )

    response = await _handle_rpc(body)
    if response is None:
        # notification에 대한 빈 응답 (204-equivalent)
        return JSONResponse({}, status_code=200)
    return JSONResponse(response, status_code=200)


@router.get("/mcp/sse")
async def mcp_sse(request: Request):
    """SSE 스트림 — endpoint 이벤트 전송 (MCP 클라이언트 연결용)."""

    async def _event_generator():
        # MCP over SSE: endpoint 이벤트를 먼저 전송
        endpoint_url = f"http://127.0.0.1:{PORT}/mcp"
        yield f"event: endpoint\ndata: {endpoint_url}\n\n"
        # 연결 유지 (30초 heartbeat)
        while True:
            if await request.is_disconnected():
                break
            yield ": heartbeat\n\n"
            await asyncio.sleep(30)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/mcp/status")
async def mcp_status():
    """MCP 연결 상태 반환."""
    return JSONResponse({
        "connected":  _mcp_connected,
        "session_id": _mcp_client_id,
        "tools":      [t["name"] for t in TOOLS],
    })


@router.delete("/mcp/session")
async def mcp_disconnect():
    """MCP 세션 강제 해제 (대시보드 UI에서 OFF 전환 시 호출)."""
    global _mcp_connected, _mcp_client_id
    _mcp_connected = False
    _mcp_client_id = None
    return JSONResponse({"ok": True, "disconnected": True})
