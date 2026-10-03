"""Retention policy for local observability run artifacts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil


def load_retention_limits(config_path: Path) -> dict[str, int | float]:
    """Load only retention limits without importing the pytest runtime."""
    limits: dict[str, int | float] = {"max_runs": 20, "max_total_mb": 2048}
    try:
        data = json.loads(Path(config_path).read_text(encoding="utf-8"))
        retention = data.get("retention", {})
        if isinstance(retention, dict):
            for key in limits:
                value = retention.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                    limits[key] = value
    except (OSError, TypeError, json.JSONDecodeError):
        pass
    return limits


def _tree_size(path: Path) -> int:
    total = 0
    try:
        for child in path.rglob("*"):
            if child.is_file() and not child.is_symlink():
                try:
                    total += child.stat().st_size
                except OSError:
                    continue
    except OSError:
        pass
    return total


def _read_metadata(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _utc_timestamp(value) -> datetime | None:
    try:
        # Legacy manifests use naive local datetime.now(); results carry UTC.
        return datetime.fromisoformat(str(value)).astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def _manifest_state(run_dir: Path, now: datetime, grace: timedelta) -> tuple[str, datetime]:
    """Use owned outcomes for runs that never produced an artifact manifest."""
    manifest = _read_metadata(run_dir / "artifacts" / "manifest.json")
    result = _read_metadata(run_dir / "execution_result.json")
    if result.get("run_id") != run_dir.name:
        result = {}
    manifest_started = _utc_timestamp(manifest.get("started_at"))
    started_at = (_utc_timestamp(result.get("started_at")) or manifest_started
                  or _utc_timestamp(result.get("finished_at"))
                  or _utc_timestamp(manifest.get("finished_at")))
    if started_at is None:
        try:
            started_at = datetime.fromtimestamp(run_dir.stat().st_mtime, timezone.utc)
        except OSError:
            started_at = now
    status = result.get("status")
    if not isinstance(status, str):
        status = None
    if status in {"passed", "failed", "cancelled", "timed_out", "interrupted", "incomplete"}:
        active = False
    elif status == "running":
        active = True
    else:
        active = manifest.get("finished_at") is None and manifest_started is not None
    if active and now - started_at < grace:
        return "protected", started_at
    return "deletable", started_at


def purge_old_runs(
    runs_dir: Path,
    max_runs: int = 20,
    max_total_mb: float = 2048,
    *,
    now: datetime | None = None,
    active_grace_hours: float = 6,
) -> dict:
    """Prune oldest completed/stale runs while protecting recent active runs."""
    runs_dir = Path(runs_dir)
    empty = {
        "deleted_runs": [],
        "protected_runs": [],
        "freed_bytes": 0,
        "remaining_runs": 0,
        "remaining_bytes": 0,
    }
    if not runs_dir.exists():
        return empty

    now = (now or datetime.now()).astimezone(timezone.utc)
    grace = timedelta(hours=max(0, active_grace_hours))
    protected: list[tuple[datetime, Path, int]] = []
    deletable: list[tuple[datetime, Path, int]] = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir() or run_dir.is_symlink():
            continue
        state, started_at = _manifest_state(run_dir, now, grace)
        record = (started_at, run_dir, _tree_size(run_dir))
        (protected if state == "protected" else deletable).append(record)

    deletable.sort(key=lambda item: (item[0], item[1].name))
    deletable_bytes = sum(item[2] for item in deletable)
    max_bytes = max(0, int(max_total_mb * 1024 * 1024))
    max_runs = max(0, int(max_runs))
    deleted_runs: list[str] = []
    freed_bytes = 0

    while deletable and (len(deletable) > max_runs or deletable_bytes > max_bytes):
        _, oldest, size = deletable.pop(0)
        shutil.rmtree(oldest)
        deleted_runs.append(oldest.name)
        freed_bytes += size
        deletable_bytes = max(0, deletable_bytes - size)

    remaining = [item for item in protected + deletable if item[1].exists()]
    return {
        "deleted_runs": deleted_runs,
        "protected_runs": sorted(item[1].name for item in protected),
        "freed_bytes": freed_bytes,
        "remaining_runs": len(remaining),
        "remaining_bytes": sum(_tree_size(item[1]) for item in remaining),
    }
