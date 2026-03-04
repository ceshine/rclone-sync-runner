"""Tests for run orchestration behavior."""

from __future__ import annotations

from datetime import UTC, datetime

from rclone_sync_runner.models import GlobalConfig, JobRunResult, RunSummary, RunnerConfig, SyncJob
from rclone_sync_runner.runner import run_jobs


class DummyNotifier:
    """Test notifier that captures emitted summaries."""

    def __init__(self) -> None:
        self.last_summary: RunSummary | None = None

    def on_run_finished(self, summary: RunSummary) -> None:
        self.last_summary = summary


def _result(job_name: str, succeeded: bool, return_code: int) -> JobRunResult:
    now = datetime.now(UTC)
    return JobRunResult(
        job_name=job_name,
        source=f"/src/{job_name}",
        destination=f"remote:{job_name}",
        started_at=now,
        ended_at=now,
        duration_seconds=1.0,
        return_code=return_code,
        succeeded=succeeded,
        dry_run=False,
        error_count=0 if succeeded else 1,
        error_samples=[] if succeeded else ["failed"],
        last_stats={"bytes": 100},
    )


def _config(continue_on_error: bool) -> RunnerConfig:
    return RunnerConfig.model_validate(
        {
            "version": 1,
            "global": {
                "name": "local-runner",
                "rclone_bin": "rclone",
                "log_level": "INFO",
                "continue_on_error": continue_on_error,
            },
            "jobs": [
                {"name": "a", "source": "/a", "destination": "remote:a"},
                {"name": "b", "source": "/b", "destination": "remote:b"},
                {"name": "c", "source": "/c", "destination": "remote:c"},
            ],
        }
    )


def test_run_jobs_returns_zero_when_all_success(monkeypatch) -> None:
    config = _config(continue_on_error=True)

    def fake_execute_sync_job(job: SyncJob, global_config: GlobalConfig, dry_run: bool = False) -> JobRunResult:
        del global_config
        result = _result(job.name, succeeded=True, return_code=0)
        result.dry_run = dry_run
        return result

    monkeypatch.setattr("rclone_sync_runner.runner.execute_sync_job", fake_execute_sync_job)

    summary, exit_code = run_jobs(config=config)

    assert exit_code == 0
    assert summary.total_jobs == 3
    assert summary.successful_jobs == 3
    assert summary.failed_jobs == 0
    assert summary.dry_run is False
    assert summary.global_name == "local-runner"


def test_run_jobs_returns_one_when_any_failure(monkeypatch) -> None:
    config = _config(continue_on_error=True)

    def fake_execute_sync_job(job: SyncJob, global_config: GlobalConfig, dry_run: bool = False) -> JobRunResult:
        del global_config
        if job.name == "b":
            result = _result(job.name, succeeded=False, return_code=1)
            result.dry_run = dry_run
            return result
        result = _result(job.name, succeeded=True, return_code=0)
        result.dry_run = dry_run
        return result

    monkeypatch.setattr("rclone_sync_runner.runner.execute_sync_job", fake_execute_sync_job)

    summary, exit_code = run_jobs(config=config)

    assert exit_code == 1
    assert summary.total_jobs == 3
    assert summary.successful_jobs == 2
    assert summary.failed_jobs == 1
    assert summary.dry_run is False


def test_run_jobs_stops_when_continue_on_error_is_false(monkeypatch) -> None:
    config = _config(continue_on_error=False)
    called_jobs: list[str] = []

    def fake_execute_sync_job(job: SyncJob, global_config: GlobalConfig, dry_run: bool = False) -> JobRunResult:
        del global_config
        called_jobs.append(job.name)
        if job.name == "b":
            result = _result(job.name, succeeded=False, return_code=1)
            result.dry_run = dry_run
            return result
        result = _result(job.name, succeeded=True, return_code=0)
        result.dry_run = dry_run
        return result

    monkeypatch.setattr("rclone_sync_runner.runner.execute_sync_job", fake_execute_sync_job)

    summary, exit_code = run_jobs(config=config)

    assert exit_code == 1
    assert called_jobs == ["a", "b"]
    assert summary.total_jobs == 2
    assert summary.successful_jobs == 1
    assert summary.failed_jobs == 1
    assert summary.dry_run is False


def test_run_jobs_calls_notifier(monkeypatch) -> None:
    config = _config(continue_on_error=True)
    notifier = DummyNotifier()

    def fake_execute_sync_job(job: SyncJob, global_config: GlobalConfig, dry_run: bool = False) -> JobRunResult:
        del global_config
        result = _result(job.name, succeeded=True, return_code=0)
        result.dry_run = dry_run
        return result

    monkeypatch.setattr("rclone_sync_runner.runner.execute_sync_job", fake_execute_sync_job)

    _, _ = run_jobs(config=config, notifiers=[notifier])

    assert notifier.last_summary is not None
    assert notifier.last_summary.total_jobs == 3
    assert notifier.last_summary.dry_run is False
    assert notifier.last_summary.global_name == "local-runner"


def test_run_jobs_sets_summary_dry_run_when_enabled(monkeypatch) -> None:
    config = _config(continue_on_error=True)

    def fake_execute_sync_job(job: SyncJob, global_config: GlobalConfig, dry_run: bool = False) -> JobRunResult:
        del global_config
        result = _result(job.name, succeeded=True, return_code=0)
        result.dry_run = dry_run
        return result

    monkeypatch.setattr("rclone_sync_runner.runner.execute_sync_job", fake_execute_sync_job)

    summary, exit_code = run_jobs(config=config, dry_run=True)

    assert exit_code == 0
    assert summary.dry_run is True
    assert all(result.dry_run for result in summary.results)
