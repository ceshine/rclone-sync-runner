"""Folder-pair discovery logic using rclone lsjson for remote path traversal."""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from rich.console import Console

from .models import SyncJob

LOGGER = logging.getLogger(__name__)


def _build_lsjson_command(
    rclone_bin: str,
    remote_path: str,
    *,
    recursive: bool,
    max_depth: int,
) -> list[str]:
    """Build the rclone lsjson argument list.

    Kept separate from list_rclone_dirs so the command shape can be asserted
    in unit tests without any subprocess involvement.

    Args:
        rclone_bin (str): Path or name of the rclone binary.
        remote_path (str): Remote path to list (e.g. ``gdrive:Movies``).
        recursive (bool): Whether to recurse into subdirectories.
        max_depth (int): Maximum directory traversal depth.

    Returns:
        list[str]: Argument list ready for subprocess execution.
    """
    command = [rclone_bin, "lsjson", "--dirs-only", "--max-depth", str(max_depth)]
    if recursive:
        command.append("-R")
    command.append(remote_path)
    return command


def list_rclone_dirs(
    rclone_bin: str,
    remote_path: str,
    *,
    recursive: bool,
    max_depth: int,
) -> list[dict[str, Any]]:
    """Call rclone lsjson and return the parsed list of directory items.

    Each item is a dict with at minimum "Name" (basename) and "Path"
    (path relative to remote_path).

    Args:
        rclone_bin (str): Path or name of the rclone binary.
        remote_path (str): Remote path to list (e.g. ``gdrive:Movies``).
        recursive (bool): Whether to recurse into subdirectories.
        max_depth (int): Maximum directory traversal depth.

    Returns:
        list[dict[str, Any]]: Parsed directory entries from rclone lsjson output.

    Raises:
        RuntimeError: If rclone exits with a non-zero code or stdout is not
            valid JSON.
    """
    command = _build_lsjson_command(rclone_bin, remote_path, recursive=recursive, max_depth=max_depth)
    LOGGER.debug("Running: %s", " ".join(command))

    result = subprocess.run(command, capture_output=True, text=True, check=False, encoding="utf-8")

    if result.returncode != 0:
        raise RuntimeError(
            f"rclone lsjson failed for '{remote_path}' (exit {result.returncode}): {result.stderr.strip()}"
        )

    try:
        items: list[dict[str, Any]] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse rclone lsjson output for '{remote_path}': {exc}") from exc

    return items


def match_folder_pairs(
    folder_a_items: list[dict[str, Any]],
    folder_b_items: list[dict[str, Any]],
    folder_a_root: str,
    folder_b_root: str,
    console: Console,
) -> list[SyncJob]:
    """Match folder A children against folder B dirs and return a SyncJob list.

    For each item in folder_a_items, searches folder_b_items for items with
    the same Name.  Applies skip-if-zero / skip-if-multiple logic:

    - 0 matches: logged as SKIP (no match)
    - 1 match:   produces a SyncJob
    - 2+ matches: logged as SKIP (ambiguous)

    Args:
        folder_a_items (list[dict[str, Any]]): Directory entries from folder A (source root).
        folder_b_items (list[dict[str, Any]]): Directory entries from folder B (destination tree).
        folder_a_root (str): rclone remote root path for folder A.
        folder_b_root (str): rclone remote root path for folder B.
        console (Console): Rich console for progress output.

    Returns:
        list[SyncJob]: One SyncJob per unambiguous matched folder pair.
    """
    a_root = folder_a_root.rstrip("/")
    b_root = folder_b_root.rstrip("/")

    # Index folder B items by directory name for O(1) lookup
    b_index: dict[str, list[dict[str, Any]]] = {}
    for item in folder_b_items:
        name = item["Name"]
        b_index.setdefault(name, []).append(item)

    jobs: list[SyncJob] = []

    for a_item in sorted(folder_a_items, key=lambda x: x["Name"]):
        name = a_item["Name"]
        matches = b_index.get(name, [])

        if len(matches) == 0:
            LOGGER.info("No match found in Folder B for '%s'", name)
            console.print(f"  [dim]SKIP[/dim] {name} — no match in Folder B")
        elif len(matches) == 1:
            source = f"{a_root}/{a_item['Path']}"
            destination = f"{b_root}/{matches[0]['Path']}"
            jobs.append(SyncJob(name=name, source=source, destination=destination))
            console.print(f"  [green]MATCH[/green] {name} → {destination}")
        else:
            locations = ", ".join(f"{b_root}/{m['Path']}" for m in matches)
            LOGGER.warning("Multiple matches for '%s' in Folder B: %s", name, locations)
            console.print(f"  [yellow]SKIP[/yellow] {name} — multiple matches: {locations}")

    return jobs
