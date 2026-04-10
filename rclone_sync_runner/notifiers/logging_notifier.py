"""Logging notifier used by the MVP."""

from __future__ import annotations

import logging

from rclone_sync_runner.models import RunSummary

LOGGER = logging.getLogger(__name__)


class LoggingNotifier:
    """Emit a concise run summary to application logs."""

    def on_run_finished(self, summary: RunSummary) -> None:
        """Log run-level completion details.

        Args:
            summary (RunSummary): Run summary object.
        """
        LOGGER.info(
            "Run finished: mode=%s total=%s succeeded=%s failed=%s duration=%.2fs",
            "dry-run" if summary.dry_run else "live",
            summary.total_jobs,
            summary.successful_jobs,
            summary.failed_jobs,
            summary.duration_seconds,
        )
