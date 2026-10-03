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


def _result(run_dir, status, started_at=None, finished_at=None, *, owner=None):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / 'execution_result.json').write_text(json.dumps({
        'run_id': owner or run_dir.name, 'status': status,
        'started_at': started_at.isoformat() if started_at else None,
        'finished_at': finished_at.isoformat() if finished_at else None,
    }))


def test_newest_result_only_failure_survives_purge_after_preflight(tmp_path):
    runs = tmp_path / 'runs'
    old = _run(runs, 'old', started_at=NOW - timedelta(days=2), finished=True)
    failed = runs / 'new-failure'
    _result(failed, 'failed', NOW - timedelta(minutes=1), NOW)
    result = purge_old_runs(runs, max_runs=1, max_total_mb=100, now=NOW)
    assert failed.exists() and not old.exists()
    assert result['deleted_runs'] == ['old']


def test_recent_result_only_running_run_is_protected_for_six_hours(tmp_path):
    runs = tmp_path / 'runs'
    recent, stale = runs / 'recent', runs / 'stale'
    _result(recent, 'running', NOW - timedelta(hours=1))
    _result(stale, 'running', NOW - timedelta(hours=7))
    result = purge_old_runs(runs, max_runs=0, max_total_mb=0, now=NOW)
    assert recent.exists() and not stale.exists()
    assert result['protected_runs'] == ['recent']


def test_owned_terminal_result_releases_unfinished_manifest_protection(tmp_path):
    runs = tmp_path / 'runs'
    for status in ('timed_out', 'interrupted', 'failed', 'cancelled'):
        directory = _run(runs, status, started_at=NOW - timedelta(minutes=20), finished=False)
        _result(directory, status, NOW - timedelta(minutes=20), NOW)
    result = purge_old_runs(runs, max_runs=0, max_total_mb=0, now=NOW)
    assert len(result['deleted_runs']) == 4
    assert not result['protected_runs']


def test_mixed_local_manifest_and_offset_results_order_by_actual_instant(tmp_path):
    from datetime import timezone
    runs = tmp_path / 'runs'
    old = _run(runs, 'local-old', started_at=NOW - timedelta(hours=2), finished=True)
    new = runs / 'offset-new'
    # Legacy manifests use local naive datetime.now(); results use aware UTC.
    offset = timezone(timedelta(hours=-4))
    _result(new, 'failed', (NOW - timedelta(hours=1)).astimezone(offset))
    result = purge_old_runs(runs, max_runs=1, max_total_mb=100, now=NOW.astimezone(timezone.utc))
    assert not old.exists() and new.exists()
    assert result['deleted_runs'] == ['local-old']


def test_new_orphan_directory_uses_mtime_instead_of_ancient_default(tmp_path):
    import os
    runs = tmp_path / 'runs'
    old = _run(runs, 'old', started_at=NOW - timedelta(days=1), finished=True)
    orphan = runs / 'orphan'
    orphan.mkdir()
    os.utime(orphan, (NOW.timestamp(), NOW.timestamp()))
    purge_old_runs(runs, max_runs=1, max_total_mb=100, now=NOW)
    assert orphan.exists() and not old.exists()


def test_foreign_result_cannot_unprotect_an_active_manifest(tmp_path):
    runs = tmp_path / 'runs'
    directory = _run(runs, 'active', started_at=NOW - timedelta(hours=1), finished=False)
    _result(directory, 'timed_out', NOW - timedelta(days=1), NOW, owner='another-run')
    result = purge_old_runs(runs, max_runs=0, max_total_mb=0, now=NOW)
    assert directory.exists()
    assert result['protected_runs'] == ['active']


def test_result_finished_time_orders_run_when_started_time_is_missing(tmp_path):
    runs = tmp_path / 'runs'
    old = _run(runs, 'old', started_at=NOW - timedelta(days=1), finished=True)
    new = runs / 'finished-only'
    _result(new, 'interrupted', finished_at=NOW)
    purge_old_runs(runs, max_runs=1, max_total_mb=100, now=NOW)
    assert new.exists() and not old.exists()


def test_aware_and_naive_manifest_timestamps_are_comparable(tmp_path):
    from datetime import timezone
    runs = tmp_path / 'runs'
    old = _run(runs, 'aware-old', started_at=(NOW - timedelta(hours=2)).astimezone(timezone.utc), finished=True)
    new = _run(runs, 'naive-new', started_at=NOW - timedelta(hours=1), finished=True)
    result = purge_old_runs(runs, max_runs=1, max_total_mb=100, now=NOW)
    assert new.exists() and not old.exists()
    assert result['deleted_runs'] == ['aware-old']


def test_malformed_result_status_does_not_break_retention_or_unprotect_manifest(tmp_path):
    runs = tmp_path / 'runs'
    for name, status in [('list-status', ['failed']), ('dict-status', {'status': 'failed'})]:
        directory = _run(runs, name, started_at=NOW - timedelta(hours=1), finished=False)
        _result(directory, status, NOW - timedelta(hours=1))
    result = purge_old_runs(runs, max_runs=0, max_total_mb=0, now=NOW)
    assert result['protected_runs'] == ['dict-status', 'list-status']
    assert not result['deleted_runs']
