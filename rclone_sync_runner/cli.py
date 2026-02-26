"""CLI entrypoint for running configured rclone sync jobs."""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from rclone_sync_runner.config import ConfigError, load_config
from rclone_sync_runner.logging_setup import setup_logging
from rclone_sync_runner.models import RunSummary
from rclone_sync_runner.notifiers.logging_notifier import LoggingNotifier
from rclone_sync_runner.runner import run_jobs

app = typer.Typer(help="Run sequential rclone sync jobs from YAML configuration.")
LOGGER = logging.getLogger(__name__)


def _render_summary(summary: RunSummary) -> None:
    """Render a run summary table using Rich."""
    console = Console()
    table = Table(title="rclone-sync-runner summary")
    table.add_column("Job")
    table.add_column("Source")
    table.add_column("Destination")
    table.add_column("Status")
    table.add_column("Return Code")
    table.add_column("Duration (s)")
    table.add_column("Errors")

    for result in summary.results:
        status = "OK" if result.succeeded else "FAILED"
        table.add_row(
            result.job_name,
            result.source,
            result.destination,
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


@app.command()
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
    app()


if __name__ == "__main__":
    main()
