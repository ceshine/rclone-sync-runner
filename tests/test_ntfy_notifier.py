"""Tests for ntfy notifier behavior."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from rclone_sync_runner.models import RunSummary, JobRunResult
from rclone_sync_runner.notifiers.ntfy_notifier import (
    NtfyNotifier,
    MAX_BODY_BYTES,
    TRUNCATION_MARKER,
    MAX_FAILED_JOB_NAMES,
    MAX_LOGGED_RESPONSE_CHARS,
)


def _job_result(
    job_name: str,
    succeeded: bool,
    *,
    last_stats: dict[str, int | float] | None,
) -> JobRunResult:
    now = datetime.now(UTC)
    return JobRunResult(
        job_name=job_name,
        source="/src/docs",
        destination="remote:docs",
        started_at=now,
        ended_at=now,
        duration_seconds=2.5,
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


def _capturing_transport(captured: list[httpx.Request], status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status_code, json={"id": "abc123"})

    return httpx.MockTransport(handler)


def test_ntfy_notifier_sends_expected_request() -> None:
    captured: list[httpx.Request] = []
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
                last_stats={"bytes": 100, "transfers": 1, "deletes": 0, "checks": 4, "elapsedTime": 2.5},
            ),
            _job_result(
                "photos",
                succeeded=True,
                last_stats={"bytes": 3000, "transfers": 5, "deletes": 2, "checks": 6, "elapsedTime": 3.2},
            ),
        ],
    )

    notifier = NtfyNotifier(
        server_url="https://ntfy.example.com/",
        topic="rclone-sync",
        token="tk_secret",
        priority=4,
        transport=_capturing_transport(captured),
    )
    notifier.on_run_finished(summary)

    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert str(request.url) == "https://ntfy.example.com/rclone-sync"
    assert request.headers["Title"] == "rclone-sync-runner FAILED"
    assert request.headers["Priority"] == "4"
    assert request.headers["Tags"] == "x"
    assert request.headers["Markdown"] == "yes"
    assert request.headers["Authorization"] == "Bearer tk_secret"
    assert request.content.decode("utf-8") == (
        "- config name: daily-home-backup\n"
        "- mode: live\n"
        "- successful jobs: 1/2\n"
        "- failed jobs: docs\n"
        "- run duration: 5.40s\n\n"
        "**Aggregated job stats**\n\n"
        "- transfers: 6\n"
        "- deletes: 2\n"
        "- checks: 10\n"
        "- bytes: 3,100\n"
        "- duration seconds: 5.70"
    )


def test_ntfy_notifier_omits_authorization_without_token() -> None:
    captured: list[httpx.Request] = []

    notifier = NtfyNotifier(
        server_url="https://ntfy.example.com",
        topic="rclone-sync",
        transport=_capturing_transport(captured),
    )
    notifier.on_run_finished(_summary())

    request = captured[0]
    assert "Authorization" not in request.headers
    assert request.headers["Title"] == "rclone-sync-runner SUCCEEDED"
    assert request.headers["Tags"] == "white_check_mark"
    assert request.headers["Priority"] == "3"
    assert request.content.decode("utf-8").startswith("- mode: live\n")
    assert "- failed jobs: none\n" in request.content.decode("utf-8")


def test_ntfy_notifier_logs_http_errors(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(403, json={"code": 40301, "http": 403, "error": "forbidden"})

    notifier = NtfyNotifier(
        server_url="https://ntfy.example.com",
        topic="rclone-sync",
        token="tk_secret",
        transport=httpx.MockTransport(handler),
    )
    notifier.on_run_finished(_summary(failed=True))

    assert "ntfy notification failed: HTTP 403" in caplog.text
    assert "forbidden" in caplog.text
    assert "tk_secret" not in caplog.text


def test_ntfy_notifier_logs_network_errors(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    notifier = NtfyNotifier(
        server_url="https://ntfy.example.com",
        topic="rclone-sync",
        transport=httpx.MockTransport(handler),
    )
    notifier.on_run_finished(_summary())

    assert "ntfy notification failed: network down" in caplog.text


def _failing_transport(error_message: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.LocalProtocolError(error_message.format(authorization=request.headers["Authorization"]))

    return httpx.MockTransport(handler)


def test_ntfy_notifier_logs_redirects_as_failures(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(301, headers={"Location": "https://ntfy.example.com/rclone-sync"})

    notifier = NtfyNotifier(
        server_url="http://ntfy.example.com",
        topic="rclone-sync",
        transport=httpx.MockTransport(handler),
    )
    notifier.on_run_finished(_summary())

    assert "ntfy notification failed: HTTP 301" in caplog.text


def test_ntfy_notifier_limits_logged_response_text(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(502, text="<html>" + "x" * 5000 + "</html>")

    notifier = NtfyNotifier(
        server_url="https://ntfy.example.com",
        topic="rclone-sync",
        transport=httpx.MockTransport(handler),
    )
    notifier.on_run_finished(_summary())

    assert "ntfy notification failed: HTTP 502" in caplog.text
    assert "x" * MAX_LOGGED_RESPONSE_CHARS not in caplog.text
    assert "</html>" not in caplog.text


def test_ntfy_notifier_redacts_token_in_error_messages(caplog) -> None:
    notifier = NtfyNotifier(
        server_url="https://ntfy.example.com",
        topic="rclone-sync",
        token="tk_secret",
        transport=_failing_transport("Illegal header value {authorization!r}"),
    )
    notifier.on_run_finished(_summary())

    assert "ntfy notification failed: Illegal header value" in caplog.text
    assert "<redacted token>" in caplog.text
    assert "tk_secret" not in caplog.text


def test_ntfy_notifier_handles_non_ascii_token(caplog) -> None:
    captured: list[httpx.Request] = []

    # Config validation rejects this token; the notifier must still not raise when it is built directly.
    notifier = NtfyNotifier(
        server_url="https://ntfy.example.com",
        topic="rclone-sync",
        token="tk_sécret",
        transport=_capturing_transport(captured),
    )
    notifier.on_run_finished(_summary())

    assert captured == []
    assert "ntfy notification failed" in caplog.text
    assert "tk_sécret" not in caplog.text


def test_ntfy_notifier_handles_invalid_server_url(caplog) -> None:
    captured: list[httpx.Request] = []

    notifier = NtfyNotifier(
        server_url="https://[::1",
        topic="rclone-sync",
        transport=_capturing_transport(captured),
    )
    notifier.on_run_finished(_summary())

    assert captured == []
    assert "ntfy notification failed" in caplog.text


def test_ntfy_notifier_limits_failed_job_names() -> None:
    results = [_job_result(f"données-{index}", succeeded=False, last_stats=None) for index in range(600)]
    summary = RunSummary(
        global_name=None,
        total_jobs=len(results),
        successful_jobs=0,
        failed_jobs=len(results),
        duration_seconds=1.0,
        dry_run=False,
        results=results,
    )

    text = NtfyNotifier._build_message(summary)

    assert f"données-{MAX_FAILED_JOB_NAMES - 1}, and {600 - MAX_FAILED_JOB_NAMES} more\n" in text
    assert f"données-{MAX_FAILED_JOB_NAMES}," not in text
    assert "- bytes: 0" in text
    assert len(text.encode("utf-8")) <= MAX_BODY_BYTES


def test_ntfy_notifier_truncates_long_messages() -> None:
    captured: list[httpx.Request] = []
    # A long multi-byte config name produces a body far above the ntfy limit.
    summary = _summary().model_copy(update={"global_name": "é" * 5000})

    notifier = NtfyNotifier(
        server_url="https://ntfy.example.com",
        topic="rclone-sync",
        transport=_capturing_transport(captured),
    )
    notifier.on_run_finished(summary)

    content = captured[0].content
    assert len(content) <= MAX_BODY_BYTES
    assert content.decode("utf-8").endswith(TRUNCATION_MARKER)


def test_ntfy_notifier_truncate_cuts_at_character_boundary() -> None:
    budget = MAX_BODY_BYTES - len(TRUNCATION_MARKER.encode("utf-8"))
    # The two-byte "é" starts at the last byte of the budget, so a plain byte cut would split it.
    text = "a" * (budget - 1) + "é" * 10

    truncated = NtfyNotifier._truncate(text)

    encoded = truncated.encode("utf-8")
    assert len(encoded) <= MAX_BODY_BYTES
    assert truncated == "a" * (budget - 1) + TRUNCATION_MARKER


def test_ntfy_notifier_truncate_keeps_text_at_limit() -> None:
    text = "a" * MAX_BODY_BYTES

    assert NtfyNotifier._truncate(text) == text


def test_ntfy_notifier_truncate_shortens_text_one_byte_over_limit() -> None:
    truncated = NtfyNotifier._truncate("a" * (MAX_BODY_BYTES + 1))

    assert len(truncated.encode("utf-8")) == MAX_BODY_BYTES
    assert truncated.endswith(TRUNCATION_MARKER)


def test_ntfy_notifier_escapes_markdown_values() -> None:
    summary = RunSummary(
        global_name="home_backup*v1",
        total_jobs=1,
        successful_jobs=0,
        failed_jobs=1,
        duration_seconds=1.0,
        dry_run=False,
        results=[_job_result("docs_[backup]", succeeded=False, last_stats=None)],
    )

    text = NtfyNotifier._build_message(summary)

    assert "home\\_backup\\*v1" in text
    assert "docs\\_\\[backup\\]" in text


def test_ntfy_notifier_keeps_common_punctuation_readable() -> None:
    summary = _summary(failed=True).model_copy(update={"global_name": "home-backup.v1 (daily)"})

    text = NtfyNotifier._build_message(summary)

    assert "- config name: home-backup.v1 (daily)\n" in text
