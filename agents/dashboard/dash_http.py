"""dash_http.py — HTTP 요청 유틸리티 (serve.py Phase-3 분리).

HTTP 핸들러 메서드가 공통으로 사용하는 요청 파싱·파일 잠금 유틸.
serve.py가 이 모듈을 import하고, 이 모듈은 serve를 import하지 않는다 (순환 import 방지).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


MAX_JSON_BODY_BYTES = 2 * 1024 * 1024


class BodyTooLarge(Exception):
    pass


def _content_length(handler) -> int:
    try:
        return max(int(handler.headers.get("Content-Length", 0)), 0)
    except ValueError:
        return 0


def _read_raw_body(handler, limit: int) -> bytes:
    length = _content_length(handler)
    if length > limit:
        raise BodyTooLarge(length)
    return handler.rfile.read(length) if length else b""


def _read_body(handler, limit: int = MAX_JSON_BODY_BYTES) -> dict:
    """요청 바디를 JSON으로 파싱해 반환. 바디 없으면 빈 dict. 상한 초과는 BodyTooLarge."""
    raw = _read_raw_body(handler, limit)
    return json.loads(raw.decode("utf-8")) if raw else {}


def _read_profiles_locked(path: Path) -> dict:
    from _paths import _file_lock
    from routes_tc_import_admin import ImportRunError
    path.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(path.with_suffix(".lock"), path):
        if not path.exists():
            return {"profiles": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ImportRunError("프로필 저장소를 읽을 수 없습니다", "PROFILE_STORE_ERROR") from exc
        if not isinstance(data, dict) or not isinstance(data.get("profiles", []), list):
            raise ImportRunError("프로필 저장소 형식이 잘못되었습니다", "PROFILE_STORE_ERROR")
        return data


def _update_profiles_locked(path: Path, mutate) -> dict:
    import tempfile as _tempfile
    from _paths import _file_lock
    from routes_tc_import_admin import ImportRunError
    path.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(path.with_suffix(".lock"), path):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ImportRunError("프로필 저장소를 읽을 수 없습니다", "PROFILE_STORE_ERROR") from exc
            if not isinstance(data, dict) or not isinstance(data.get("profiles", []), list):
                raise ImportRunError("프로필 저장소 형식이 잘못되었습니다", "PROFILE_STORE_ERROR")
        else:
            data = {"profiles": []}
        result = mutate(data)
        fd, tmp = _tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
            Path(tmp).replace(path)
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise
        return result
