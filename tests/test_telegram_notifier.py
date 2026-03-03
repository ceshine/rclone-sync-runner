"""Tests for Telegram notifier behavior."""

from __future__ import annotations

from datetime import UTC, datetime

from telegram.error import TelegramError

from rclone_sync_runner.models import JobRunResult, RunSummary
from rclone_sync_runner.notifiers.telegram_notifier import TelegramNotifier


def _summary(failed: bool = False) -> RunSummary:
    now = datetime.now(UTC)
    result = JobRunResult(
        job_name="docs",
        source="/src/docs",
        destination="remote:docs",
        started_at=now,
        ended_at=now,
        duration_seconds=2.5,
        return_code=1 if failed else 0,
        succeeded=not failed,
        dry_run=False,
        error_count=1 if failed else 0,
        error_samples=["failed"] if failed else [],
        last_stats={"bytes": 100},
    )
    return RunSummary(
        total_jobs=1,
        successful_jobs=0 if failed else 1,
        failed_jobs=1 if failed else 0,
        duration_seconds=2.5,
        dry_run=False,
        results=[result],
    )


def test_telegram_notifier_sends_expected_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeBot:
        def __init__(self, token: str) -> None:
            captured["token"] = token

        async def __aenter__(self) -> _FakeBot:
            return self

        async def __aexit__(self, exc_type, exc_value, traceback) -> None:  # noqa: ANN001
            del exc_type, exc_value, traceback

        async def send_message(self, **kwargs: object) -> None:
            captured["payload"] = kwargs

    monkeypatch.setattr("rclone_sync_runner.notifiers.telegram_notifier.Bot", _FakeBot)

    notifier = TelegramNotifier(
        bot_token="12345:ABCDEF",
        chat_id="-10012345",
        message_thread_id=42,
        disable_notification=True,
    )
    notifier.on_run_finished(_summary(failed=True))

    assert captured["token"] == "12345:ABCDEF"
    assert captured["payload"] == {
        "chat_id": "-10012345",
        "text": (
            "rclone-sync-runner FAILED\nmode=live\ntotal=1\nsucceeded=0\nfailed=1\nduration=2.50s\nfailed_jobs=docs"
        ),
        "message_thread_id": 42,
        "disable_notification": True,
        "read_timeout": 10.0,
        "write_timeout": 10.0,
        "connect_timeout": 10.0,
        "pool_timeout": 10.0,
    }


def test_telegram_notifier_handles_network_errors(monkeypatch, caplog) -> None:
    class _FailingBot:
        def __init__(self, token: str) -> None:
            del token

        async def __aenter__(self) -> _FailingBot:
            return self

        async def __aexit__(self, exc_type, exc_value, traceback) -> None:  # noqa: ANN001
            del exc_type, exc_value, traceback

        async def send_message(self, **kwargs: object) -> None:
            del kwargs
            raise TelegramError("network down")

    monkeypatch.setattr("rclone_sync_runner.notifiers.telegram_notifier.Bot", _FailingBot)

    notifier = TelegramNotifier(bot_token="12345:ABCDEF", chat_id="-10012345")
    notifier.on_run_finished(_summary())

    assert "Telegram notification failed" in caplog.text
