"""Subprocess integration for running rclone sync jobs."""

from __future__ import annotations

import logging
import subprocess
from datetime import UTC, datetime
from typing import Any

import orjson
from pydantic import BaseModel

from .models import GlobalConfig, JobRunResult, SyncJob

LOGGER = logging.getLogger(__name__)

MAX_ERROR_SAMPLES = 20


class ParsedLogLine(BaseModel):
    """Parsed representation of a single rclone stderr line."""

    is_json: bool
    stats: dict[str, Any] | None = None
    error_message: str | None = None
    raw_line: str


def build_rclone_sync_command(job: SyncJob, global_config: GlobalConfig) -> list[str]:
    """Build an rclone sync command for a job.

    Args:
        job: Job definition.
        global_config: Global config values.

    Returns:
        Command argument list for subprocess execution.
    """
    command = [
        global_config.rclone_bin,
        "sync",
        job.source,
        job.destination,
        "--use-json-log",
        "--log-level",
        global_config.log_level,
        "--stats",
        "30s",
        "--stats-log-level",
        "INFO",
    ]
    command.extend(job.extra_args)
    return command


def parse_rclone_stderr_line(line: str) -> ParsedLogLine:
    """Parse one stderr line from rclone JSON logs.

    Args:
        line: Raw stderr line.

    Returns:
        Parsed line with stats and/or error details when available.
    """
    sanitized_line = line.strip()
    if not sanitized_line:
        return ParsedLogLine(is_json=False, raw_line=sanitized_line)

    try:
        payload = orjson.loads(sanitized_line)
    except orjson.JSONDecodeError:
        return ParsedLogLine(is_json=False, raw_line=sanitized_line)

    if not isinstance(payload, dict):
        return ParsedLogLine(is_json=True, raw_line=sanitized_line)

    stats = payload.get("stats")
    parsed_stats = stats if isinstance(stats, dict) else None

    error_message: str | None = None
    level_value = payload.get("level")
    if isinstance(level_value, str) and level_value.lower() == "error":
        message = payload.get("msg", "")
        if isinstance(message, str):
            error_message = message or sanitized_line
        else:
            error_message = sanitized_line

    return ParsedLogLine(
        is_json=True,
        stats=parsed_stats,
        error_message=error_message,
        raw_line=sanitized_line,
    )


def execute_sync_job(job: SyncJob, global_config: GlobalConfig) -> JobRunResult:
    """Execute one sync job and collect structured results.

    Args:
        job: Job definition.
        global_config: Global config values.

    Returns:
        Job execution result.

    Raises:
        RuntimeError: If subprocess could not be started.
    """
    started_at = datetime.now(UTC)
    command = build_rclone_sync_command(job=job, global_config=global_config)

    LOGGER.info(
        "Starting job '%s' from '%s' to '%s'",
        job.name,
        job.source,
        job.destination,
    )

    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        command_text = " ".join(command)
        raise RuntimeError(f"Failed to start rclone command: {command_text}. Error: {error}") from error

    error_count = 0
    error_samples: list[str] = []
    last_stats: dict[str, Any] | None = None

    if process.stderr is None:
        raise RuntimeError(f"No stderr stream available for job '{job.name}'.")

    for line in process.stderr:
        parsed_line = parse_rclone_stderr_line(line)

        if not parsed_line.is_json:
            if parsed_line.raw_line:
                LOGGER.warning("Unstructured rclone log line for job '%s': %s", job.name, parsed_line.raw_line)
            continue

        if parsed_line.stats is not None:
            last_stats = parsed_line.stats
            LOGGER.info("Job '%s' stats update: %s", job.name, parsed_line.stats)

        if parsed_line.error_message:
            error_count += 1
            if len(error_samples) < MAX_ERROR_SAMPLES:
                error_samples.append(parsed_line.error_message)
            LOGGER.error("Job '%s' error event: %s", job.name, parsed_line.error_message)

    return_code = process.wait()
    ended_at = datetime.now(UTC)
    duration_seconds = (ended_at - started_at).total_seconds()
    succeeded = return_code == 0

    if succeeded:
        LOGGER.info("Finished job '%s' successfully in %.2fs", job.name, duration_seconds)
    else:
        LOGGER.error(
            "Job '%s' failed in %.2fs with return code %s",
            job.name,
            duration_seconds,
            return_code,
        )

    return JobRunResult(
        job_name=job.name,
        source=job.source,
        destination=job.destination,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=duration_seconds,
        return_code=return_code,
        succeeded=succeeded,
        error_count=error_count,
        error_samples=error_samples,
        last_stats=last_stats,
    )
