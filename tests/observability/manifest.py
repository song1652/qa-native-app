"""Manifest repository and deterministic observability artifact rules."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
from pathlib import Path
from typing import Optional


def node_slug(nodeid: str) -> str:
    value = nodeid.replace("/", "_").replace("::", "__").replace(" ", "_")
    value = re.sub(r"[^A-Za-z0-9._-]", "_", value)
    if len(value) > 200:
        value = value[:200] + "_" + hashlib.sha1(nodeid.encode()).hexdigest()[:12]
    return value


def should_keep(policy: str, outcome: str, attempt_count: int = 1) -> bool:
    if policy == "always":
        return True
    if policy == "never":
        return False
    if attempt_count > 1:
        return True
    return outcome in ("failed", "error")


def load_manifest(artifact_dir: Path) -> dict:
    path = artifact_dir / "manifest.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_manifest(artifact_dir: Path, manifest: dict) -> None:
    """Persist a manifest atomically through a sibling temporary file."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    temporary = artifact_dir / "manifest.json.tmp"
    try:
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(artifact_dir / "manifest.json")
    except Exception as exc:
        print(f"[obs] manifest_write_failed: {exc}", file=sys.stderr)


def find_entry(manifest: dict, slug: str) -> Optional[dict]:
    return next(
        (entry for entry in manifest.get("entries", []) if entry.get("slug") == slug),
        None,
    )


def append_attempt(manifest: dict, nodeid: str, slug: str, attempt: dict) -> dict:
    """Append one immutable attempt and refresh compatibility summary fields."""
    entry = find_entry(manifest, slug)
    if entry is None:
        entry = {"nodeid": nodeid, "slug": slug, "attempts": []}
        manifest.setdefault("entries", []).append(entry)
    attempts = entry.setdefault("attempts", [])
    attempts.append(attempt)
    entry.update({key: value for key, value in attempt.items() if key != "n"})
    entry["nodeid"] = nodeid
    entry["slug"] = slug
    entry["attempt_count"] = len(attempts)
    return entry


def mp4_duration_seconds(path: Path) -> float:
    """Read the mvhd duration without introducing a media dependency."""
    try:
        data = path.read_bytes()
        index = data.find(b"mvhd")
        if index < 4 or index + 24 > len(data):
            return 0.0
        version = data[index + 4]
        if version == 0:
            timescale = struct.unpack(">I", data[index + 16 : index + 20])[0]
            duration = struct.unpack(">I", data[index + 20 : index + 24])[0]
        elif version == 1:
            if index + 36 > len(data):
                return 0.0
            timescale = struct.unpack(">I", data[index + 24 : index + 28])[0]
            duration = struct.unpack(">Q", data[index + 28 : index + 36])[0]
        else:
            return 0.0
        return duration / timescale if timescale else 0.0
    except (OSError, struct.error):
        return 0.0


def validate_mp4(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0 and mp4_duration_seconds(path) > 0
    except OSError:
        return False


def truncate_syslog(path: Path, max_bytes: int = 20 * 1024 * 1024) -> bool:
    if not path.exists() or path.stat().st_size <= max_bytes:
        return False
    with path.open("rb") as source:
        source.seek(-max_bytes, 2)
        data = source.read()
    path.write_bytes(data)
    return True
