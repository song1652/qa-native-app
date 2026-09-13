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


@router.websocket("/ws/timeline")
async def ws_timeline(websocket: WebSocket):
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
    """동기 코드에서 WebSocket 브로드캐스트 호출 (threading 환경)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(_broadcast_timeline(event), loop)
    except Exception:
        pass
