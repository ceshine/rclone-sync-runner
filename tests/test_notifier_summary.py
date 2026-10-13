"""Tests for run summary helpers shared by notifiers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from rclone_sync_runner.models import RunSummary, JobRunResult
from rclone_sync_runner.notifiers.summary import stats_number, aggregate_job_stats


def _job_result(job_name: str, last_stats: dict[str, Any] | None) -> JobRunResult:
    now = datetime.now(UTC)
    return JobRunResult(
        job_name=job_name,
        source="/src",
        destination="remote:dst",
        started_at=now,
        ended_at=now,
        duration_seconds=1.0,
        return_code=0,
        succeeded=True,
        dry_run=False,
        error_count=0,
        error_samples=[],
        last_stats=last_stats,
    )


def test_stats_number_returns_numeric_values() -> None:
    assert stats_number({"bytes": 3}, "bytes") == 3.0
    assert stats_number({"elapsedTime": 2.5}, "elapsedTime") == 2.5


def test_stats_number_ignores_missing_and_non_numeric_values() -> None:
    assert stats_number(None, "bytes") == 0.0
    assert stats_number({}, "bytes") == 0.0
    assert stats_number({"bytes": "12"}, "bytes") == 0.0
    # bool is a subclass of int, but True is not a byte count.
    assert stats_number({"bytes": True}, "bytes") == 0.0


def test_aggregate_job_stats_sums_all_jobs() -> None:
    summary = RunSummary(
        total_jobs=3,
        successful_jobs=3,
        failed_jobs=0,
        duration_seconds=6.0,
        dry_run=False,
        results=[
            _job_result("a", {"bytes": 100, "transfers": 1, "deletes": 2, "checks": 3, "elapsedTime": 1.5}),
            _job_result("b", {"bytes": 50, "transfers": 4, "deletes": 0, "checks": 1, "elapsedTime": 2.0}),
            _job_result("c", None),
        ],
    )

    assert aggregate_job_stats(summary) == {
        "transfers": 5.0,
        "deletes": 2.0,
        "checks": 4.0,
        "bytes": 150.0,
        "duration_seconds": 3.5,
    }
