"""Tests for sync job command construction and log parsing."""

from __future__ import annotations

from rclone_sync_runner.models import GlobalConfig, SyncJob
from rclone_sync_runner.sync import (
    build_rclone_sync_command,
    execute_sync_job,
    parse_rclone_stderr_line,
)


def test_build_rclone_sync_command_includes_required_flags() -> None:
    job = SyncJob(
        name="docs",
        source="/src/docs",
        destination="remote:docs",
        extra_args=["--fast-list"],
    )
    global_config = GlobalConfig(rclone_bin="rclone", log_level="INFO")

    command = build_rclone_sync_command(job=job, global_config=global_config)

    assert command[:4] == ["rclone", "sync", "/src/docs", "remote:docs"]
    assert "--use-json-log" in command
    assert "--stats" in command
    assert "30s" in command
    assert command[-1] == "--fast-list"


def test_build_rclone_sync_command_includes_dry_run_flag_when_enabled() -> None:
    job = SyncJob(
        name="docs",
        source="/src/docs",
        destination="remote:docs",
        extra_args=[],
    )
    global_config = GlobalConfig(rclone_bin="rclone", log_level="INFO")

    command = build_rclone_sync_command(job=job, global_config=global_config, dry_run=True)

    assert command[-1] == "--dry-run"


def test_parse_rclone_stderr_line_extracts_stats() -> None:
    line = (
        '{"level":"info","msg":"Transferred","stats":{"bytes":1024,"checks":5},'
        '"source":"rclone","time":"2026-02-26T00:00:00Z"}'
    )

    parsed = parse_rclone_stderr_line(line)

    assert parsed.is_json is True
    assert parsed.stats == {"bytes": 1024, "checks": 5}
    assert parsed.error_message is None


def test_parse_rclone_stderr_line_extracts_error_message() -> None:
    line = '{"level":"error","msg":"copy failed","time":"2026-02-26T00:00:00Z"}'

    parsed = parse_rclone_stderr_line(line)

    assert parsed.is_json is True
    assert parsed.error_message == "copy failed"


def test_parse_rclone_stderr_line_handles_malformed_line() -> None:
    parsed = parse_rclone_stderr_line("not json at all")

    assert parsed.is_json is False
    assert parsed.raw_line == "not json at all"
    assert parsed.stats is None
    assert parsed.error_message is None


class FakeProcess:
    """Simple process fake for testing stderr streaming behavior."""

    def __init__(self, stderr_lines: list[str], return_code: int) -> None:
        self.stderr = stderr_lines
        self._return_code = return_code

    def wait(self) -> int:
        return self._return_code


def test_execute_sync_job_collects_error_samples_and_stats(monkeypatch) -> None:
    job = SyncJob(
        name="docs",
        source="/src/docs",
        destination="remote:docs",
        extra_args=[],
    )
    global_config = GlobalConfig(rclone_bin="rclone", log_level="INFO")

    def fake_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        del args, kwargs
        return FakeProcess(
            stderr_lines=[
                '{"level":"info","stats":{"bytes":12}}\n',
                "not json\n",
                '{"level":"error","msg":"copy failed"}\n',
            ],
            return_code=1,
        )

    monkeypatch.setattr("rclone_sync_runner.sync.subprocess.Popen", fake_popen)

    result = execute_sync_job(job=job, global_config=global_config, dry_run=True)

    assert result.succeeded is False
    assert result.return_code == 1
    assert result.dry_run is True
    assert result.error_count == 1
    assert result.error_samples == ["copy failed"]
    assert result.last_stats == {"bytes": 12}
