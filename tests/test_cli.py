"""Tests for CLI helper behavior."""

from __future__ import annotations

from rclone_sync_runner.cli import _build_notifiers, _format_ongoing_progress, _format_finished_progress
from rclone_sync_runner.models import RunnerConfig
from rclone_sync_runner.notifiers.logging_notifier import LoggingNotifier
from rclone_sync_runner.notifiers.telegram_notifier import TelegramNotifier

# Realistic rclone stats payloads used across progress formatter tests.
_ONGOING_STATS = {
    "bytes": 754810880,
    "checks": 206,
    "deletedDirs": 0,
    "deletes": 0,
    "elapsedTime": 30.000040914,
    "errors": 0,
    "eta": 581,
    "fatalError": False,
    "speed": 25226284.616487354,
    "totalBytes": 15418655467,
    "totalChecks": 206,
    "totalTransfers": 36,
    "transferring": [
        {"bytes": 226426880, "name": "file1.mp4", "percentage": 29, "size": 755066003},
        {"bytes": 124977152, "name": "file2.mp4", "percentage": 6, "size": 2010023304},
    ],
    "transfers": 0,
}

_FINISHED_STATS = {
    "bytes": 0,
    "checks": 18,
    "deletedDirs": 0,
    "deletes": 3,
    "elapsedTime": 0.563213769,
    "errors": 0,
    "eta": None,
    "fatalError": False,
    "speed": 0,
    "totalBytes": 0,
    "totalChecks": 18,
    "totalTransfers": 0,
    "transfers": 0,
}


class TestFormatOngoingProgress:
    def test_contains_job_name_with_cyan_markup(self) -> None:
        result = _format_ongoing_progress("my-job", _ONGOING_STATS, 2)
        assert "[cyan]my-job[/cyan]" in result

    def test_contains_active_count(self) -> None:
        result = _format_ongoing_progress("my-job", _ONGOING_STATS, 2)
        assert "active=2" in result

    def test_contains_percentage(self) -> None:
        result = _format_ongoing_progress("my-job", _ONGOING_STATS, 2)
        # 754810880 / 15418655467 ≈ 4%
        assert "(4%)" in result

    def test_contains_speed(self) -> None:
        result = _format_ongoing_progress("my-job", _ONGOING_STATS, 2)
        assert "speed=" in result
        assert "/s" in result

    def test_contains_eta(self) -> None:
        result = _format_ongoing_progress("my-job", _ONGOING_STATS, 2)
        assert "eta=581s" in result

    def test_unknown_speed_shows_question_mark(self) -> None:
        stats = {**_ONGOING_STATS, "speed": None}
        result = _format_ongoing_progress("my-job", stats, 1)
        assert "speed=?/s" in result

    def test_unknown_eta_shows_question_mark(self) -> None:
        stats = {**_ONGOING_STATS, "eta": None}
        result = _format_ongoing_progress("my-job", stats, 1)
        assert "eta=?" in result

    def test_zero_total_bytes_shows_zero_percent(self) -> None:
        stats = {**_ONGOING_STATS, "totalBytes": 0, "bytes": 0}
        result = _format_ongoing_progress("my-job", stats, 1)
        assert "(0%)" in result


class TestFormatFinishedProgress:
    def test_contains_job_name_with_green_markup(self) -> None:
        result = _format_finished_progress("my-job", _FINISHED_STATS)
        assert "[green]my-job[/green]" in result

    def test_contains_elapsed_time(self) -> None:
        result = _format_finished_progress("my-job", _FINISHED_STATS)
        assert "elapsed=0.6s" in result

    def test_contains_deletes(self) -> None:
        result = _format_finished_progress("my-job", _FINISHED_STATS)
        assert "deletes=3" in result

    def test_contains_checks(self) -> None:
        result = _format_finished_progress("my-job", _FINISHED_STATS)
        assert "checks=18" in result

    def test_contains_errors(self) -> None:
        result = _format_finished_progress("my-job", _FINISHED_STATS)
        assert "errors=0" in result

    def test_missing_elapsed_time_shows_question_mark(self) -> None:
        stats = {k: v for k, v in _FINISHED_STATS.items() if k != "elapsedTime"}
        result = _format_finished_progress("my-job", stats)
        assert "elapsed=?" in result


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
