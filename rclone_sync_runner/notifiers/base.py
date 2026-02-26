"""Notifier extension-point contracts."""

from __future__ import annotations

from typing import Protocol

from rclone_sync_runner.models import RunSummary


class Notifier(Protocol):
    """Protocol for run-finished notification hooks."""

    def on_run_finished(self, summary: RunSummary) -> None:
        """Handle run completion event."""
