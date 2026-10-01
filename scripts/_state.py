"""TC 스튜디오용 JSON 상태 파일의 원자적 read/update."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import _paths


def read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    with _paths._file_lock(path.with_suffix(".lock"), path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}


def update_state(path: Path, mutator) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _paths._file_lock(path.with_suffix(".lock"), path):
        current = {}
        if path.exists():
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                backup = path.with_name(f"{path.stem}.corrupt.{datetime.now():%Y%m%d_%H%M%S}{path.suffix}")
                shutil.copy2(path, backup)
                raise ValueError(f"상태 파일 파싱 실패: {path}") from exc
        value = mutator(current)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(value, out, ensure_ascii=False, indent=2)
            Path(tmp).replace(path)
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise
        return value
