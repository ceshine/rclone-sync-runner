"""Logging configuration helpers."""

from __future__ import annotations

import os
import logging

LOGGER = logging.getLogger("rclone_sync_runner")


def setup_logging(level: str) -> None:
    """Configure process-wide logging.

    Args:
        level (str): Logging level name.
    """
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    LOGGER.setLevel(logging.DEBUG if os.environ.get("DEBUG", "f").lower() in ("true", "1") else resolved_level)
    logging.basicConfig(
        level=resolved_level,
        format="[%(asctime)s][%(levelname)s] %(message)s (%(name)s)",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        force=True,
    )
