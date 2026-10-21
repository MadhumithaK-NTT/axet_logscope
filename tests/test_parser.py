"""Tests for logscope.parser — LogEntry dataclass and parse_stream generator."""

from __future__ import annotations

import io
from datetime import datetime

import pytest

from logscope.parser import LogEntry, parse_stream


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stream(text: str) -> io.StringIO:
    return io.StringIO(text)


def _collect(text: str) -> tuple[list[LogEntry], int]:
    """Return (entries, malformed_count) for *text*."""
    malformed: list[int] = [0]
    entries = list(parse_stream(_stream(text), malformed))
    return entries, malformed[0]


# ---------------------------------------------------------------------------
# Valid lines
# ---------------------------------------------------------------------------

class TestValidLines:
    def test_info_line_parses(self):
        entries, bad = _collect("2026-10-01 09:15:00 INFO Service started\n")
        assert len(entries) == 1
        assert bad == 0
        e = entries[0]
        assert e.level == "INFO"
        assert e.message == "Service started"

    def test_warn_line_parses(self):
        entries, bad = _collect("2026-10-01 09:17:05 WARN Disk usage above 80%\n")
        assert len(entries) == 1
        assert entries[0].level == "WARN"

    def test_error_line_parses(self):
        entries, bad = _collect("2026-10-01 09:16:12 ERROR Database connection failed\n")
        assert len(entries) == 1
        assert entries[0].level == "ERROR"

    def test_timestamp_is_datetime_object(self):
        entries, _ = _collect("2026-10-01 09:15:00 INFO Service started\n")
        assert isinstance(entries[0].timestamp, datetime)

    def test_timestamp_fields_correct(self):
        entries, _ = _collect("2026-10-01 09:15:00 INFO Service started\n")
        ts = entries[0].timestamp
        assert ts.year == 2026
        assert ts.month == 10
        assert ts.day == 1
        assert ts.hour == 9
        assert ts.minute == 15
        assert ts.second == 0

    def test_raw_preserves_original_line(self):
        line = "2026-10-01 09:15:00 INFO Service started"
        entries, _ = _collect(line + "\n")
        assert entries[0].raw == line

    def test_raw_preserved_without_trailing_newline(self):
        line = "2026-10-01 09:15:00 INFO No newline at end"
        entries, _ = _collect(line)
        assert entries[0].raw == line

    def test_message_with_spaces(self):
        entries, _ = _collect("2026-10-01 09:15:00 ERROR Could not connect to host 10.0.0.1\n")
        assert entries[0].message == "Could not connect to host 10.0.0.1"

    def test_logentry_is_frozen(self):
        entries, _ = _collect("2026-10-01 09:15:00 INFO frozen check\n")
        with pytest.raises((AttributeError, TypeError)):
            entries[0].level = "WARN"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Malformed lines
# ---------------------------------------------------------------------------

class TestMalformedLines:
    def test_empty_line_is_malformed(self):
        _, bad = _collect("\n")
        assert bad == 1

    def test_missing_level_is_malformed(self):
        _, bad = _collect("2026-10-01 09:15:00 Service started\n")
        assert bad == 1

    def test_wrong_level_is_malformed(self):
        _, bad = _collect("2026-10-01 09:15:00 DEBUG Something\n")
        assert bad == 1

    def test_bad_date_format_is_malformed(self):
        _, bad = _collect("01-10-2026 09:15:00 INFO Bad date format\n")
        assert bad == 1

    def test_missing_timestamp_is_malformed(self):
        _, bad = _collect("INFO Service started\n")
        assert bad == 1

    def test_plain_text_is_malformed(self):
        _, bad = _collect("this is just free text\n")
        assert bad == 1

    def test_invalid_calendar_date_is_malformed_not_exception(self):
        """Feb 30 matches the regex but is not a real date — must be malformed."""
        _, bad = _collect("2026-02-30 10:00:00 ERROR impossible date\n")
        assert bad == 1

    def test_invalid_calendar_date_yields_no_entries(self):
        entries, _ = _collect("2026-02-30 10:00:00 ERROR impossible date\n")
        assert entries == []

    def test_invalid_month_13_is_malformed(self):
        _, bad = _collect("2026-13-01 10:00:00 INFO bad month\n")
        assert bad == 1

    def test_invalid_hour_25_is_malformed(self):
        _, bad = _collect("2026-10-01 25:00:00 INFO bad hour\n")
        assert bad == 1


# ---------------------------------------------------------------------------
# Mixed input
# ---------------------------------------------------------------------------

class TestMixedInput:
    MIXED = (
        "2026-10-01 09:15:00 INFO Service started\n"
        "this line is malformed\n"
        "2026-10-01 09:16:12 ERROR Database connection failed\n"
        "2026-02-30 10:00:00 WARN impossible date\n"
        "2026-10-01 09:17:05 WARN Disk usage above 80%\n"
        "\n"
    )

    def test_correct_entry_count(self):
        entries, _ = _collect(self.MIXED)
        assert len(entries) == 3

    def test_correct_malformed_count(self):
        _, bad = _collect(self.MIXED)
        assert bad == 3

    def test_entries_in_order(self):
        entries, _ = _collect(self.MIXED)
        assert entries[0].level == "INFO"
        assert entries[1].level == "ERROR"
        assert entries[2].level == "WARN"

    def test_malformed_count_starts_at_zero(self):
        malformed: list[int] = [0]
        list(parse_stream(_stream("2026-10-01 09:15:00 INFO ok\n"), malformed))
        assert malformed[0] == 0


# ---------------------------------------------------------------------------
# Streaming behaviour — no list accumulation inside the generator
# ---------------------------------------------------------------------------

class TestStreaming:
    def test_generator_is_lazy(self):
        """parse_stream must return a generator, not a list."""
        import types
        malformed: list[int] = [0]
        result = parse_stream(_stream("2026-10-01 09:15:00 INFO test\n"), malformed)
        assert isinstance(result, types.GeneratorType)

    def test_malformed_count_updates_during_iteration(self):
        """Counter increments as we iterate, not only after exhaustion."""
        text = (
            "bad line\n"
            "2026-10-01 09:15:00 INFO ok\n"
            "another bad line\n"
        )
        malformed: list[int] = [0]
        gen = parse_stream(_stream(text), malformed)
        next(gen)           # consumes "bad line" (malformed) then yields INFO
        assert malformed[0] == 1
        with pytest.raises(StopIteration):
            next(gen)       # consumes "another bad line"
        assert malformed[0] == 2


# ---------------------------------------------------------------------------
# sample.log smoke test
# ---------------------------------------------------------------------------

class TestSampleLog:
    FIXTURE = "tests/fixtures/sample.log"

    def test_sample_log_parses_without_exception(self):
        with open(self.FIXTURE, encoding="utf-8") as f:
            malformed: list[int] = [0]
            entries = list(parse_stream(f, malformed))
        assert len(entries) == 10
        assert malformed[0] == 1

    def test_sample_log_first_timestamp(self):
        with open(self.FIXTURE, encoding="utf-8") as f:
            malformed: list[int] = [0]
            entries = list(parse_stream(f, malformed))
        assert entries[0].timestamp == datetime(2026, 10, 1, 9, 15, 0)

    def test_sample_log_last_timestamp(self):
        with open(self.FIXTURE, encoding="utf-8") as f:
            malformed: list[int] = [0]
            entries = list(parse_stream(f, malformed))
        assert entries[-1].timestamp == datetime(2026, 10, 1, 9, 22, 30)
