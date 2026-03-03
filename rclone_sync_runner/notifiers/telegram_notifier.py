"""Telegram notifier for run summary delivery."""

from __future__ import annotations

import asyncio
import logging

from telegram import Bot
from telegram.error import TelegramError

from rclone_sync_runner.models import RunSummary

LOGGER = logging.getLogger(__name__)


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
            bot_token: Telegram bot token.
            chat_id: Target chat ID.
            message_thread_id: Optional thread/topic identifier.
            disable_notification: Send message silently when true.
            timeout_seconds: Bot API request timeout in seconds.
        """
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._message_thread_id = message_thread_id
        self._disable_notification = disable_notification
        self._timeout_seconds = timeout_seconds

    def on_run_finished(self, summary: RunSummary) -> None:
        """Send a run summary message to Telegram.

        Args:
            summary: Run summary object.
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
        """Send a message through python-telegram-bot."""
        async with Bot(token=self._bot_token) as bot:
            await bot.send_message(
                chat_id=self._chat_id,
                text=text,
                message_thread_id=message_thread_id,
                disable_notification=self._disable_notification,
                read_timeout=self._timeout_seconds,
                write_timeout=self._timeout_seconds,
                connect_timeout=self._timeout_seconds,
                pool_timeout=self._timeout_seconds,
            )

    @staticmethod
    def _build_message(summary: RunSummary) -> str:
        """Build a concise human-readable summary message."""
        status = "SUCCEEDED" if summary.failed_jobs == 0 else "FAILED"
        mode = "dry-run" if summary.dry_run else "live"
        lines = [
            f"rclone-sync-runner {status}",
            f"mode={mode}",
            f"total={summary.total_jobs}",
            f"succeeded={summary.successful_jobs}",
            f"failed={summary.failed_jobs}",
            f"duration={summary.duration_seconds:.2f}s",
        ]

        failed_job_names = [result.job_name for result in summary.results if not result.succeeded]
        if failed_job_names:
            lines.append(f"failed_jobs={', '.join(failed_job_names)}")

        return "\n".join(lines)
