"""Tests for pure formatting utilities."""

from __future__ import annotations

import pytest

from rclone_sync_runner.formatting import stats_value, format_bytes


class TestFormatBytes:
    def test_zero_returns_zero_b(self) -> None:
        assert format_bytes(0) == "0 B"

    def test_negative_returns_zero_b(self) -> None:
        assert format_bytes(-1) == "0 B"

    def test_bytes_range(self) -> None:
        assert format_bytes(512) == "512.00 B"

    def test_kib_range(self) -> None:
        assert format_bytes(1024) == "1.00 KiB"

    def test_mib_range(self) -> None:
        assert format_bytes(1024 * 1024) == "1.00 MiB"

    def test_gib_range(self) -> None:
        assert format_bytes(1024**3) == "1.00 GiB"

    def test_si_units(self) -> None:
        result = format_bytes(1_000_000, binary=False)
        assert result == "1.00 MB"

    def test_si_kb(self) -> None:
        result = format_bytes(1_000, binary=False)
        assert result == "1.00 kB"


class TestStatsValue:
    def test_none_stats_returns_zero(self) -> None:
        assert stats_value(None, "bytes") == "0"

    def test_missing_key_returns_zero(self) -> None:
        assert stats_value({"transfers": 5}, "bytes") == "0"

    def test_bool_value_returns_zero(self) -> None:
        assert stats_value({"fatalError": True}, "fatalError") == "0"

    def test_int_value(self) -> None:
        assert stats_value({"transfers": 7}, "transfers") == "7"

    def test_float_value_truncates_to_int(self) -> None:
        assert stats_value({"speed": 25226284.6}, "speed") == "25226284"

    def test_non_numeric_value_returns_zero(self) -> None:
        assert stats_value({"eta": "soon"}, "eta") == "0"

    @pytest.mark.parametrize("value", [0, 0.0])
    def test_zero_numeric_value(self, value: int | float) -> None:
        assert stats_value({"bytes": value}, "bytes") == "0"
