"""
routes/observability.py — TC 실행 관측성 API 엔드포인트.

GET  /api/run_artifacts              → 최근 run 목록
GET  /api/run_artifacts/{run_id}     → manifest 반환
GET  /api/run_artifacts/{run_id}/video   → video.mp4 스트리밍 (HTTP Range)
GET  /api/run_artifacts/{run_id}/logcat  → syslog.txt 뒤쪽 N줄
GET  /api/run_artifacts/{run_id}/screenshot → screenshot.png
DELETE /api/run_artifacts/{run_id}   → run 삭제
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.responses import FileResponse

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
RUNS_DIR = PROJECT_ROOT / "state" / "runs"

# run_id 정규식 — PRD §3-2, §7-2
_RUN_ID_RE = re.compile(r"^run_[a-z]+_\d{8}_\d{6}_\d{3}$")


def _artifact_root(run_id: str) -> Path:
    """run_id 검증 + artifacts 디렉토리 반환. 실패 시 HTTPException."""
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="invalid_run_id")
    root = (RUNS_DIR / run_id / "artifacts").resolve()
    base = RUNS_DIR.resolve()
    if not root.is_relative_to(base):
        raise HTTPException(status_code=404, detail="run_not_found")
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="run_not_found")
    return root


def _load_manifest(artifact_dir: Path) -> dict:
    mf = artifact_dir / "manifest.json"
    if not mf.exists():
        raise HTTPException(status_code=404, detail="run_not_found")
    try:
        return json.loads(mf.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="manifest_parse_error")


def _find_entry(manifest: dict, nodeid: str) -> Optional[dict]:
    for entry in manifest.get("entries", []):
        if entry.get("nodeid") == nodeid:
            return entry
    return None


def _attempts(entry: dict) -> list[dict]:
    current = entry.get("attempts")
    if isinstance(current, list) and current:
        return [dict(item) for item in current]
    legacy = {
        key: value for key, value in entry.items()
        if key not in {"nodeid", "slug", "attempts", "attempt_count"}
    }
    legacy["n"] = int(entry.get("attempt_count") or 1)
    return [legacy]


def _select_attempt(entry: dict, attempt: Optional[int]) -> Optional[dict]:
    attempts = _attempts(entry)
    if attempt is None:
        return attempts[-1] if attempts else None
    return next((item for item in attempts if int(item.get("n", 0)) == attempt), None)


def _artifact_urls(run_id: str, nodeid: str, attempt: dict) -> dict:
    from urllib.parse import quote
    encoded = quote(nodeid, safe="")
    number = int(attempt.get("n", 1))
    result = dict(attempt)
    result["video_url"] = (
        f"/api/run_artifacts/{run_id}/video?nodeid={encoded}&attempt={number}"
        if attempt.get("kept") and attempt.get("video") else None
    )
    result["syslog_url"] = (
        f"/api/run_artifacts/{run_id}/logcat?nodeid={encoded}&attempt={number}&tail=2000"
        if attempt.get("kept") and attempt.get("syslog") else None
    )
    shot = attempt.get("screenshot")
    result["screenshot_url"] = None
    if shot and shot.get("external") and str(shot.get("path", "")).startswith("reports/screenshots/"):
        result["screenshot_url"] = "/screenshots/" + str(shot["path"])[len("reports/screenshots/"):]
    elif attempt.get("kept") and shot:
        result["screenshot_url"] = (
            f"/api/run_artifacts/{run_id}/screenshot?nodeid={encoded}&attempt={number}"
        )
    return result


def _safe_artifact_path(artifact_dir: Path, rel_path: str) -> Path:
    """manifest에서 얻은 상대 경로를 절대 경로로 변환. 탈출 방지."""
    p = (artifact_dir / rel_path).resolve()
    if not p.is_relative_to(artifact_dir.resolve()):
        raise HTTPException(status_code=403, detail="forbidden")
    return p


def _du_bytes(path: Path) -> int:
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except Exception:
                    pass
    except Exception:
        pass
    return total


# ─── GET /api/run_artifacts ─────────────────────────────────────
@router.get("/api/runs")
@router.get("/api/run_artifacts")
async def list_run_artifacts(
    platform: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
):
    """최근 run 목록. started_at 내림차순."""
    runs = []
    if not RUNS_DIR.exists():
        return JSONResponse({"ok": True, "runs": []})

    for run_dir in RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        mf = run_dir / "artifacts" / "manifest.json"
        if not mf.exists():
            continue
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if platform and m.get("platform") != platform:
            continue
        entries = m.get("entries", [])
        total = len(entries)
        latest = [(_attempts(entry) or [{}])[-1] for entry in entries]
        failed = sum(1 for e in latest if e.get("outcome") in ("failed", "error"))
        with_video = sum(1 for e in latest if e.get("video") is not None and e.get("kept"))
        with_syslog = sum(1 for e in latest if e.get("syslog") is not None and e.get("kept"))
        size_bytes = _du_bytes(run_dir)
        size_mb = round(size_bytes / (1024 * 1024), 2)
        runs.append({
            "run_id": m.get("run_id", run_dir.name),
            "platform": m.get("platform", ""),
            "mode": m.get("mode", ""),
            "udid": m.get("udid", ""),
            "device_name": m.get("device_name", ""),
            "started_at": m.get("started_at", ""),
            "finished_at": m.get("finished_at"),
            "keep_policy": m.get("keep_policy", "on_failure"),
            "counts": {
                "total": total,
                "failed": failed,
                "with_video": with_video,
                "with_syslog": with_syslog,
            },
            "size_mb": size_mb,
        })

    runs.sort(key=lambda x: x["started_at"], reverse=True)
    return JSONResponse({"ok": True, "runs": runs[:limit]})


# ─── GET /api/run_artifacts/{run_id} ────────────────────────────
@router.get("/api/run_artifacts/{run_id}")
async def get_run_artifacts(run_id: str):
    """manifest 전체 + 각 아티팩트 조회 URL 포함."""
    artifact_dir = _artifact_root(run_id)
    manifest = _load_manifest(artifact_dir)

    entries_out = []
    for entry in manifest.get("entries", []):
        nodeid = entry.get("nodeid", "")
        attempts = [_artifact_urls(run_id, nodeid, item) for item in _attempts(entry)]
        latest = attempts[-1] if attempts else {}
        entry_out = dict(entry)
        entry_out.update({k: v for k, v in latest.items() if k != "n"})
        entry_out["attempts"] = attempts
        entry_out["attempt_count"] = len(attempts)
        entries_out.append(entry_out)

    result = {k: v for k, v in manifest.items() if k != "entries"}
    result["ok"] = True
    result["entries"] = entries_out
    return JSONResponse(result)


# ─── GET /api/run_artifacts/{run_id}/video ──────────────────────
@router.get("/api/run_artifacts/{run_id}/video")
async def get_run_video(
    run_id: str,
    nodeid: str = Query(...),
    attempt: Optional[int] = Query(None, ge=1),
):
    """video.mp4 스트리밍. starlette FileResponse가 HTTP Range 처리."""
    artifact_dir = _artifact_root(run_id)
    manifest = _load_manifest(artifact_dir)

    entry = _find_entry(manifest, nodeid)
    if entry is None:
        raise HTTPException(status_code=404, detail="artifact_not_found")

    selected = _select_attempt(entry, attempt)
    video = selected.get("video") if selected else None
    if not video or not selected.get("kept"):
        raise HTTPException(status_code=404, detail="artifact_not_found")

    video_path = _safe_artifact_path(artifact_dir, video["path"])
    if not video_path.exists() or video_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="artifact_not_found")

    return FileResponse(str(video_path), media_type="video/mp4")


# ─── GET /api/run_artifacts/{run_id}/screenshot ─────────────────
@router.get("/api/run_artifacts/{run_id}/screenshot")
async def get_run_screenshot(
    run_id: str,
    nodeid: str = Query(...),
    attempt: Optional[int] = Query(None, ge=1),
):
    artifact_dir = _artifact_root(run_id)
    manifest = _load_manifest(artifact_dir)
    entry = _find_entry(manifest, nodeid)
    if entry is None:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    selected = _select_attempt(entry, attempt)
    screenshot = selected.get("screenshot") if selected else None
    if not screenshot or screenshot.get("external") or not selected.get("kept"):
        raise HTTPException(status_code=404, detail="artifact_not_found")
    screenshot_path = _safe_artifact_path(artifact_dir, screenshot["path"])
    if not screenshot_path.is_file() or screenshot_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    return FileResponse(str(screenshot_path), media_type="image/png")


# ─── GET /api/run_artifacts/{run_id}/logcat ─────────────────────
@router.get("/api/run_artifacts/{run_id}/logcat")
async def get_run_logcat(
    run_id: str,
    nodeid: str = Query(...),
    attempt: Optional[int] = Query(None, ge=1),
    tail: int = Query(2000, ge=1, le=200000),
    download: int = Query(0),
):
    """syslog.txt 뒤쪽 tail 줄 반환."""
    artifact_dir = _artifact_root(run_id)
    manifest = _load_manifest(artifact_dir)

    entry = _find_entry(manifest, nodeid)
    if entry is None:
        raise HTTPException(status_code=404, detail="artifact_not_found")

    selected = _select_attempt(entry, attempt)
    syslog = selected.get("syslog") if selected else None
    if not syslog or not selected.get("kept"):
        raise HTTPException(status_code=404, detail="artifact_not_found")

    syslog_path = _safe_artifact_path(artifact_dir, syslog["path"])
    if not syslog_path.exists():
        raise HTTPException(status_code=404, detail="artifact_not_found")

    try:
        content = syslog_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        raise HTTPException(status_code=500, detail="read_error")

    lines = content.splitlines()
    tail_lines = lines[-tail:] if len(lines) > tail else lines
    result = "\n".join(tail_lines)

    headers = {}
    if download:
        slug = syslog["path"].split("/")[0] if "/" in syslog["path"] else "syslog"
        headers["Content-Disposition"] = f'attachment; filename="{slug}_syslog.txt"'
    else:
        headers["Content-Disposition"] = "inline"

    return PlainTextResponse(
        result,
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )


# ─── DELETE /api/run_artifacts/{run_id} ─────────────────────────
@router.delete("/api/run_artifacts/{run_id}")
async def delete_run_artifacts(run_id: str):
    """run 디렉토리 삭제. 실행 중이면 409."""
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="invalid_run_id")

    run_dir = (RUNS_DIR / run_id).resolve()
    base = RUNS_DIR.resolve()
    if not run_dir.is_relative_to(base):
        raise HTTPException(status_code=404, detail="run_not_found")
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="run_not_found")

    mf = run_dir / "artifacts" / "manifest.json"
    if mf.exists():
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
            if m.get("finished_at") is None:
                raise HTTPException(status_code=409, detail="run_active")
        except HTTPException:
            raise
        except Exception:
            pass

    try:
        shutil.rmtree(str(run_dir))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse({"ok": True, "deleted": run_id})
