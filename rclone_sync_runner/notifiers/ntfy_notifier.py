"""ntfy notifier for run summary delivery."""

from __future__ import annotations

import logging
from typing import final

import httpx

from rclone_sync_runner.models import RunSummary
from rclone_sync_runner.notifiers.summary import aggregate_job_stats

LOGGER = logging.getLogger(__name__)

# Without an attachment cache, ntfy rejects a body of 4,096 bytes or more, or a body that is not valid UTF-8.
MAX_BODY_BYTES = 4095
TRUNCATION_MARKER = "\n\n(truncated)"
# Keep the stats in the message when many jobs fail; the byte limit is only a safety net.
MAX_FAILED_JOB_NAMES = 20
MAX_LOGGED_RESPONSE_CHARS = 200
# Characters that start inline Markdown syntax. Other punctuation stays readable in clients without Markdown.
MARKDOWN_SPECIAL_CHARACTERS = frozenset("\\`*_[]<>~")


@final
class NtfyNotifier:
    """Send run completion summaries to an ntfy topic."""

    def __init__(
        self,
        server_url: str,
        topic: str,
        token: str | None = None,
        priority: int = 3,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialize the ntfy notifier.

        Args:
            server_url (str): Base URL of the ntfy server, for example ``https://ntfy.sh``.
            topic (str): Topic to publish to.
            token (str | None): Access token (``tk_...``), or None for topics that allow anonymous writes.
            priority (int): Message priority from 1 (min) to 5 (max).
            timeout_seconds (float): HTTP request timeout in seconds.
            transport (httpx.BaseTransport | None): Optional HTTP transport, used by tests to mock the server.
        """
        self._url = f"{server_url.rstrip('/')}/{topic}"
        self._token = token
        self._priority = priority
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def on_run_finished(self, summary: RunSummary) -> None:
        """Publish a run summary message to ntfy.

        Args:
            summary (RunSummary): Run summary object.
        """
        failed = summary.failed_jobs > 0
        # Header values must be ASCII, so user-provided names go in the body only.
        headers = {
            "Title": f"rclone-sync-runner {'FAILED' if failed else 'SUCCEEDED'}",
            "Priority": str(self._priority),
            "Tags": "x" if failed else "white_check_mark",
            "Markdown": "yes",
        }
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"

        body = self._truncate(self._build_message(summary))
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout_seconds) as client:
                response = client.post(self._url, content=body.encode("utf-8"), headers=headers)
                _ = response.raise_for_status()
        except httpx.HTTPStatusError as error:
            response_text = error.response.text.strip()[:MAX_LOGGED_RESPONSE_CHARS]
            LOGGER.warning(
                "ntfy notification failed: HTTP %s: %s", error.response.status_code, self._redact(response_text)
            )
        # InvalidURL and ValueError (for example UnicodeEncodeError for a non-ASCII header) come from bad settings.
        except (httpx.HTTPError, httpx.InvalidURL, ValueError) as error:
            LOGGER.warning("ntfy notification failed: %s", self._redact(str(error)))

    def _redact(self, text: str) -> str:
        """Remove the access token from text that goes to the logs.

        Some errors, for example an invalid header value, include the header in their message.

        Args:
            text (str): Text to log.

        Returns:
            str: The text with each occurrence of the token replaced.
        """
        if not self._token:
            return text
        return text.replace(self._token, "<redacted token>")

    @staticmethod
    def _markdown_text(value: str) -> str:
        """Escape user-provided data for Markdown rendering.

        Args:
            value (str): Raw string to escape.

        Returns:
            str: The string with a backslash before each character in ``MARKDOWN_SPECIAL_CHARACTERS``.
        """
        return "".join(f"\\{char}" if char in MARKDOWN_SPECIAL_CHARACTERS else char for char in value)

    @staticmethod
    def _truncate(text: str) -> str:
        """Shorten a message body to the size that ntfy accepts.

        Args:
            text (str): Message body.

        Returns:
            str: The original text if it fits in ``MAX_BODY_BYTES`` UTF-8 bytes. Otherwise, the text cut at a
                character boundary, followed by ``TRUNCATION_MARKER``, with a total size of at most
                ``MAX_BODY_BYTES``.
        """
        encoded = text.encode("utf-8")
        if len(encoded) <= MAX_BODY_BYTES:
            return text

        budget = MAX_BODY_BYTES - len(TRUNCATION_MARKER.encode("utf-8"))
        # "ignore" drops a multi-byte character that the cut splits.
        return encoded[:budget].decode("utf-8", "ignore") + TRUNCATION_MARKER

    @classmethod
    def _build_message(cls, summary: RunSummary) -> str:
        """Build a markdown-formatted run summary message.

        Args:
            summary (RunSummary): The completed run summary to format.

        Returns:
            str: Markdown message body. The run status is in the title header, not in the body.
        """
        mode = "dry-run" if summary.dry_run else "live"
        failed_job_names = [result.job_name for result in summary.results if not result.succeeded]
        failed_jobs = ", ".join(cls._markdown_text(name) for name in failed_job_names[:MAX_FAILED_JOB_NAMES])
        if not failed_job_names:
            failed_jobs = "none"
        elif len(failed_job_names) > MAX_FAILED_JOB_NAMES:
            failed_jobs += f", and {len(failed_job_names) - MAX_FAILED_JOB_NAMES} more"
        aggregated = aggregate_job_stats(summary)

        lines: list[str] = []
        if summary.global_name:
            lines.append(f"- config name: {cls._markdown_text(summary.global_name)}")
        lines.extend(
            [
                f"- mode: {mode}",
                f"- successful jobs: {summary.successful_jobs}/{summary.total_jobs}",
                f"- failed jobs: {failed_jobs}",
                f"- run duration: {summary.duration_seconds:.2f}s",
                "",
                "**Aggregated job stats**",
                "",
                f"- transfers: {int(aggregated['transfers'])}",
                f"- deletes: {int(aggregated['deletes'])}",
                f"- checks: {int(aggregated['checks'])}",
                f"- bytes: {int(aggregated['bytes']):,d}",
                f"- duration seconds: {aggregated['duration_seconds']:.2f}",
            ]
        )
        return "\n".join(lines)
