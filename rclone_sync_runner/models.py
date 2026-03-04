"""Typed models for configuration and runtime results."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GlobalConfig(BaseModel):
    """Global settings that apply to all sync jobs."""

    name: str | None = None
    rclone_bin: str = "rclone"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    continue_on_error: bool = True


class SyncJob(BaseModel):
    """Single rclone sync job definition."""

    name: str
    source: str
    destination: str
    extra_args: list[str] = Field(default_factory=list)


class TelegramNotificationConfig(BaseModel):
    """Telegram notification channel settings."""

    bot_token: str = Field(min_length=1)
    chat_id: str = Field(min_length=1)
    message_thread_id: int | None = None
    disable_notification: bool = False


class NotificationChannelsConfig(BaseModel):
    """Optional notification channel configuration."""

    telegram: TelegramNotificationConfig | None = None


class RunnerConfig(BaseModel):
    """Full validated runner configuration."""

    model_config = ConfigDict(populate_by_name=True)

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

        jobs_with_disallowed_flags: set[str] = set()
        for job in self.jobs:
            if any(arg == "-n" or arg.startswith("--dry-run") for arg in job.extra_args):
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
