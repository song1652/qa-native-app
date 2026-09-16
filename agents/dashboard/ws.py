"""
ws.py — WebSocket Action Timeline 핸들러 및 브로드캐스트 헬퍼.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import _ws_connections, _ws_lock  # noqa: E402

router = APIRouter()

# uvicorn 이벤트 루프를 async 컨텍스트에서 한 번 캡처해 스레드 브로드캐스트에 재사용.
# asyncio.get_event_loop() 는 Python 3.10+ 비-메인 스레드에서 DeprecationWarning,
# 3.12+ 에서는 RuntimeError 를 유발하므로 루프 참조를 직접 저장한다.
_loop: asyncio.AbstractEventLoop | None = None


@router.websocket("/ws/timeline")
async def ws_timeline(websocket: WebSocket):
    global _loop
    if _loop is None:
        _loop = asyncio.get_running_loop()
    await websocket.accept()
    async with _ws_lock:
        _ws_connections.append(websocket)
    try:
        while True:
            # 클라이언트 ping 메시지로 연결 유지
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        async with _ws_lock:
            if websocket in _ws_connections:
                _ws_connections.remove(websocket)


async def _broadcast_timeline(event: dict) -> None:
    """연결된 모든 WebSocket 클라이언트에 Action Timeline 이벤트 전송."""
    global _loop
    if _loop is None:
        _loop = asyncio.get_running_loop()
    message = json.dumps(event, ensure_ascii=False)
    async with _ws_lock:
        dead = []
        for ws in _ws_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_connections.remove(ws)


def broadcast_timeline_sync(event: dict) -> None:
    """동기·스레드 컨텍스트에서 WebSocket 브로드캐스트 호출."""
    try:
        loop = _loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(_broadcast_timeline(event), loop)
    except Exception:
        pass
