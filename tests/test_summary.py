"""Tests for logscope.commands.summary."""

from __future__ import annotations

import io
from datetime import datetime

import pytest

from logscope.parser import parse_stream
from logscope.commands.summary import summarise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(text: str) -> dict:
    malformed: list[int] = [0]
    entries = parse_stream(io.StringIO(text), malformed)
    return summarise(entries, malformed)


# ---------------------------------------------------------------------------
# Level counts
# ---------------------------------------------------------------------------

class TestLevelCounts:
    def test_counts_info(self):
        result = _run(
            "2026-10-01 09:00:00 INFO a\n"
            "2026-10-01 09:01:00 INFO b\n"
        )
        assert result["level_counts"]["INFO"] == 2

    def test_counts_warn(self):
        result = _run("2026-10-01 09:00:00 WARN disk\n")
        assert result["level_counts"]["WARN"] == 1

    def test_counts_error(self):
        result = _run(
            "2026-10-01 09:00:00 ERROR e1\n"
            "2026-10-01 09:01:00 ERROR e2\n"
            "2026-10-01 09:02:00 ERROR e3\n"
        )
        assert result["level_counts"]["ERROR"] == 3

    def test_zero_counts_when_level_absent(self):
        result = _run("2026-10-01 09:00:00 INFO only info\n")
        assert result["level_counts"]["WARN"] == 0
        assert result["level_counts"]["ERROR"] == 0

    def test_all_levels_present(self):
        text = (
            "2026-10-01 09:00:00 INFO i\n"
            "2026-10-01 09:01:00 WARN w\n"
            "2026-10-01 09:02:00 ERROR e\n"
        )
        result = _run(text)
        assert result["level_counts"] == {"INFO": 1, "WARN": 1, "ERROR": 1}


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------

class TestTimestamps:
    def test_first_timestamp(self):
        text = (
            "2026-10-01 09:00:00 INFO first\n"
            "2026-10-01 09:05:00 INFO second\n"
            "2026-10-01 09:10:00 INFO third\n"
        )
        result = _run(text)
        assert result["first_timestamp"] == datetime(2026, 10, 1, 9, 0, 0)

    def test_last_timestamp(self):
        text = (
            "2026-10-01 09:00:00 INFO first\n"
            "2026-10-01 09:05:00 INFO second\n"
            "2026-10-01 09:10:00 INFO third\n"
        )
        result = _run(text)
        assert result["last_timestamp"] == datetime(2026, 10, 1, 9, 10, 0)

    def test_single_line_first_equals_last(self):
        result = _run("2026-10-01 09:00:00 INFO only\n")
        assert result["first_timestamp"] == result["last_timestamp"]

    def test_timestamps_none_when_no_valid_lines(self):
        result = _run("this is malformed\n")
        assert result["first_timestamp"] is None
        assert result["last_timestamp"] is None

    def test_timestamps_are_datetime_objects(self):
        result = _run("2026-10-01 09:00:00 INFO x\n")
        assert isinstance(result["first_timestamp"], datetime)
        assert isinstance(result["last_timestamp"], datetime)

    def test_out_of_order_timestamps_first(self):
        text = (
            "2026-10-01 09:10:00 INFO later\n"
            "2026-10-01 09:00:00 INFO earlier\n"
        )
        result = _run(text)
        assert result["first_timestamp"] == datetime(2026, 10, 1, 9, 0, 0)

    def test_out_of_order_timestamps_last(self):
        text = (
            "2026-10-01 09:10:00 INFO later\n"
            "2026-10-01 09:00:00 INFO earlier\n"
        )
        result = _run(text)
        assert result["last_timestamp"] == datetime(2026, 10, 1, 9, 10, 0)


# ---------------------------------------------------------------------------
# Top errors
# ---------------------------------------------------------------------------

class TestTopErrors:
    def test_no_errors_returns_empty_list(self):
        result = _run("2026-10-01 09:00:00 INFO all good\n")
        assert result["top_errors"] == []

    def test_single_error_message(self):
        result = _run("2026-10-01 09:00:00 ERROR db failed\n")
        assert result["top_errors"] == [("db failed", 1)]

    def test_fewer_than_five_errors_all_returned(self):
        text = (
            "2026-10-01 09:00:00 ERROR alpha\n"
            "2026-10-01 09:01:00 ERROR beta\n"
            "2026-10-01 09:02:00 ERROR gamma\n"
        )
        result = _run(text)
        messages = [msg for msg, _ in result["top_errors"]]
        assert set(messages) == {"alpha", "beta", "gamma"}
        assert len(result["top_errors"]) == 3

    def test_top_five_limit(self):
        lines = "\n".join(
            f"2026-10-01 09:{i:02d}:00 ERROR error_{i:02d}"
            for i in range(8)
        )
        result = _run(lines + "\n")
        assert len(result["top_errors"]) == 5

    def test_ordered_by_frequency_descending(self):
        text = (
            "2026-10-01 09:00:00 ERROR rare\n"
            "2026-10-01 09:01:00 ERROR common\n"
            "2026-10-01 09:02:00 ERROR common\n"
            "2026-10-01 09:03:00 ERROR common\n"
        )
        result = _run(text)
        assert result["top_errors"][0] == ("common", 3)
        assert result["top_errors"][1] == ("rare", 1)

    def test_tie_broken_lexicographically(self):
        text = (
            "2026-10-01 09:00:00 ERROR zebra\n"
            "2026-10-01 09:01:00 ERROR apple\n"
            "2026-10-01 09:02:00 ERROR mango\n"
        )
        result = _run(text)
        messages = [msg for msg, _ in result["top_errors"]]
        assert messages == ["apple", "mango", "zebra"]

    def test_tie_broken_lexicographically_mixed_counts(self):
        text = (
            "2026-10-01 09:00:00 ERROR zebra\n"
            "2026-10-01 09:01:00 ERROR zebra\n"
            "2026-10-01 09:02:00 ERROR apple\n"
            "2026-10-01 09:03:00 ERROR apple\n"
            "2026-10-01 09:04:00 ERROR unique\n"
        )
        result = _run(text)
        messages = [msg for msg, _ in result["top_errors"]]
        assert messages[0] == "apple"
        assert messages[1] == "zebra"
        assert messages[2] == "unique"

    def test_top_errors_counts_accurate(self):
        text = (
            "2026-10-01 09:00:00 ERROR db\n"
            "2026-10-01 09:01:00 ERROR db\n"
            "2026-10-01 09:02:00 ERROR db\n"
            "2026-10-01 09:03:00 ERROR timeout\n"
            "2026-10-01 09:04:00 ERROR timeout\n"
        )
        result = _run(text)
        top = dict(result["top_errors"])
        assert top["db"] == 3
        assert top["timeout"] == 2

    def test_warn_and_info_not_in_top_errors(self):
        text = (
            "2026-10-01 09:00:00 INFO not an error\n"
            "2026-10-01 09:01:00 WARN also not\n"
            "2026-10-01 09:02:00 ERROR real error\n"
        )
        result = _run(text)
        messages = [msg for msg, _ in result["top_errors"]]
        assert "not an error" not in messages
        assert "also not" not in messages
        assert "real error" in messages


# ---------------------------------------------------------------------------
# Malformed-line count
# ---------------------------------------------------------------------------

class TestMalformedCount:
    def test_no_malformed(self):
        result = _run("2026-10-01 09:00:00 INFO clean\n")
        assert result["malformed_lines"] == 0

    def test_malformed_lines_counted(self):
        text = (
            "2026-10-01 09:00:00 INFO ok\n"
            "this is bad\n"
            "also bad\n"
            "2026-10-01 09:01:00 ERROR real\n"
        )
        result = _run(text)
        assert result["malformed_lines"] == 2

    def test_invalid_calendar_date_counted_as_malformed(self):
        text = (
            "2026-02-30 10:00:00 ERROR impossible\n"
            "2026-10-01 09:00:00 INFO good\n"
        )
        result = _run(text)
        assert result["malformed_lines"] == 1

    def test_all_malformed_zero_valid(self):
        result = _run("bad\nanother bad\n")
        assert result["malformed_lines"] == 2
        assert result["level_counts"] == {"INFO": 0, "WARN": 0, "ERROR": 0}

    def test_empty_input(self):
        result = _run("")
        assert result["malformed_lines"] == 0
        assert result["first_timestamp"] is None
        assert result["last_timestamp"] is None
        assert result["top_errors"] == []


# ---------------------------------------------------------------------------
# Return type / structure
# ---------------------------------------------------------------------------

class TestReturnStructure:
    def test_result_is_dict(self):
        result = _run("2026-10-01 09:00:00 INFO x\n")
        assert isinstance(result, dict)

    def test_all_keys_present(self):
        result = _run("2026-10-01 09:00:00 INFO x\n")
        assert set(result.keys()) == {
            "level_counts",
            "top_errors",
            "first_timestamp",
            "last_timestamp",
            "malformed_lines",
        }

    def test_top_errors_is_list_of_tuples(self):
        result = _run("2026-10-01 09:00:00 ERROR oops\n")
        assert isinstance(result["top_errors"], list)
        assert isinstance(result["top_errors"][0], tuple)
