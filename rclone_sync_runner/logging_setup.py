"""Logging configuration helpers."""

from __future__ import annotations

import logging


def setup_logging(level: str) -> None:
    """Configure process-wide logging.

    Args:
        level: Logging level name.
    """
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=resolved_level,
        format="[%(asctime)s][%(levelname)s] %(message)s (%(name)s)",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        force=True,
    )
