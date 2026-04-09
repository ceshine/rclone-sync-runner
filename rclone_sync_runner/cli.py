"""CLI entrypoint for running configured rclone sync jobs."""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import ConfigError, build_runner_config, load_config, render_config_yaml
from .discovery import list_rclone_dirs, match_folder_pairs
from .logging_setup import setup_logging
from .models import RunSummary, RunnerConfig
from .notifiers import LoggingNotifier, Notifier, TelegramNotifier
from .runner import run_jobs


LOGGER = logging.getLogger(__name__)
TYPER_APP = typer.Typer(help="Run sequential rclone sync jobs from YAML configuration.")


def _build_notifiers(config: RunnerConfig) -> list[Notifier]:
    """Build notifier instances from validated config.

    Args:
        config (RunnerConfig): Validated runner configuration.

    Returns:
        list[Notifier]: Active notifier instances derived from the config.
    """
    notifiers: list[Notifier] = [LoggingNotifier()]

    telegram_config = config.notifications.telegram
    if telegram_config is not None:
        notifiers.append(
            TelegramNotifier(
                bot_token=telegram_config.bot_token,
                chat_id=telegram_config.chat_id,
                message_thread_id=telegram_config.message_thread_id,
                disable_notification=telegram_config.disable_notification,
            )
        )

    return notifiers


def _render_summary(summary: RunSummary) -> None:
    """Render a run summary table using Rich.

    Args:
        summary (RunSummary): The completed run summary to display.
    """

    def _stats_value(last_stats: dict[str, object] | None, key: str) -> str:
        """Get a numeric stats value from last_stats with a safe fallback.

        Args:
            last_stats (dict[str, object] | None): rclone stats payload, or None if unavailable.
            key (str): Stats field name to retrieve.

        Returns:
            str: Integer string representation of the value, or ``"0"`` if absent or non-numeric.
        """
        if not last_stats:
            return "0"

        value = last_stats.get(key)
        if isinstance(value, bool):
            return "0"
        if isinstance(value, int | float):
            return str(int(value))
        return "0"

    console = Console()
    # Ensure a minimum width for the summary, especially for systemd logs
    if console.width < 120:
        console = Console(width=120)

    table = Table(title="rclone-sync-runner summary")
    table.add_column("Job", min_width=25)
    table.add_column("Transfers")
    table.add_column("Deletes")
    table.add_column("Checks")
    table.add_column("Bytes")
    table.add_column("Status")
    table.add_column("Ret Code")
    table.add_column("Duration(s)")
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
            f"mode={'dry-run' if summary.dry_run else 'live'} "
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
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Preview operations without making changes.",
    ),
) -> None:
    """Execute all configured jobs sequentially.

    Args:
        config (Path): Path to YAML config file.
        dry_run (bool): Preview operations without making changes.
    """
    setup_logging("INFO")

    try:
        parsed_config = load_config(config)
    except ConfigError as error:
        LOGGER.error("%s", error)
        raise typer.Exit(code=2) from error

    setup_logging(parsed_config.global_config.log_level)
    if dry_run:
        LOGGER.info("Running in dry-run mode; no changes will be applied.")

    try:
        summary, exit_code = run_jobs(config=parsed_config, notifiers=_build_notifiers(parsed_config), dry_run=dry_run)
    except Exception:
        LOGGER.exception("Unexpected runtime orchestration failure")
        raise typer.Exit(code=2) from None

    _render_summary(summary)
    raise typer.Exit(code=exit_code)


@TYPER_APP.command()
def discovery(
    folder_a: str = typer.Argument(..., help="rclone path for folder A (e.g. 'gdrive:Movies')."),
    folder_b: str = typer.Argument(..., help="rclone path to search for matching subfolders."),
    max_depth: int = typer.Option(
        3,
        "--max-depth",
        "-d",
        help="Maximum search depth inside Folder B (1 = immediate children only).",
        min=1,
    ),
    output: Path = typer.Option(
        Path("draft.yaml"),
        "--output",
        "-o",
        help="Output path for the generated draft YAML config file.",
    ),
    rclone_bin: str = typer.Option(
        "rclone",
        "--rclone-bin",
        help="Path or name of the rclone binary.",
    ),
) -> None:
    """Discover matching remote folder pairs and generate a draft sync config.

    Args:
        folder_a (str): rclone path for folder A (source root).
        folder_b (str): rclone path to search for matching subfolders.
        max_depth (int): Maximum search depth inside folder B.
        output (Path): Output path for the generated draft YAML config file.
        rclone_bin (str): Path or name of the rclone binary.
    """
    console = Console()
    console.print(f"[bold]Discovering folder pairs...[/bold]  (max depth: {max_depth})")
    console.print(f"  Folder A: {folder_a}")
    console.print(f"  Folder B: {folder_b}\n")

    try:
        folder_a_items = list_rclone_dirs(rclone_bin, folder_a, recursive=False, max_depth=1)
        folder_b_items = list_rclone_dirs(rclone_bin, folder_b, recursive=True, max_depth=max_depth)
    except RuntimeError as error:
        console.print(f"[bold red]Error:[/bold red] {error}")
        raise typer.Exit(code=1) from error

    if not folder_a_items:
        console.print("[yellow]No subdirectories found in Folder A. No config file written.[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"Found [bold]{len(folder_a_items)}[/bold] subdirectories in Folder A.\n")

    jobs = match_folder_pairs(folder_a_items, folder_b_items, folder_a, folder_b, console)

    if not jobs:
        console.print("\n[yellow]No matching pairs discovered. No config file written.[/yellow]")
        raise typer.Exit(code=0)

    config = build_runner_config(jobs)
    yaml_text = render_config_yaml(config)

    output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(yaml_text, encoding="utf-8")

    console.print(f"\n[bold green]Config written:[/bold green] {output}  ({len(jobs)} pair(s))")


def main() -> None:
    """Console script wrapper."""
    TYPER_APP()


if __name__ == "__main__":
    main()
