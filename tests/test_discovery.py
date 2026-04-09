"""Tests for the discovery module."""

from __future__ import annotations

import json
import subprocess
from io import StringIO

import pytest
from rich.console import Console

from rclone_sync_runner.config import build_runner_config
from rclone_sync_runner.discovery import (
    _build_lsjson_command,
    list_rclone_dirs,
    match_folder_pairs,
)
from rclone_sync_runner.models import SyncJob


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _console() -> Console:
    """Return a Console that writes to a StringIO buffer for assertion."""
    return Console(file=StringIO(), highlight=False, markup=False)


def _lsjson_item(name: str, path: str | None = None) -> dict:
    return {"Name": name, "Path": path if path is not None else name, "IsDir": True}


# ---------------------------------------------------------------------------
# _build_lsjson_command
# ---------------------------------------------------------------------------


def test_build_lsjson_command_non_recursive() -> None:
    cmd = _build_lsjson_command("rclone", "gdrive:Movies", recursive=False, max_depth=1)

    assert cmd[0] == "rclone"
    assert "lsjson" in cmd
    assert "--dirs-only" in cmd
    assert "--max-depth" in cmd
    assert cmd[cmd.index("--max-depth") + 1] == "1"
    assert "-R" not in cmd
    assert cmd[-1] == "gdrive:Movies"


def test_build_lsjson_command_recursive() -> None:
    cmd = _build_lsjson_command("/usr/bin/rclone", "remote:Backup", recursive=True, max_depth=4)

    assert cmd[0] == "/usr/bin/rclone"
    assert "-R" in cmd
    assert cmd[cmd.index("--max-depth") + 1] == "4"
    assert cmd[-1] == "remote:Backup"


# ---------------------------------------------------------------------------
# list_rclone_dirs
# ---------------------------------------------------------------------------


def test_list_rclone_dirs_success(monkeypatch) -> None:
    items = [{"Name": "foo", "Path": "foo", "IsDir": True}]

    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=json.dumps(items), stderr="")

    monkeypatch.setattr("rclone_sync_runner.discovery.subprocess.run", fake_run)

    result = list_rclone_dirs("rclone", "gdrive:Movies", recursive=False, max_depth=1)

    assert result == items


def test_list_rclone_dirs_empty_result(monkeypatch) -> None:
    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="[]", stderr="")

    monkeypatch.setattr("rclone_sync_runner.discovery.subprocess.run", fake_run)

    result = list_rclone_dirs("rclone", "gdrive:Empty", recursive=False, max_depth=1)

    assert result == []


def test_list_rclone_dirs_raises_on_nonzero_returncode(monkeypatch) -> None:
    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="permission denied")

    monkeypatch.setattr("rclone_sync_runner.discovery.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="permission denied"):
        list_rclone_dirs("rclone", "gdrive:Movies", recursive=False, max_depth=1)


def test_list_rclone_dirs_raises_on_invalid_json(monkeypatch) -> None:
    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="not valid json", stderr="")

    monkeypatch.setattr("rclone_sync_runner.discovery.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="Could not parse"):
        list_rclone_dirs("rclone", "gdrive:Movies", recursive=False, max_depth=1)


# ---------------------------------------------------------------------------
# match_folder_pairs
# ---------------------------------------------------------------------------


def test_match_folder_pairs_single_match() -> None:
    a_items = [_lsjson_item("foo")]
    b_items = [_lsjson_item("foo", path="subdir/foo")]
    console = _console()

    jobs = match_folder_pairs(a_items, b_items, "gdrive:A", "gdrive:B", console)

    assert len(jobs) == 1
    assert jobs[0].name == "foo"
    assert jobs[0].source == "gdrive:A/foo"
    assert jobs[0].destination == "gdrive:B/subdir/foo"


def test_match_folder_pairs_zero_matches_skips() -> None:
    a_items = [_lsjson_item("bar")]
    b_items = [_lsjson_item("baz")]
    console = _console()

    jobs = match_folder_pairs(a_items, b_items, "gdrive:A", "gdrive:B", console)

    assert jobs == []


def test_match_folder_pairs_multiple_matches_skips() -> None:
    a_items = [_lsjson_item("baz")]
    b_items = [
        _lsjson_item("baz", path="x/baz"),
        _lsjson_item("baz", path="y/baz"),
    ]
    console = _console()

    jobs = match_folder_pairs(a_items, b_items, "gdrive:A", "gdrive:B", console)

    assert jobs == []


def test_match_folder_pairs_mixed_three_children() -> None:
    # "alpha" → 0 matches, "beta" → 1 match, "gamma" → 2 matches
    a_items = [_lsjson_item("alpha"), _lsjson_item("beta"), _lsjson_item("gamma")]
    b_items = [
        _lsjson_item("beta", path="sub/beta"),
        _lsjson_item("gamma", path="x/gamma"),
        _lsjson_item("gamma", path="y/gamma"),
    ]
    console = _console()

    jobs = match_folder_pairs(a_items, b_items, "remote:A", "remote:B", console)

    assert len(jobs) == 1
    assert jobs[0].name == "beta"


def test_match_folder_pairs_trailing_slash_normalised() -> None:
    a_items = [_lsjson_item("foo")]
    b_items = [_lsjson_item("foo", path="nested/foo")]
    console = _console()

    jobs = match_folder_pairs(a_items, b_items, "gdrive:A/", "gdrive:B/", console)

    assert "//" not in jobs[0].source
    assert "//" not in jobs[0].destination
    assert jobs[0].source == "gdrive:A/foo"
    assert jobs[0].destination == "gdrive:B/nested/foo"


# ---------------------------------------------------------------------------
# build_runner_config
# ---------------------------------------------------------------------------


def test_build_runner_config_produces_valid_config() -> None:
    jobs = [
        SyncJob(name="foo", source="gdrive:A/foo", destination="gdrive:B/foo"),
        SyncJob(name="bar", source="gdrive:A/bar", destination="gdrive:B/bar"),
    ]

    config = build_runner_config(jobs)

    assert config.version == 1
    assert len(config.jobs) == 2


def test_build_runner_config_preserves_job_names() -> None:
    jobs = [SyncJob(name="my-job", source="/src", destination="remote:dst")]

    config = build_runner_config(jobs)

    assert config.jobs[0].name == "my-job"
    assert config.jobs[0].source == "/src"
    assert config.jobs[0].destination == "remote:dst"
