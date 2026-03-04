"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from rclone_sync_runner.config import ConfigError, load_config


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_load_config_success(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "valid.yaml",
        """
version: 1
global:
  rclone_bin: rclone
  log_level: INFO
  continue_on_error: true
jobs:
  - name: photos
    source: /data/photos
    destination: remote:photos
    extra_args:
      - --delete-during
""",
    )

    config = load_config(config_path)

    assert config.version == 1
    assert config.global_config.rclone_bin == "rclone"
    assert len(config.jobs) == 1
    assert config.jobs[0].extra_args == ["--delete-during"]


def test_load_config_rejects_duplicate_job_names(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "duplicate_names.yaml",
        """
version: 1
global:
  log_level: INFO
jobs:
  - name: backup
    source: /a
    destination: /b
  - name: backup
    source: /c
    destination: /d
""",
    )

    with pytest.raises(ConfigError, match="Duplicate job names"):
        load_config(config_path)


def test_load_config_rejects_empty_jobs(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "empty_jobs.yaml",
        """
version: 1
global:
  log_level: INFO
jobs: []
""",
    )

    with pytest.raises(ConfigError, match="at least one job"):
        load_config(config_path)


def test_load_config_rejects_invalid_version(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "invalid_version.yaml",
        """
version: 2
global:
  log_level: INFO
jobs:
  - name: docs
    source: /data/docs
    destination: remote:docs
""",
    )

    with pytest.raises(ConfigError, match="Only version 1 is supported"):
        load_config(config_path)


def test_load_config_rejects_non_string_extra_args(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "invalid_extra_args.yaml",
        """
version: 1
global:
  log_level: INFO
jobs:
  - name: docs
    source: /data/docs
    destination: remote:docs
    extra_args:
      - --fast-list
      - 123
""",
    )

    with pytest.raises(ConfigError, match="extra_args"):
        load_config(config_path)


def test_load_config_accepts_telegram_notifications(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "telegram_notifications.yaml",
        """
version: 1
global:
  log_level: INFO
jobs:
  - name: docs
    source: /data/docs
    destination: remote:docs
notifications:
  telegram:
    bot_token: "12345:ABCDEF"
    chat_id: "-10012345"
    message_thread_id: 42
    disable_notification: true
""",
    )

    config = load_config(config_path)

    assert config.notifications.telegram is not None
    assert config.notifications.telegram.bot_token == "12345:ABCDEF"
    assert config.notifications.telegram.chat_id == "-10012345"
    assert config.notifications.telegram.message_thread_id == 42
    assert config.notifications.telegram.disable_notification is True


def test_load_config_rejects_empty_telegram_token(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "invalid_telegram_notifications.yaml",
        """
version: 1
global:
  log_level: INFO
jobs:
  - name: docs
    source: /data/docs
    destination: remote:docs
notifications:
  telegram:
    bot_token: ""
    chat_id: "-10012345"
""",
    )

    with pytest.raises(ConfigError, match="bot_token"):
        load_config(config_path)


@pytest.mark.parametrize("dry_run_arg", ["-n", "--dry-run", "--dry-run=true"])
def test_load_config_rejects_dry_run_flags_in_extra_args(tmp_path: Path, dry_run_arg: str) -> None:
    config_path = _write_config(
        tmp_path / "invalid_dry_run_extra_args.yaml",
        f"""
version: 1
global:
  log_level: INFO
jobs:
  - name: docs
    source: /data/docs
    destination: remote:docs
    extra_args:
      - {dry_run_arg}
""",
    )

    with pytest.raises(ConfigError, match="Do not set '-n' or '--dry-run'"):
        load_config(config_path)
