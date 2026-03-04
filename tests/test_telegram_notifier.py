"""Tests for Telegram notifier behavior."""

from __future__ import annotations

from datetime import UTC, datetime

from telegram.error import TelegramError

from rclone_sync_runner.models import JobRunResult, RunSummary
from rclone_sync_runner.notifiers.telegram_notifier import TelegramNotifier


def _job_result(
    job_name: str,
    succeeded: bool,
    *,
    duration_seconds: float,
    last_stats: dict[str, int | float] | None,
) -> JobRunResult:
    now = datetime.now(UTC)
    return JobRunResult(
        job_name=job_name,
        source="/src/docs",
        destination="remote:docs",
        started_at=now,
        ended_at=now,
        duration_seconds=duration_seconds,
        return_code=0 if succeeded else 1,
        succeeded=succeeded,
        dry_run=False,
        error_count=0 if succeeded else 1,
        error_samples=[] if succeeded else ["failed"],
        last_stats=last_stats,
    )


def _summary(failed: bool = False) -> RunSummary:
    result = _job_result(
        "docs",
        succeeded=not failed,
        duration_seconds=2.5,
        last_stats={"bytes": 100, "transfers": 1, "deletes": 0, "checks": 3, "elapsedTime": 2.5},
    )
    return RunSummary(
        global_name=None,
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

    summary = RunSummary(
        global_name="daily-home-backup",
        total_jobs=2,
        successful_jobs=1,
        failed_jobs=1,
        duration_seconds=5.4,
        dry_run=False,
        results=[
            _job_result(
                "docs",
                succeeded=False,
                duration_seconds=2.5,
                last_stats={"bytes": 100, "transfers": 1, "deletes": 0, "checks": 4, "elapsedTime": 2.5},
            ),
            _job_result(
                "photos",
                succeeded=True,
                duration_seconds=2.9,
                last_stats={"bytes": 300, "transfers": 5, "deletes": 2, "checks": 6, "elapsedTime": 3.2},
            ),
        ],
    )

    notifier = TelegramNotifier(
        bot_token="12345:ABCDEF",
        chat_id="-10012345",
        message_thread_id=42,
        disable_notification=True,
    )
    notifier.on_run_finished(summary)

    assert captured["token"] == "12345:ABCDEF"
    assert captured["payload"] == {
        "chat_id": "-10012345",
        "text": (
            "*rclone-sync-runner FAILED*\n\n"
            "- config name: daily-home-backup\n"
            "- mode: live\n"
            "- successful jobs: 1/2\n"
            "- failed jobs: docs\n"
            "- run duration: 5.40s\n\n"
            "*Aggregated job stats*\n\n"
            "- transfers: 6\n"
            "- deletes: 2\n"
            "- checks: 10\n"
            "- bytes: 400\n"
            "- duration seconds: 5.70"
        ),
        "parse_mode": "Markdown",
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


def test_telegram_notifier_escapes_markdown_values() -> None:
    summary = RunSummary(
        global_name="home_backup_v1",
        total_jobs=1,
        successful_jobs=0,
        failed_jobs=1,
        duration_seconds=1.0,
        dry_run=False,
        results=[
            _job_result(
                "docs_backup_v1",
                succeeded=False,
                duration_seconds=1.0,
                last_stats={"bytes": 1, "transfers": 1, "deletes": 0, "checks": 1, "elapsedTime": 1.0},
            )
        ],
    )

    text = TelegramNotifier._build_message(summary)
    assert "home\\_backup\\_v1" in text
    assert "docs\\_backup\\_v1" in text
