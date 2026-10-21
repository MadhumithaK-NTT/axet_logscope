"""Tests for logscope.commands.timeline."""

from __future__ import annotations

import io
from datetime import datetime

import pytest

from logscope.parser import parse_stream
from logscope.commands.timeline import (
    VALID_BUCKETS,
    bucket_minutes,
    timeline,
    _floor_timestamp,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(text: str, bucket: str) -> dict:
    malformed: list[int] = [0]
    entries = parse_stream(io.StringIO(text), malformed)
    return timeline(entries, malformed, bucket)


def _lines(*specs: tuple[str, str, str]) -> str:
    """Build log text from (timestamp, level, message) tuples."""
    return "".join(f"{ts} {lvl} {msg}\n" for ts, lvl, msg in specs)


# ---------------------------------------------------------------------------
# bucket_minutes helper
# ---------------------------------------------------------------------------

class TestBucketMinutes:
    def test_15m(self):
        assert bucket_minutes("15m") == 15

    def test_30m(self):
        assert bucket_minutes("30m") == 30

    def test_1h(self):
        assert bucket_minutes("1h") == 60

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid bucket"):
            bucket_minutes("2h")

    def test_invalid_empty_string_raises(self):
        with pytest.raises(ValueError):
            bucket_minutes("")

    def test_valid_buckets_constant(self):
        assert VALID_BUCKETS == {"15m", "30m", "1h"}


# ---------------------------------------------------------------------------
# Bucket-floor calculation
# ---------------------------------------------------------------------------

class TestFloorTimestamp:
    # 15-minute buckets
    def test_15m_floor_start_of_bucket(self):
        ts = datetime(2026, 10, 1, 9, 0, 0)
        assert _floor_timestamp(ts, 15) == datetime(2026, 10, 1, 9, 0, 0)

    def test_15m_floor_mid_bucket(self):
        ts = datetime(2026, 10, 1, 9, 7, 33)
        assert _floor_timestamp(ts, 15) == datetime(2026, 10, 1, 9, 0, 0)

    def test_15m_floor_at_15(self):
        ts = datetime(2026, 10, 1, 9, 15, 0)
        assert _floor_timestamp(ts, 15) == datetime(2026, 10, 1, 9, 15, 0)

    def test_15m_floor_just_before_boundary(self):
        ts = datetime(2026, 10, 1, 9, 14, 59)
        assert _floor_timestamp(ts, 15) == datetime(2026, 10, 1, 9, 0, 0)

    def test_15m_floor_at_45(self):
        ts = datetime(2026, 10, 1, 9, 45, 0)
        assert _floor_timestamp(ts, 15) == datetime(2026, 10, 1, 9, 45, 0)

    # 30-minute buckets
    def test_30m_floor_start(self):
        ts = datetime(2026, 10, 1, 9, 0, 0)
        assert _floor_timestamp(ts, 30) == datetime(2026, 10, 1, 9, 0, 0)

    def test_30m_floor_at_30(self):
        ts = datetime(2026, 10, 1, 9, 30, 0)
        assert _floor_timestamp(ts, 30) == datetime(2026, 10, 1, 9, 30, 0)

    def test_30m_floor_mid(self):
        ts = datetime(2026, 10, 1, 9, 17, 0)
        assert _floor_timestamp(ts, 30) == datetime(2026, 10, 1, 9, 0, 0)

    # 1-hour buckets
    def test_1h_floor_start(self):
        ts = datetime(2026, 10, 1, 9, 0, 0)
        assert _floor_timestamp(ts, 60) == datetime(2026, 10, 1, 9, 0, 0)

    def test_1h_floor_mid_hour(self):
        ts = datetime(2026, 10, 1, 9, 37, 22)
        assert _floor_timestamp(ts, 60) == datetime(2026, 10, 1, 9, 0, 0)

    def test_1h_floor_next_hour(self):
        ts = datetime(2026, 10, 1, 10, 0, 0)
        assert _floor_timestamp(ts, 60) == datetime(2026, 10, 1, 10, 0, 0)


# ---------------------------------------------------------------------------
# Bucket boundary attribution
# ---------------------------------------------------------------------------

class TestBucketBoundary:
    def test_15m_boundary_timestamp_in_new_bucket(self):
        text = _lines(
            ("2026-10-01 09:00:00", "ERROR", "start"),
            ("2026-10-01 09:15:00", "ERROR", "boundary"),   # exact boundary
            ("2026-10-01 09:29:00", "ERROR", "before next"),
        )
        result = _run(text, "15m")
        labels = [label for label, _ in result["buckets"]]
        # Match on label *start* to avoid confusing 09:15 start with 09:00–09:15 end.
        assert any(l.startswith("2026-10-01 09:00") for l in labels)
        assert any(l.startswith("2026-10-01 09:15") for l in labels)
        # boundary belongs to 09:15 bucket, not 09:00
        bucket_09_00 = next(c for l, c in result["buckets"] if l.startswith("2026-10-01 09:00"))
        bucket_09_15 = next(c for l, c in result["buckets"] if l.startswith("2026-10-01 09:15"))
        assert bucket_09_00 == 1
        assert bucket_09_15 == 2

    def test_30m_boundary_timestamp_in_new_bucket(self):
        text = _lines(
            ("2026-10-01 09:00:00", "ERROR", "first"),
            ("2026-10-01 09:30:00", "ERROR", "boundary"),
        )
        result = _run(text, "30m")
        assert len(result["buckets"]) == 2
        bucket_00 = next(c for l, c in result["buckets"] if l.startswith("2026-10-01 09:00"))
        bucket_30 = next(c for l, c in result["buckets"] if l.startswith("2026-10-01 09:30"))
        assert bucket_00 == 1
        assert bucket_30 == 1

    def test_1h_boundary_timestamp_in_new_bucket(self):
        text = _lines(
            ("2026-10-01 09:00:00", "ERROR", "first"),
            ("2026-10-01 10:00:00", "ERROR", "next hour"),
        )
        result = _run(text, "1h")
        assert len(result["buckets"]) == 2


# ---------------------------------------------------------------------------
# All three bucket sizes
# ---------------------------------------------------------------------------

class TestBucketSizes:
    TEXT = _lines(
        ("2026-10-01 09:00:00", "ERROR", "e1"),
        ("2026-10-01 09:10:00", "ERROR", "e2"),
        ("2026-10-01 09:20:00", "ERROR", "e3"),
        ("2026-10-01 09:40:00", "ERROR", "e4"),
        ("2026-10-01 10:05:00", "ERROR", "e5"),
    )

    def test_15m_bucket_count(self):
        result = _run(self.TEXT, "15m")
        # 09:00→09:15 (e1,e2 nope — e2 is 09:10 so same bucket as e1)
        # 09:15→09:30 (e3 at 09:20)
        # 09:30→09:45 (e4 at 09:40)
        # 10:00→10:15 (e5 at 10:05)
        assert len(result["buckets"]) == 4

    def test_30m_bucket_count(self):
        result = _run(self.TEXT, "30m")
        # 09:00 (e1,e2,e3), 09:30 (e4), 10:00 (e5)
        assert len(result["buckets"]) == 3

    def test_1h_bucket_count(self):
        result = _run(self.TEXT, "1h")
        # 09:00 (e1,e2,e3,e4), 10:00 (e5)
        assert len(result["buckets"]) == 2

    def test_15m_error_counts(self):
        result = _run(self.TEXT, "15m")
        total = sum(c for _, c in result["buckets"])
        assert total == 5

    def test_30m_error_counts(self):
        result = _run(self.TEXT, "30m")
        total = sum(c for _, c in result["buckets"])
        assert total == 5

    def test_1h_error_counts(self):
        result = _run(self.TEXT, "1h")
        total = sum(c for _, c in result["buckets"])
        assert total == 5


# ---------------------------------------------------------------------------
# Chronological ordering
# ---------------------------------------------------------------------------

class TestChronologicalOrder:
    def test_buckets_are_in_order(self):
        text = _lines(
            ("2026-10-01 10:00:00", "ERROR", "later"),
            ("2026-10-01 09:00:00", "ERROR", "earlier"),
        )
        result = _run(text, "1h")
        labels = [label for label, _ in result["buckets"]]
        assert labels[0] < labels[1]

    def test_bar_chart_lines_in_order(self):
        text = _lines(
            ("2026-10-01 10:00:00", "ERROR", "later"),
            ("2026-10-01 09:00:00", "ERROR", "earlier"),
        )
        result = _run(text, "1h")
        chart_lines = result["bar_chart"].splitlines()
        assert chart_lines[0].startswith("2026-10-01 09:00")
        assert chart_lines[1].startswith("2026-10-01 10:00")


# ---------------------------------------------------------------------------
# Only ERROR lines counted; INFO and WARN ignored
# ---------------------------------------------------------------------------

class TestOnlyErrors:
    def test_info_lines_not_counted(self):
        text = _lines(
            ("2026-10-01 09:00:00", "INFO", "not an error"),
            ("2026-10-01 09:01:00", "ERROR", "real error"),
        )
        result = _run(text, "15m")
        assert len(result["buckets"]) == 1
        assert result["buckets"][0][1] == 1

    def test_warn_lines_not_counted(self):
        text = _lines(
            ("2026-10-01 09:00:00", "WARN", "warning"),
            ("2026-10-01 09:01:00", "ERROR", "real error"),
        )
        result = _run(text, "15m")
        total = sum(c for _, c in result["buckets"])
        assert total == 1

    def test_no_errors_returns_empty_buckets(self):
        text = _lines(
            ("2026-10-01 09:00:00", "INFO", "all good"),
            ("2026-10-01 09:01:00", "WARN", "mild"),
        )
        result = _run(text, "15m")
        assert result["buckets"] == []
        assert result["bar_chart"] == ""


# ---------------------------------------------------------------------------
# Malformed lines
# ---------------------------------------------------------------------------

class TestMalformedLines:
    def test_malformed_count_reported(self):
        text = (
            "2026-10-01 09:00:00 ERROR real\n"
            "this is bad\n"
            "also bad\n"
        )
        result = _run(text, "15m")
        assert result["malformed_lines"] == 2

    def test_malformed_not_counted_in_buckets(self):
        text = (
            "bad line\n"
            "2026-10-01 09:00:00 ERROR real\n"
        )
        result = _run(text, "15m")
        assert sum(c for _, c in result["buckets"]) == 1

    def test_zero_malformed_clean_input(self):
        text = _lines(("2026-10-01 09:00:00", "ERROR", "clean"))
        result = _run(text, "15m")
        assert result["malformed_lines"] == 0


# ---------------------------------------------------------------------------
# Invalid bucket value
# ---------------------------------------------------------------------------

class TestInvalidBucket:
    def test_invalid_bucket_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid bucket"):
            _run("2026-10-01 09:00:00 ERROR e\n", "2h")

    def test_invalid_bucket_45m_raises(self):
        with pytest.raises(ValueError):
            _run("2026-10-01 09:00:00 ERROR e\n", "45m")

    def test_invalid_bucket_empty_raises(self):
        with pytest.raises(ValueError):
            _run("2026-10-01 09:00:00 ERROR e\n", "")


# ---------------------------------------------------------------------------
# Bar chart format
# ---------------------------------------------------------------------------

class TestBarChart:
    def test_bar_chart_contains_bucket_label(self):
        text = _lines(("2026-10-01 09:00:00", "ERROR", "e"))
        result = _run(text, "1h")
        assert "2026-10-01 09:00" in result["bar_chart"]

    def test_bar_chart_contains_count(self):
        text = _lines(
            ("2026-10-01 09:00:00", "ERROR", "e1"),
            ("2026-10-01 09:01:00", "ERROR", "e2"),
            ("2026-10-01 09:02:00", "ERROR", "e3"),
        )
        result = _run(text, "1h")
        assert "(3)" in result["bar_chart"]

    def test_bar_chart_empty_when_no_errors(self):
        text = _lines(("2026-10-01 09:00:00", "INFO", "x"))
        result = _run(text, "1h")
        assert result["bar_chart"] == ""

    def test_bar_chart_one_line_per_bucket(self):
        text = _lines(
            ("2026-10-01 09:00:00", "ERROR", "a"),
            ("2026-10-01 10:00:00", "ERROR", "b"),
        )
        result = _run(text, "1h")
        assert len(result["bar_chart"].splitlines()) == 2


# ---------------------------------------------------------------------------
# Return structure
# ---------------------------------------------------------------------------

class TestReturnStructure:
    def test_all_keys_present(self):
        result = _run("2026-10-01 09:00:00 ERROR x\n", "15m")
        assert set(result.keys()) == {"bucket", "buckets", "bar_chart", "malformed_lines"}

    def test_bucket_field_echoes_input(self):
        result = _run("2026-10-01 09:00:00 ERROR x\n", "30m")
        assert result["bucket"] == "30m"

    def test_buckets_is_list_of_tuples(self):
        result = _run("2026-10-01 09:00:00 ERROR x\n", "15m")
        assert isinstance(result["buckets"], list)
        assert isinstance(result["buckets"][0], tuple)
