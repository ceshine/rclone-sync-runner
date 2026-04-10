"""Formatting utilities for rclone stats and byte values."""

from __future__ import annotations


def format_bytes(num_bytes: int, binary: bool = True) -> str:
    """Convert a byte count into a human-readable size string.

    Args:
        num_bytes (int): The number of bytes to format. Values <= 0 return
            ``"0 B"``.
        binary (bool): If ``True`` (default), use binary prefixes (KiB, MiB,
            …) with a 1024-byte step. If ``False``, use SI prefixes (kB, MB,
            …) with a 1000-byte step.

    Returns:
        str: A string such as ``"1.50 MiB"`` or ``"1.57 MB"`` representing the
            size in the largest unit where the value is >= 1.
    """
    if num_bytes <= 0:
        return "0 B"

    if binary:
        units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
        step = 1024.0
    else:
        units = ["B", "kB", "MB", "GB", "TB", "PB"]
        step = 1000.0

    size = float(num_bytes)
    for unit in units:
        if size < step or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= step
    return f"{size:.2f} {units[-1]}"


def stats_value(last_stats: dict[str, object] | None, key: str) -> str:
    """Get a numeric stats value from last_stats with a safe fallback.

    Args:
        last_stats (dict[str, object] | None): rclone stats payload, or None if unavailable.
        key (str): Stats field name to retrieve.

    Returns:
        str: Integer string representation of the value, or ``"0"`` if absent or non-numeric.
    """
    if not last_stats:
        return "0"

    value = last_stats.get(key)
    if isinstance(value, bool):
        return "0"
    if isinstance(value, int | float):
        return str(int(value))
    return "0"
