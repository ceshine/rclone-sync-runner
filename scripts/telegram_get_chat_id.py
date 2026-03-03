"""Print chat metadata for the latest message received by a Telegram bot."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from telegram import Bot, Message, Update
from telegram.error import TelegramError

from rclone_sync_runner.models import RunnerConfig
from rclone_sync_runner.config import ConfigError, load_config

TYPER_APP = typer.Typer(help="Inspect latest Telegram bot message to discover chat ID.")
CONSOLE = Console()


class ScriptError(RuntimeError):
    """Raised when script input or Telegram data is invalid."""


@dataclass(frozen=True)
class LatestMessageInfo:
    """Display-ready metadata for a Telegram message."""

    sender_info: str
    chat_id: str
    timestamp_utc: str


def _load_bot_token(config: RunnerConfig) -> str:
    """Extract Telegram bot token from validated config."""
    telegram_config = config.notifications.telegram
    if telegram_config is None:
        raise ScriptError("Config must contain notifications.telegram settings.")
    return telegram_config.bot_token


def _extract_message(update: Update) -> Message | None:
    """Extract a message-like payload from an update."""
    return update.message or update.edited_message or update.channel_post or update.edited_channel_post


def _format_sender_info(message: Message) -> str:
    """Build a readable sender string."""
    if message.from_user is not None:
        from_user = message.from_user
        name = " ".join(part for part in [from_user.first_name, from_user.last_name] if part).strip()
        username = f"@{from_user.username}" if from_user.username else "-"
        display_name = name or from_user.full_name
        return f"user_id={from_user.id}, name={display_name}, username={username}"

    if message.sender_chat is not None:
        sender_chat = message.sender_chat
        title = sender_chat.title or sender_chat.full_name or sender_chat.username or "unknown"
        username = f"@{sender_chat.username}" if sender_chat.username else "-"
        return f"chat_sender_id={sender_chat.id}, title={title}, username={username}"

    return "unknown sender"


def _to_latest_message_info(message: Message) -> LatestMessageInfo:
    """Convert Telegram Message into display-friendly metadata."""
    timestamp_utc = message.date.astimezone(timezone.utc).isoformat()
    return LatestMessageInfo(
        sender_info=_format_sender_info(message),
        chat_id=str(message.chat.id),
        timestamp_utc=timestamp_utc,
    )


async def _fetch_latest_message_info(bot_token: str) -> LatestMessageInfo:
    """Fetch latest message metadata via getUpdates."""
    async with Bot(token=bot_token) as bot:
        updates = await bot.get_updates(
            limit=5,
            timeout=3,
            allowed_updates=["message", "edited_message", "channel_post", "edited_channel_post"],
        )

    latest_message: Message | None = None
    latest_update_id = -1
    for update in updates:
        message = _extract_message(update)
        if message is None:
            continue
        if latest_message is None:
            latest_message = message
            latest_update_id = update.update_id
            continue
        if message.date > latest_message.date or (
            message.date == latest_message.date and update.update_id > latest_update_id
        ):
            latest_message = message
            latest_update_id = update.update_id

    if latest_message is None:
        raise ScriptError(
            "No message updates were found for this bot. Send a message to the bot, then run this script again."
        )

    return _to_latest_message_info(latest_message)


def _render_message_info(message_info: LatestMessageInfo) -> None:
    """Render latest message metadata in a small table."""
    table = Table(title="Latest Telegram Message")
    table.add_column("Field", style="bold cyan")
    table.add_column("Value", style="white")
    table.add_row("Sender", message_info.sender_info)
    table.add_row("Chat ID", message_info.chat_id)
    table.add_row("Timestamp (UTC)", message_info.timestamp_utc)
    CONSOLE.print(table)


@TYPER_APP.command()
def main(
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
    """Read bot token from config and print metadata of the latest bot message."""
    try:
        runner_config = load_config(config)
        bot_token = _load_bot_token(runner_config)
        latest_message_info = asyncio.run(_fetch_latest_message_info(bot_token))
    except (ConfigError, ScriptError, TelegramError, OSError) as error:
        CONSOLE.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(code=2) from error

    _render_message_info(latest_message_info)


if __name__ == "__main__":
    TYPER_APP()
