"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from rclone_sync_runner.config import ConfigError, load_config, render_config_yaml, build_runner_config
from rclone_sync_runner.models import SyncJob


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


_NTFY_CONFIG_TEMPLATE = """
version: 1
global:
  log_level: INFO
jobs:
  - name: docs
    source: /data/docs
    destination: remote:docs
notifications:
  ntfy:
{ntfy_block}
"""


def test_load_config_accepts_ntfy_notifications(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "ntfy_notifications.yaml",
        _NTFY_CONFIG_TEMPLATE.format(
            ntfy_block=(
                "    server_url: https://ntfy.example.com\n"
                "    topic: rclone-sync\n"
                "    token: tk_secret\n"
                "    priority: 4"
            )
        ),
    )

    config = load_config(config_path)

    assert config.notifications.ntfy is not None
    assert config.notifications.ntfy.server_url == "https://ntfy.example.com"
    assert config.notifications.ntfy.topic == "rclone-sync"
    assert config.notifications.ntfy.token == "tk_secret"
    assert config.notifications.ntfy.priority == 4


def test_load_config_applies_ntfy_defaults(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "ntfy_defaults.yaml",
        _NTFY_CONFIG_TEMPLATE.format(ntfy_block="    server_url: https://ntfy.sh\n    topic: rclone-sync"),
    )

    config = load_config(config_path)

    assert config.notifications.ntfy is not None
    assert config.notifications.ntfy.token is None
    assert config.notifications.ntfy.priority == 3


@pytest.mark.parametrize(
    ("ntfy_block", "field_name"),
    [
        ("    server_url: ntfy.example.com\n    topic: rclone-sync", "server_url"),
        ("    server_url: https://ntfy.example.com\n    topic: rclone/sync", "topic"),
        ("    server_url: https://ntfy.example.com\n    topic: rclone-sync\n    token: ''", "token"),
        ("    server_url: https://ntfy.example.com\n    topic: rclone-sync\n    priority: 6", "priority"),
        ("    server_url: https://[::1\n    topic: rclone-sync", "server_url"),
        ("    server_url: https://ntfy.example.com/?a=1\n    topic: rclone-sync", "server_url"),
        ("    server_url: https://ntfy.example.com/#top\n    topic: rclone-sync", "server_url"),
        ("    server_url: 'https://ntfy.example.com?'\n    topic: rclone-sync", "server_url"),
        ("    server_url: 'https://ntfy.example.com#'\n    topic: rclone-sync", "server_url"),
        ("    server_url: http://ntfy.example.com\n    topic: rclone-sync\n    token: tk_secret", "https"),
    ],
)
def test_load_config_rejects_invalid_ntfy_values(tmp_path: Path, ntfy_block: str, field_name: str) -> None:
    config_path = _write_config(
        tmp_path / "invalid_ntfy_notifications.yaml",
        _NTFY_CONFIG_TEMPLATE.format(ntfy_block=ntfy_block),
    )

    with pytest.raises(ConfigError, match=field_name):
        load_config(config_path)


@pytest.mark.parametrize(
    "token_yaml",
    [
        # A block scalar keeps the trailing newline.
        "    token: |\n      tk_secret",
        "    token: tk_sécret",
        "    token: secret",
    ],
)
def test_load_config_rejects_malformed_ntfy_token_without_echoing_it(tmp_path: Path, token_yaml: str) -> None:
    config_path = _write_config(
        tmp_path / "malformed_ntfy_token.yaml",
        _NTFY_CONFIG_TEMPLATE.format(
            ntfy_block=f"    server_url: https://ntfy.example.com\n    topic: rclone-sync\n{token_yaml}"
        ),
    )

    with pytest.raises(ConfigError, match="token") as error_info:
        load_config(config_path)

    assert "secret" not in str(error_info.value)
    assert "sécret" not in str(error_info.value)


def test_load_config_accepts_ntfy_http_url_without_token(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "ntfy_http.yaml",
        _NTFY_CONFIG_TEMPLATE.format(ntfy_block="    server_url: http://localhost:8080\n    topic: rclone-sync"),
    )

    config = load_config(config_path)

    assert config.notifications.ntfy is not None
    assert config.notifications.ntfy.server_url == "http://localhost:8080"


def test_load_config_accepts_global_extra_args(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "global_extra_args.yaml",
        """
version: 1
global:
  log_level: INFO
  extra_args:
    - --fast-list
    - --transfers
    - "8"
jobs:
  - name: docs
    source: /data/docs
    destination: remote:docs
""",
    )

    config = load_config(config_path)

    assert config.global_config.extra_args == ["--fast-list", "--transfers", "8"]
    assert config.jobs[0].extra_args is None


@pytest.mark.parametrize("dry_run_arg", ["-n", "--dry-run", "--dry-run=true"])
def test_load_config_rejects_dry_run_flags_in_global_extra_args(tmp_path: Path, dry_run_arg: str) -> None:
    config_path = _write_config(
        tmp_path / "invalid_global_dry_run.yaml",
        f"""
version: 1
global:
  log_level: INFO
  extra_args:
    - {dry_run_arg}
jobs:
  - name: docs
    source: /data/docs
    destination: remote:docs
""",
    )

    with pytest.raises(ConfigError, match="Do not set '-n' or '--dry-run'"):
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


# ---------------------------------------------------------------------------
# render_config_yaml
# ---------------------------------------------------------------------------


def test_render_config_yaml_uses_global_alias() -> None:
    config = build_runner_config([SyncJob(name="j", source="/a", destination="/b")])

    yaml_text = render_config_yaml(config)

    assert "global:" in yaml_text
    assert "global_config:" not in yaml_text


def test_render_config_yaml_omits_empty_notifications() -> None:
    config = build_runner_config([SyncJob(name="j", source="/a", destination="/b")])

    yaml_text = render_config_yaml(config)

    assert "telegram" not in yaml_text
    assert "notifications" not in yaml_text


def test_render_config_yaml_round_trips_through_load_config(tmp_path: Path) -> None:
    jobs = [
        SyncJob(name="alpha", source="gdrive:A/alpha", destination="gdrive:B/alpha"),
        SyncJob(name="beta", source="gdrive:A/beta", destination="gdrive:B/beta"),
    ]
    config = build_runner_config(jobs)
    yaml_text = render_config_yaml(config)

    config_file = tmp_path / "draft.yaml"
    config_file.write_text(yaml_text, encoding="utf-8")

    loaded = load_config(config_file)

    assert loaded.version == 1
    assert len(loaded.jobs) == 2
    assert loaded.jobs[0].name == "alpha"
    assert loaded.jobs[1].name == "beta"
