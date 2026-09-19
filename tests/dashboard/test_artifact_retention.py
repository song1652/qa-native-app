"""Deterministic retention tests for observability run artifacts."""

from datetime import datetime, timedelta
import json
from pathlib import Path
import sys


DASHBOARD = Path(__file__).parents[2] / "agents" / "dashboard"
sys.path.insert(0, str(DASHBOARD))

from utils.artifact_retention import load_retention_limits, purge_old_runs  # noqa: E402


NOW = datetime(2026, 9, 19, 1, 0, 0)


def _run(runs_dir: Path, run_id: str, *, started_at: datetime, finished: bool, size=1):
    artifact_dir = runs_dir / run_id / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "payload.bin").write_bytes(b"x" * size)
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "started_at": started_at.isoformat(),
                "finished_at": NOW.isoformat() if finished else None,
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    return runs_dir / run_id


def test_recent_unfinished_run_is_protected_while_stale_run_is_prunable(tmp_path):
    runs = tmp_path / "runs"
    recent = _run(runs, "recent", started_at=NOW - timedelta(hours=1), finished=False)
    stale = _run(runs, "stale", started_at=NOW - timedelta(hours=7), finished=False)

    result = purge_old_runs(runs, max_runs=0, max_total_mb=0, now=NOW)

    assert recent.exists()
    assert not stale.exists()
    assert result["deleted_runs"] == ["stale"]
    assert result["protected_runs"] == ["recent"]


def test_count_limit_deletes_oldest_completed_run_first(tmp_path):
    runs = tmp_path / "runs"
    oldest = _run(runs, "oldest", started_at=NOW - timedelta(days=3), finished=True)
    middle = _run(runs, "middle", started_at=NOW - timedelta(days=2), finished=True)
    newest = _run(runs, "newest", started_at=NOW - timedelta(days=1), finished=True)

    result = purge_old_runs(runs, max_runs=2, max_total_mb=100, now=NOW)

    assert not oldest.exists()
    assert middle.exists() and newest.exists()
    assert result["deleted_runs"] == ["oldest"]
    assert result["remaining_runs"] == 2


def test_size_limit_deletes_oldest_until_remaining_bytes_fit(tmp_path):
    runs = tmp_path / "runs"
    oldest = _run(
        runs, "large-old", started_at=NOW - timedelta(days=2), finished=True, size=700_000
    )
    newest = _run(
        runs, "large-new", started_at=NOW - timedelta(days=1), finished=True, size=700_000
    )

    result = purge_old_runs(runs, max_runs=20, max_total_mb=1, now=NOW)

    assert not oldest.exists()
    assert newest.exists()
    assert result["freed_bytes"] >= 700_000
    assert result["remaining_bytes"] < 1024 * 1024


def test_missing_runs_directory_is_a_noop(tmp_path):
    result = purge_old_runs(tmp_path / "missing", now=NOW)

    assert result == {
        "deleted_runs": [],
        "protected_runs": [],
        "freed_bytes": 0,
        "remaining_runs": 0,
        "remaining_bytes": 0,
    }


def test_retention_config_merges_partial_values_with_safe_defaults(tmp_path):
    config = tmp_path / "observability.json"
    config.write_text(
        json.dumps({"retention": {"max_runs": 7}}), encoding="utf-8"
    )

    assert load_retention_limits(config) == {"max_runs": 7, "max_total_mb": 2048}
    assert load_retention_limits(tmp_path / "missing.json") == {
        "max_runs": 20,
        "max_total_mb": 2048,
    }
