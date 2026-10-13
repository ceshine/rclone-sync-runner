"""Typed models for configuration and runtime results."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import httpx
from pydantic import Field, BaseModel, ConfigDict, field_validator, model_validator


class GlobalConfig(BaseModel):
    """Global settings that apply to all sync jobs."""

    name: str | None = None
    rclone_bin: str = "rclone"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    continue_on_error: bool = True
    extra_args: list[str] = Field(default_factory=list)


class SyncJob(BaseModel):
    """Single rclone sync job definition."""

    name: str
    source: str
    destination: str
    extra_args: list[str] | None = None


class TelegramNotificationConfig(BaseModel):
    """Telegram notification channel settings."""

    bot_token: str = Field(min_length=1)
    chat_id: str = Field(min_length=1)
    message_thread_id: int | None = None
    disable_notification: bool = False


class NtfyNotificationConfig(BaseModel):
    """ntfy notification channel settings."""

    server_url: str
    # Same character set and length limit that the ntfy server accepts for topic names.
    topic: str = Field(pattern=r"^[-_A-Za-z0-9]{1,64}$")
    # The format of tokens that ntfy issues. It keeps whitespace and non-ASCII text out of the HTTP header.
    token: str | None = Field(default=None, pattern=r"^tk_[A-Za-z0-9]+$")
    priority: int = Field(default=3, ge=1, le=5)

    @field_validator("server_url")
    @classmethod
    def validate_server_url(cls, value: str) -> str:
        """Check that the server URL can be used as the base of a topic URL.

        Args:
            value (str): Configured server URL.

        Returns:
            str: The unchanged server URL.

        Raises:
            ValueError: If the URL cannot be parsed, is not http(s), has no host, or has a query or fragment.
        """
        try:
            url = httpx.URL(value)
        except httpx.InvalidURL as error:
            raise ValueError(f"server_url is not a valid URL: {error}") from error
        if url.scheme not in ("http", "https") or not url.host:
            raise ValueError("server_url must be an http or https URL with a host")
        # Also check the raw text: an empty query or fragment (a trailing ? or #) parses as empty.
        if url.query or url.fragment or "?" in value or "#" in value:
            raise ValueError("server_url must not contain a query or a fragment")
        return value

    @model_validator(mode="after")
    def require_https_with_token(self) -> NtfyNotificationConfig:
        """Reject a token that would be sent over plain HTTP.

        Returns:
            NtfyNotificationConfig: The validated config.

        Raises:
            ValueError: If a token is set and the server URL does not use https.
        """
        if self.token is not None and httpx.URL(self.server_url).scheme != "https":
            raise ValueError("server_url must use https when a token is set")
        return self


class NotificationChannelsConfig(BaseModel):
    """Optional notification channel configuration."""

    telegram: TelegramNotificationConfig | None = None
    ntfy: NtfyNotificationConfig | None = None


class RunnerConfig(BaseModel):
    """Full validated runner configuration."""

    # Hide input values in validation errors, so that a rejected token or bot token is not printed to the logs.
    model_config = ConfigDict(populate_by_name=True, hide_input_in_errors=True)

    version: int
    global_config: GlobalConfig = Field(alias="global")
    jobs: list[SyncJob]
    notifications: NotificationChannelsConfig = Field(default_factory=NotificationChannelsConfig)

    @model_validator(mode="after")
    def validate_mvp_constraints(self) -> RunnerConfig:
        """Validate constraints required by the MVP schema."""
        if self.version != 1:
            raise ValueError("Unsupported config version. Only version 1 is supported.")
        if not self.jobs:
            raise ValueError("Configuration must include at least one job.")

        seen_names: set[str] = set()
        duplicate_names: set[str] = set()
        for job in self.jobs:
            if job.name in seen_names:
                duplicate_names.add(job.name)
            seen_names.add(job.name)

        if duplicate_names:
            duplicates = ", ".join(sorted(duplicate_names))
            raise ValueError(f"Duplicate job names are not allowed: {duplicates}")

        if any(arg == "-n" or arg.startswith("--dry-run") for arg in self.global_config.extra_args):
            raise ValueError(
                "Do not set '-n' or '--dry-run' in global extra_args. Use the CLI '--dry-run/-n' option instead."
            )

        jobs_with_disallowed_flags: set[str] = set()
        for job in self.jobs:
            job_args = job.extra_args or []
            if any(arg == "-n" or arg.startswith("--dry-run") for arg in job_args):
                jobs_with_disallowed_flags.add(job.name)

        if jobs_with_disallowed_flags:
            job_names = ", ".join(sorted(jobs_with_disallowed_flags))
            raise ValueError(
                (
                    "Do not set '-n' or '--dry-run' in job extra_args. "
                    "Use the CLI '--dry-run/-n' option instead. "
                    f"Jobs: {job_names}"
                )
            )

        return self


class JobRunResult(BaseModel):
    """Per-job execution result."""

    job_name: str
    source: str
    destination: str
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    return_code: int
    succeeded: bool
    dry_run: bool
    error_count: int
    error_samples: list[str]
    last_stats: dict[str, Any] | None = None


class RunSummary(BaseModel):
    """Overall run summary."""

    global_name: str | None = None
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    duration_seconds: float
    dry_run: bool
    results: list[JobRunResult]
