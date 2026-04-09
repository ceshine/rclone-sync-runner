"""Telegram notifier for run summary delivery."""

from __future__ import annotations

import asyncio
import logging
from typing import final
from string import Template

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.helpers import escape_markdown

from rclone_sync_runner.models import RunSummary

LOGGER = logging.getLogger(__name__)


@final
class TelegramNotifier:
    """Send run completion summaries to Telegram."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        message_thread_id: int | None = None,
        disable_notification: bool = False,
        timeout_seconds: float = 10.0,
    ) -> None:
        """Initialize the Telegram notifier.

        Args:
            bot_token (str): Telegram bot token.
            chat_id (str): Target chat ID.
            message_thread_id (int | None): Optional thread/topic identifier.
            disable_notification (bool): Send message silently when true.
            timeout_seconds (float): Bot API request timeout in seconds.
        """
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._message_thread_id = message_thread_id
        self._disable_notification = disable_notification
        self._timeout_seconds = timeout_seconds

    def on_run_finished(self, summary: RunSummary) -> None:
        """Send a run summary message to Telegram.

        Args:
            summary (RunSummary): Run summary object.
        """
        try:
            asyncio.run(
                self._send_message(
                    text=self._build_message(summary),
                    message_thread_id=self._message_thread_id,
                )
            )
        except TelegramError as error:
            LOGGER.warning("Telegram notification failed: %s", error)
        except OSError as error:
            LOGGER.warning("Telegram notification failed: %s", error)

    async def _send_message(self, text: str, message_thread_id: int | None) -> None:
        """Send a message through python-telegram-bot.

        Args:
            text (str): Markdown-formatted message body.
            message_thread_id (int | None): Thread or topic ID, or None for the main chat.
        """
        async with Bot(token=self._bot_token) as bot:
            _ = await bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                message_thread_id=message_thread_id,
                disable_notification=self._disable_notification,
                read_timeout=self._timeout_seconds,
                write_timeout=self._timeout_seconds,
                connect_timeout=self._timeout_seconds,
                pool_timeout=self._timeout_seconds,
            )

    @staticmethod
    def _stats_number(last_stats: dict[str, object] | None, key: str) -> float:
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

    @classmethod
    def _aggregated_totals(cls, summary: RunSummary) -> dict[str, float]:
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
            totals["transfers"] += cls._stats_number(result.last_stats, "transfers")
            totals["deletes"] += cls._stats_number(result.last_stats, "deletes")
            totals["checks"] += cls._stats_number(result.last_stats, "checks")
            totals["bytes"] += cls._stats_number(result.last_stats, "bytes")
            totals["duration_seconds"] += cls._stats_number(result.last_stats, "elapsedTime")

        return totals

    @staticmethod
    def _markdown_text(value: str) -> str:
        """Escape user-provided data for Telegram Markdown parsing.

        Args:
            value (str): Raw string to escape.

        Returns:
            str: Telegram Markdown v1-safe escaped string.
        """
        return escape_markdown(value, version=1)

    @classmethod
    def _build_message(cls, summary: RunSummary) -> str:
        """Build a markdown-formatted run summary message.

        Args:
            summary (RunSummary): The completed run summary to format.

        Returns:
            str: Telegram Markdown v1-formatted message string.
        """
        status = "SUCCEEDED" if summary.failed_jobs == 0 else "FAILED"
        mode = "dry-run" if summary.dry_run else "live"
        config_name_line = f"- config name: {cls._markdown_text(summary.global_name)}\n" if summary.global_name else ""
        failed_job_names = [result.job_name for result in summary.results if not result.succeeded]
        failed_jobs_markdown = (
            ", ".join(cls._markdown_text(job_name) for job_name in failed_job_names)
            if failed_job_names
            else cls._markdown_text("none")
        )
        aggregated = cls._aggregated_totals(summary)

        template = Template(
            (
                "*rclone-sync-runner $status*\n\n"
                "$runner_line"
                "- mode: $mode\n"
                "- successful jobs: $successful_jobs/$total_jobs\n"
                "- failed jobs: $failed_jobs\n"
                "- run duration: $run_duration\n\n"
                "*Aggregated job stats*\n\n"
                "- transfers: $transfers\n"
                "- deletes: $deletes\n"
                "- checks: $checks\n"
                "- bytes: $bytes\n"
                "- duration seconds: $duration_seconds"
            )
        )
        return template.substitute(
            status=cls._markdown_text(status),
            mode=cls._markdown_text(mode),
            runner_line=config_name_line,
            successful_jobs=cls._markdown_text(str(summary.successful_jobs)),
            total_jobs=cls._markdown_text(str(summary.total_jobs)),
            failed_jobs=failed_jobs_markdown,
            run_duration=cls._markdown_text(f"{summary.duration_seconds:.2f}s"),
            transfers=cls._markdown_text(str(int(aggregated["transfers"]))),
            deletes=cls._markdown_text(str(int(aggregated["deletes"]))),
            checks=cls._markdown_text(str(int(aggregated["checks"]))),
            bytes=cls._markdown_text(f"{int(aggregated['bytes']):,d}"),
            duration_seconds=cls._markdown_text(f"{aggregated['duration_seconds']:.2f}"),
        )
