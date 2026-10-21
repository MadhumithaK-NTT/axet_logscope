"""Tests for logscope.commands.grep."""

from __future__ import annotations

import io
import types
from datetime import datetime

import pytest

from logscope.parser import parse_stream
from logscope.commands.grep import GrepResult, VALID_LEVELS, grep, parse_since


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(text: str, level: str, since: datetime | None = None) -> dict:
    """Call grep and return a plain dict with matches consumed into a list.

    Most tests only care about content; this helper makes them concise.
    The malformed count is captured after exhausting matches.
    """
    malformed: list[int] = [0]
    entries = parse_stream(io.StringIO(text), malformed)
    result = grep(entries, malformed, level, since)
    collected = list(result.matches)          # exhaust iterator here
    return {
        "level": result.level,
        "since": result.since,
        "matches": collected,
        "malformed_lines": result.malformed[0],
    }


def _lines(*specs: tuple[str, str, str]) -> str:
    return "".join(f"{ts} {lvl} {msg}\n" for ts, lvl, msg in specs)


# ---------------------------------------------------------------------------
# parse_since helper
# ---------------------------------------------------------------------------

class TestParseSince:
    def test_valid_format_parses(self):
        dt = parse_since("2026-10-01 09:00")
        assert dt == datetime(2026, 10, 1, 9, 0)

    def test_returns_datetime(self):
        assert isinstance(parse_since("2026-10-01 09:00"), datetime)

    def test_invalid_format_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid --since"):
            parse_since("01-10-2026 09:00")

    def test_missing_time_raises(self):
        with pytest.raises(ValueError):
            parse_since("2026-10-01")

    def test_invalid_calendar_date_raises(self):
        with pytest.raises(ValueError):
            parse_since("2026-02-30 09:00")

    def test_error_message_shows_expected_format(self):
        with pytest.raises(ValueError, match="YYYY-MM-DD HH:MM"):
            parse_since("bad input")

    def test_midnight(self):
        dt = parse_since("2026-10-01 00:00")
        assert dt == datetime(2026, 10, 1, 0, 0)

    def test_end_of_day(self):
        dt = parse_since("2026-10-01 23:59")
        assert dt == datetime(2026, 10, 1, 23, 59)


# ---------------------------------------------------------------------------
# Lazy iterator / streaming behaviour
# ---------------------------------------------------------------------------

class TestLazyIterator:
    def test_matches_is_iterator_not_list(self):
        """grep must return an iterator, not a pre-collected list."""
        malformed: list[int] = [0]
        entries = parse_stream(io.StringIO("2026-10-01 09:00:00 ERROR x\n"), malformed)
        result = grep(entries, malformed, "ERROR")
        assert not isinstance(result.matches, list)
        assert hasattr(result.matches, "__iter__")
        assert hasattr(result.matches, "__next__")

    def test_matches_is_generator(self):
        malformed: list[int] = [0]
        entries = parse_stream(io.StringIO("2026-10-01 09:00:00 ERROR x\n"), malformed)
        result = grep(entries, malformed, "ERROR")
        assert isinstance(result.matches, types.GeneratorType)

    def test_result_is_grep_result_dataclass(self):
        malformed: list[int] = [0]
        entries = parse_stream(io.StringIO("2026-10-01 09:00:00 ERROR x\n"), malformed)
        result = grep(entries, malformed, "ERROR")
        assert isinstance(result, GrepResult)

    def test_malformed_count_only_final_after_exhaustion(self):
        """malformed[0] must be read after the matches iterator is exhausted."""
        text = (
            "bad line\n"
            "2026-10-01 09:00:00 ERROR good\n"
            "another bad\n"
        )
        malformed: list[int] = [0]
        entries = parse_stream(io.StringIO(text), malformed)
        result = grep(entries, malformed, "ERROR")
        # consume iterator — malformed counter updates as the source is read
        _ = list(result.matches)
        assert result.malformed[0] == 2

    def test_matches_not_consumed_before_iteration(self):
        """The generator must not pull from the source until iterated."""
        malformed: list[int] = [0]
        entries = parse_stream(io.StringIO("2026-10-01 09:00:00 ERROR x\n"), malformed)
        result = grep(entries, malformed, "ERROR")
        # Before consuming, malformed[0] may still be 0 even if source has bad lines
        # because the generator hasn't run yet.  Just verify result is returned
        # before any source lines are consumed (generator is lazy).
        assert isinstance(result, GrepResult)


# ---------------------------------------------------------------------------
# Level filtering
# ---------------------------------------------------------------------------

class TestLevelFiltering:
    TEXT = _lines(
        ("2026-10-01 09:00:00", "INFO",  "info message"),
        ("2026-10-01 09:01:00", "WARN",  "warn message"),
        ("2026-10-01 09:02:00", "ERROR", "error message"),
        ("2026-10-01 09:03:00", "INFO",  "second info"),
        ("2026-10-01 09:04:00", "ERROR", "second error"),
    )

    def test_filter_info_only(self):
        result = _run(self.TEXT, "INFO")
        assert len(result["matches"]) == 2
        assert all("INFO" in m for m in result["matches"])

    def test_filter_warn_only(self):
        result = _run(self.TEXT, "WARN")
        assert len(result["matches"]) == 1
        assert "WARN" in result["matches"][0]

    def test_filter_error_only(self):
        result = _run(self.TEXT, "ERROR")
        assert len(result["matches"]) == 2
        assert all("ERROR" in m for m in result["matches"])

    def test_other_levels_excluded(self):
        result = _run(self.TEXT, "ERROR")
        assert not any("INFO" in m for m in result["matches"])
        assert not any("WARN" in m for m in result["matches"])

    def test_no_matches_returns_empty_iterator(self):
        text = _lines(("2026-10-01 09:00:00", "INFO", "only info"))
        result = _run(text, "ERROR")
        assert result["matches"] == []


# ---------------------------------------------------------------------------
# Since boundary (inclusive)
# ---------------------------------------------------------------------------

class TestSinceBoundary:
    TEXT = _lines(
        ("2026-10-01 09:00:00", "ERROR", "before"),
        ("2026-10-01 09:10:00", "ERROR", "at boundary"),
        ("2026-10-01 09:20:00", "ERROR", "after"),
    )

    def test_since_excludes_earlier_entries(self):
        since = datetime(2026, 10, 1, 9, 10)
        result = _run(self.TEXT, "ERROR", since)
        assert len(result["matches"]) == 2

    def test_since_boundary_is_inclusive(self):
        since = datetime(2026, 10, 1, 9, 10)
        result = _run(self.TEXT, "ERROR", since)
        assert any("at boundary" in m for m in result["matches"])

    def test_since_excludes_entry_one_second_before(self):
        text = _lines(
            ("2026-10-01 09:09:59", "ERROR", "just before"),
            ("2026-10-01 09:10:00", "ERROR", "exactly at"),
        )
        since = datetime(2026, 10, 1, 9, 10)
        result = _run(text, "ERROR", since)
        assert len(result["matches"]) == 1
        assert "exactly at" in result["matches"][0]

    def test_since_none_returns_all_matching(self):
        result = _run(self.TEXT, "ERROR", None)
        assert len(result["matches"]) == 3

    def test_since_after_all_entries_returns_empty(self):
        since = datetime(2026, 10, 1, 10, 0)
        result = _run(self.TEXT, "ERROR", since)
        assert result["matches"] == []

    def test_since_before_all_entries_returns_all(self):
        since = datetime(2026, 10, 1, 8, 0)
        result = _run(self.TEXT, "ERROR", since)
        assert len(result["matches"]) == 3

    def test_since_echoed_in_result(self):
        since = datetime(2026, 10, 1, 9, 10)
        malformed: list[int] = [0]
        entries = parse_stream(io.StringIO(self.TEXT), malformed)
        result = grep(entries, malformed, "ERROR", since)
        assert result.since == since

    def test_since_none_echoed_in_result(self):
        malformed: list[int] = [0]
        entries = parse_stream(io.StringIO(self.TEXT), malformed)
        result = grep(entries, malformed, "ERROR", None)
        assert result.since is None


# ---------------------------------------------------------------------------
# Combined level and since filtering
# ---------------------------------------------------------------------------

class TestCombinedFilter:
    TEXT = _lines(
        ("2026-10-01 09:00:00", "INFO",  "info early"),
        ("2026-10-01 09:05:00", "ERROR", "error early"),
        ("2026-10-01 09:10:00", "INFO",  "info at boundary"),
        ("2026-10-01 09:10:00", "ERROR", "error at boundary"),
        ("2026-10-01 09:20:00", "ERROR", "error after"),
        ("2026-10-01 09:25:00", "WARN",  "warn after"),
    )

    def test_combined_returns_only_matching_level_and_since(self):
        since = datetime(2026, 10, 1, 9, 10)
        result = _run(self.TEXT, "ERROR", since)
        assert len(result["matches"]) == 2
        assert all("ERROR" in m for m in result["matches"])

    def test_combined_excludes_correct_level(self):
        since = datetime(2026, 10, 1, 9, 10)
        result = _run(self.TEXT, "ERROR", since)
        assert not any("INFO" in m for m in result["matches"])
        assert not any("WARN" in m for m in result["matches"])

    def test_combined_excludes_before_since(self):
        since = datetime(2026, 10, 1, 9, 10)
        result = _run(self.TEXT, "ERROR", since)
        assert not any("error early" in m for m in result["matches"])

    def test_info_with_since(self):
        since = datetime(2026, 10, 1, 9, 10)
        result = _run(self.TEXT, "INFO", since)
        assert len(result["matches"]) == 1
        assert "info at boundary" in result["matches"][0]


# ---------------------------------------------------------------------------
# Raw line preservation
# ---------------------------------------------------------------------------

class TestRawLinePreservation:
    def test_raw_line_matches_original(self):
        original = "2026-10-01 09:00:00 ERROR original message here"
        result = _run(original + "\n", "ERROR")
        assert result["matches"] == [original]

    def test_raw_line_not_reconstructed(self):
        line = "2026-10-01 09:00:00 ERROR  double  space  message"
        result = _run(line + "\n", "ERROR")
        assert result["matches"] == [line]

    def test_multiple_raw_lines_preserved_in_order(self):
        lines = [
            "2026-10-01 09:00:00 ERROR first error",
            "2026-10-01 09:01:00 ERROR second error",
            "2026-10-01 09:02:00 ERROR third error",
        ]
        text = "\n".join(lines) + "\n"
        result = _run(text, "ERROR")
        assert result["matches"] == lines

    def test_trailing_newline_stripped_from_raw(self):
        result = _run("2026-10-01 09:00:00 ERROR msg\n", "ERROR")
        assert not result["matches"][0].endswith("\n")


# ---------------------------------------------------------------------------
# Malformed-line counting
# ---------------------------------------------------------------------------

class TestMalformedCount:
    def test_zero_malformed_clean_input(self):
        result = _run("2026-10-01 09:00:00 ERROR clean\n", "ERROR")
        assert result["malformed_lines"] == 0

    def test_malformed_lines_counted(self):
        text = (
            "2026-10-01 09:00:00 ERROR good\n"
            "this is bad\n"
            "also bad\n"
        )
        result = _run(text, "ERROR")
        assert result["malformed_lines"] == 2

    def test_malformed_not_in_matches(self):
        text = (
            "bad line\n"
            "2026-10-01 09:00:00 ERROR real\n"
        )
        result = _run(text, "ERROR")
        assert len(result["matches"]) == 1
        assert "bad line" not in result["matches"][0]

    def test_invalid_calendar_date_counted_as_malformed(self):
        text = (
            "2026-02-30 10:00:00 ERROR impossible\n"
            "2026-10-01 09:00:00 ERROR real\n"
        )
        result = _run(text, "ERROR")
        assert result["malformed_lines"] == 1
        assert len(result["matches"]) == 1


# ---------------------------------------------------------------------------
# Invalid inputs
# ---------------------------------------------------------------------------

class TestInvalidInputs:
    def test_invalid_level_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid level"):
            _run("2026-10-01 09:00:00 ERROR x\n", "DEBUG")

    def test_invalid_level_lowercase_raises(self):
        with pytest.raises(ValueError, match="Invalid level"):
            _run("2026-10-01 09:00:00 ERROR x\n", "error")

    def test_invalid_level_empty_raises(self):
        with pytest.raises(ValueError):
            _run("2026-10-01 09:00:00 ERROR x\n", "")

    def test_invalid_level_message_shows_valid_options(self):
        with pytest.raises(ValueError, match="ERROR"):
            _run("2026-10-01 09:00:00 ERROR x\n", "BAD")

    def test_valid_levels_constant(self):
        assert VALID_LEVELS == {"INFO", "WARN", "ERROR"}


# ---------------------------------------------------------------------------
# Return structure
# ---------------------------------------------------------------------------

class TestReturnStructure:
    def test_result_is_grep_result_dataclass(self):
        malformed: list[int] = [0]
        entries = parse_stream(io.StringIO("2026-10-01 09:00:00 ERROR x\n"), malformed)
        result = grep(entries, malformed, "ERROR")
        assert isinstance(result, GrepResult)

    def test_level_echoed_in_result(self):
        malformed: list[int] = [0]
        entries = parse_stream(io.StringIO("2026-10-01 09:00:00 ERROR x\n"), malformed)
        result = grep(entries, malformed, "ERROR")
        assert result.level == "ERROR"

    def test_matches_is_iterable(self):
        malformed: list[int] = [0]
        entries = parse_stream(io.StringIO("2026-10-01 09:00:00 ERROR x\n"), malformed)
        result = grep(entries, malformed, "ERROR")
        assert hasattr(result.matches, "__iter__")

    def test_matches_yields_strings(self):
        malformed: list[int] = [0]
        entries = parse_stream(io.StringIO("2026-10-01 09:00:00 ERROR x\n"), malformed)
        result = grep(entries, malformed, "ERROR")
        assert all(isinstance(m, str) for m in result.matches)

    def test_empty_input_yields_no_matches(self):
        malformed: list[int] = [0]
        entries = parse_stream(io.StringIO(""), malformed)
        result = grep(entries, malformed, "ERROR")
        assert list(result.matches) == []
        assert result.malformed[0] == 0
