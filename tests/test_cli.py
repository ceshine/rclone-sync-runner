"""Tests for CLI helper behavior."""

from __future__ import annotations

from rclone_sync_runner.cli import _build_notifiers
from rclone_sync_runner.models import RunnerConfig
from rclone_sync_runner.notifiers.logging_notifier import LoggingNotifier
from rclone_sync_runner.notifiers.telegram_notifier import TelegramNotifier


def test_build_notifiers_includes_logging_notifier_by_default() -> None:
    config = RunnerConfig.model_validate(
        {
            "version": 1,
            "global": {"log_level": "INFO"},
            "jobs": [{"name": "docs", "source": "/src", "destination": "remote:dst"}],
        }
    )

    notifiers = _build_notifiers(config)

    assert len(notifiers) == 1
    assert isinstance(notifiers[0], LoggingNotifier)


def test_build_notifiers_includes_telegram_notifier_when_configured() -> None:
    config = RunnerConfig.model_validate(
        {
            "version": 1,
            "global": {"log_level": "INFO"},
            "jobs": [{"name": "docs", "source": "/src", "destination": "remote:dst"}],
            "notifications": {
                "telegram": {
                    "bot_token": "12345:ABCDEF",
                    "chat_id": "-10012345",
                }
            },
        }
    )

    notifiers = _build_notifiers(config)

    assert len(notifiers) == 2
    assert isinstance(notifiers[0], LoggingNotifier)
    assert isinstance(notifiers[1], TelegramNotifier)
