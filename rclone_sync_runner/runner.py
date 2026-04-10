"""Top-level orchestration for sequential job execution."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Callable, Sequence

from rclone_sync_runner.sync import execute_sync_job
from rclone_sync_runner.models import RunSummary, JobRunResult, RunnerConfig
from rclone_sync_runner.notifiers.base import Notifier

LOGGER = logging.getLogger(__name__)


def run_jobs(
    config: RunnerConfig,
    notifiers: Sequence[Notifier] | None = None,
    dry_run: bool = False,
    on_stats: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[RunSummary, int]:
    """Execute jobs sequentially and produce a run summary.

    Args:
        config (RunnerConfig): Validated runner config.
        notifiers (Sequence[Notifier] | None): Optional notifier hooks called on run completion.
        dry_run (bool): Whether to run all jobs in rclone dry-run mode.
        on_stats (Callable[[str, dict[str, Any]], None] | None): Optional callback
            forwarded to each job for live stats updates, receiving ``(job_name, stats_dict)``.

    Returns:
        tuple[RunSummary, int]: A tuple of run summary and process exit code.
    """
    run_started_at = datetime.now(UTC)
    results: list[JobRunResult] = []

    for job in config.jobs:
        result = execute_sync_job(job=job, global_config=config.global_config, dry_run=dry_run, on_stats=on_stats)
        results.append(result)

        if not result.succeeded and not config.global_config.continue_on_error:
            LOGGER.warning("Stopping early due to failed job '%s' and continue_on_error=false", result.job_name)
            break

    run_ended_at = datetime.now(UTC)
    duration_seconds = (run_ended_at - run_started_at).total_seconds()
    successful_jobs = sum(1 for result in results if result.succeeded)
    failed_jobs = len(results) - successful_jobs

    summary = RunSummary(
        global_name=config.global_config.name,
        total_jobs=len(results),
        successful_jobs=successful_jobs,
        failed_jobs=failed_jobs,
        duration_seconds=duration_seconds,
        dry_run=dry_run,
        results=results,
    )

    for notifier in notifiers or []:
        notifier.on_run_finished(summary)

    exit_code = 0 if failed_jobs == 0 else 1
    return summary, exit_code
