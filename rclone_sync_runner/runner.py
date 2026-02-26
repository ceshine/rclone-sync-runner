"""Top-level orchestration for sequential job execution."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Sequence

from rclone_sync_runner.models import JobRunResult, RunSummary, RunnerConfig
from rclone_sync_runner.notifiers.base import Notifier
from rclone_sync_runner.rclone_subprocess import execute_sync_job

LOGGER = logging.getLogger(__name__)


def run_jobs(config: RunnerConfig, notifiers: Sequence[Notifier] | None = None) -> tuple[RunSummary, int]:
    """Execute jobs sequentially and produce a run summary.

    Args:
        config: Validated runner config.
        notifiers: Optional notifier hooks called on run completion.

    Returns:
        A tuple of run summary and process exit code.
    """
    run_started_at = datetime.now(UTC)
    results: list[JobRunResult] = []

    for job in config.jobs:
        result = execute_sync_job(job=job, global_config=config.global_config)
        results.append(result)

        if not result.succeeded and not config.global_config.continue_on_error:
            LOGGER.warning("Stopping early due to failed job '%s' and continue_on_error=false", result.job_name)
            break

    run_ended_at = datetime.now(UTC)
    duration_seconds = (run_ended_at - run_started_at).total_seconds()
    successful_jobs = sum(1 for result in results if result.succeeded)
    failed_jobs = len(results) - successful_jobs

    summary = RunSummary(
        total_jobs=len(results),
        successful_jobs=successful_jobs,
        failed_jobs=failed_jobs,
        duration_seconds=duration_seconds,
        results=results,
    )

    for notifier in notifiers or []:
        notifier.on_run_finished(summary)

    exit_code = 0 if failed_jobs == 0 else 1
    return summary, exit_code
