"""
App QA Dashboard 서버 (FastAPI + Uvicorn).

Usage:
    python agents/dashboard/serve.py
"""
from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── sys.path 설정 ────────────────────────────────────────────
# agents/dashboard/ 안의 모듈(shared, ws, routes/*, utils/*)을
# 임포트하려면 이 파일의 디렉토리를 sys.path에 추가합니다.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from shared import PORT  # noqa: E402
from utils.system import kill_port  # noqa: E402

# ── 라우터 임포트 ─────────────────────────────────────────────
import ws  # noqa: E402
from routes.api import router as api_router  # noqa: E402
from routes.capture import router as capture_router  # noqa: E402
from routes.import_studio import router as import_router  # noqa: E402
from routes.pipeline import router as pipeline_router  # noqa: E402

# ── FastAPI 앱 ────────────────────────────────────────────────
app = FastAPI(title="QA Dashboard", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{PORT}"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws.router)
app.include_router(api_router)
app.include_router(pipeline_router)
app.include_router(import_router)
app.include_router(capture_router)


# ── 서버 시작 ─────────────────────────────────────────────────
def main():
    kill_port(PORT)
    url = f"http://localhost:{PORT}"
    print(f"[Dashboard] 서버 시작: {url}")
    print(f"[Dashboard] WebSocket: ws://localhost:{PORT}/ws/timeline")
    print("[Dashboard] 종료: Ctrl+C")
    webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
