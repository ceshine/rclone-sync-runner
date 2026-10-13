"""Run summary helpers shared by notifiers."""

from __future__ import annotations

from rclone_sync_runner.models import RunSummary


def stats_number(last_stats: dict[str, object] | None, key: str) -> float:
    """Get a numeric value from rclone stats with safe fallback.

    Args:
        last_stats (dict[str, object] | None): rclone stats payload, or None if unavailable.
        key (str): Stats field name to retrieve.

    Returns:
        float: Numeric value for the key, or ``0.0`` if absent or non-numeric.
    """
    if not last_stats:
        return 0.0

    value = last_stats.get(key)
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def aggregate_job_stats(summary: RunSummary) -> dict[str, float]:
    """Aggregate numeric values from all job last_stats payloads.

    Args:
        summary (RunSummary): The completed run summary containing job results.

    Returns:
        dict[str, float]: Summed totals keyed by stat name
            (``transfers``, ``deletes``, ``checks``, ``bytes``, ``duration_seconds``).
    """
    totals = {
        "transfers": 0.0,
        "deletes": 0.0,
        "checks": 0.0,
        "bytes": 0.0,
        "duration_seconds": 0.0,
    }

    for result in summary.results:
        totals["transfers"] += stats_number(result.last_stats, "transfers")
        totals["deletes"] += stats_number(result.last_stats, "deletes")
        totals["checks"] += stats_number(result.last_stats, "checks")
        totals["bytes"] += stats_number(result.last_stats, "bytes")
        totals["duration_seconds"] += stats_number(result.last_stats, "elapsedTime")

    return totals
