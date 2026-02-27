"""CLI entrypoint for running configured rclone sync jobs."""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .runner import run_jobs
from .models import RunSummary
from .config import ConfigError, load_config
from .logging_setup import setup_logging
from .notifiers.logging_notifier import LoggingNotifier


LOGGER = logging.getLogger(__name__)
TYPER_APP = typer.Typer(help="Run sequential rclone sync jobs from YAML configuration.")


def _render_summary(summary: RunSummary) -> None:
    """Render a run summary table using Rich."""

    def _stats_value(last_stats: dict[str, object] | None, key: str) -> str:
        """Get a numeric stats value from last_stats with a safe fallback."""
        if not last_stats:
            return "0"

        value = last_stats.get(key)
        if isinstance(value, bool):
            return "0"
        if isinstance(value, int | float):
            return str(int(value))
        return "0"

    console = Console()
    table = Table(title="rclone-sync-runner summary")
    table.add_column("Job")
    table.add_column("Transfers")
    table.add_column("Deletes")
    table.add_column("Checks")
    table.add_column("Bytes")
    table.add_column("Status")
    table.add_column("Return Code")
    table.add_column("Duration (s)")
    table.add_column("Errors")

    for result in summary.results:
        status = "OK" if result.succeeded else "FAILED"
        table.add_row(
            result.job_name,
            _stats_value(result.last_stats, "transfers"),
            _stats_value(result.last_stats, "deletes"),
            _stats_value(result.last_stats, "checks"),
            _stats_value(result.last_stats, "bytes"),
            status,
            str(result.return_code),
            f"{result.duration_seconds:.2f}",
            str(result.error_count),
        )

    console.print(table)
    console.print(
        (
            "Run totals: "
            f"total={summary.total_jobs} "
            f"succeeded={summary.successful_jobs} "
            f"failed={summary.failed_jobs} "
            f"duration={summary.duration_seconds:.2f}s"
        )
    )


@TYPER_APP.command()
def run(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        help="Path to YAML config file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
) -> None:
    """Execute all configured jobs sequentially."""
    setup_logging("INFO")

    try:
        parsed_config = load_config(config)
    except ConfigError as error:
        LOGGER.error("%s", error)
        raise typer.Exit(code=2) from error

    setup_logging(parsed_config.global_config.log_level)

    try:
        summary, exit_code = run_jobs(config=parsed_config, notifiers=[LoggingNotifier()])
    except Exception:
        LOGGER.exception("Unexpected runtime orchestration failure")
        raise typer.Exit(code=2) from None

    _render_summary(summary)
    raise typer.Exit(code=exit_code)


def main() -> None:
    """Console script wrapper."""
    TYPER_APP()


if __name__ == "__main__":
    main()
