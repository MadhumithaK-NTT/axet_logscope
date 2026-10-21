"""Tests for logscope.output.json_output and logscope.output.md_output."""

from __future__ import annotations

import io
import json
import types
from datetime import datetime
from pathlib import Path

import pytest

from logscope.parser import parse_stream
from logscope.commands.summary import summarise
from logscope.commands.timeline import timeline
from logscope.commands.grep import GrepResult, grep
from logscope.output.json_output import (
    write_summary_json,
    write_timeline_json,
    write_grep_json,
)
from logscope.output.md_output import (
    report_path,
    write_summary_md,
    write_timeline_md,
    write_grep_md,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _log(text: str) -> io.StringIO:
    return io.StringIO(text)


def _summary_result(text: str) -> dict:
    mal: list[int] = [0]
    return summarise(parse_stream(_log(text), mal), mal)


def _timeline_result(text: str, bucket: str = "1h") -> dict:
    mal: list[int] = [0]
    return timeline(parse_stream(_log(text), mal), mal, bucket)


def _grep_result(text: str, level: str, since: datetime | None = None) -> GrepResult:
    mal: list[int] = [0]
    return grep(parse_stream(_log(text), mal), mal, level, since)


SAMPLE_TEXT = (
    "2026-10-01 09:00:00 INFO Service started\n"
    "2026-10-01 09:01:00 ERROR DB failed\n"
    "2026-10-01 09:02:00 ERROR DB failed\n"
    "2026-10-01 09:03:00 WARN high mem\n"
    "bad line\n"
)


# ---------------------------------------------------------------------------
# report_path helper
# ---------------------------------------------------------------------------

class TestReportPath:
    def test_summary_path(self):
        p = report_path("/logs/app.log", "summary")
        assert p.name == "app_summary_report.md"

    def test_timeline_path(self):
        p = report_path("/logs/app.log", "timeline")
        assert p.name == "app_timeline_report.md"

    def test_grep_path(self):
        p = report_path("/logs/app.log", "grep")
        assert p.name == "app_grep_report.md"

    def test_path_in_same_directory(self):
        p = report_path("/logs/app.log", "summary")
        assert p.parent == Path("/logs")

    def test_stem_used_not_full_name(self):
        p = report_path("myfile.log", "summary")
        assert "myfile" in p.name
        assert ".log" not in p.stem


# ---------------------------------------------------------------------------
# JSON — summary
# ---------------------------------------------------------------------------

class TestWriteSummaryJson:
    def test_produces_valid_json(self):
        buf = io.StringIO()
        write_summary_json(_summary_result(SAMPLE_TEXT), buf)
        parsed = json.loads(buf.getvalue())
        assert isinstance(parsed, dict)

    def test_contains_level_counts(self):
        buf = io.StringIO()
        write_summary_json(_summary_result(SAMPLE_TEXT), buf)
        parsed = json.loads(buf.getvalue())
        assert "level_counts" in parsed
        assert parsed["level_counts"]["INFO"] == 1
        assert parsed["level_counts"]["ERROR"] == 2

    def test_contains_top_errors(self):
        buf = io.StringIO()
        write_summary_json(_summary_result(SAMPLE_TEXT), buf)
        parsed = json.loads(buf.getvalue())
        assert "top_errors" in parsed
        assert isinstance(parsed["top_errors"], list)

    def test_contains_timestamps(self):
        buf = io.StringIO()
        write_summary_json(_summary_result(SAMPLE_TEXT), buf)
        parsed = json.loads(buf.getvalue())
        assert "first_timestamp" in parsed
        assert "last_timestamp" in parsed

    def test_contains_malformed_lines(self):
        buf = io.StringIO()
        write_summary_json(_summary_result(SAMPLE_TEXT), buf)
        parsed = json.loads(buf.getvalue())
        assert parsed["malformed_lines"] == 1

    def test_timestamps_serialised_as_strings(self):
        buf = io.StringIO()
        write_summary_json(_summary_result(SAMPLE_TEXT), buf)
        parsed = json.loads(buf.getvalue())
        assert isinstance(parsed["first_timestamp"], str)
        assert isinstance(parsed["last_timestamp"], str)

    def test_no_valid_lines_null_timestamps(self):
        buf = io.StringIO()
        write_summary_json(_summary_result("bad\n"), buf)
        parsed = json.loads(buf.getvalue())
        assert parsed["first_timestamp"] is None
        assert parsed["last_timestamp"] is None


# ---------------------------------------------------------------------------
# JSON — timeline
# ---------------------------------------------------------------------------

class TestWriteTimelineJson:
    def test_produces_valid_json(self):
        buf = io.StringIO()
        write_timeline_json(_timeline_result(SAMPLE_TEXT), buf)
        parsed = json.loads(buf.getvalue())
        assert isinstance(parsed, dict)

    def test_contains_bucket_field(self):
        buf = io.StringIO()
        write_timeline_json(_timeline_result(SAMPLE_TEXT, "15m"), buf)
        parsed = json.loads(buf.getvalue())
        assert parsed["bucket"] == "15m"

    def test_contains_buckets_list(self):
        buf = io.StringIO()
        write_timeline_json(_timeline_result(SAMPLE_TEXT), buf)
        parsed = json.loads(buf.getvalue())
        assert "buckets" in parsed
        assert isinstance(parsed["buckets"], list)

    def test_contains_bar_chart(self):
        buf = io.StringIO()
        write_timeline_json(_timeline_result(SAMPLE_TEXT), buf)
        parsed = json.loads(buf.getvalue())
        assert "bar_chart" in parsed

    def test_contains_malformed_lines(self):
        buf = io.StringIO()
        write_timeline_json(_timeline_result(SAMPLE_TEXT), buf)
        parsed = json.loads(buf.getvalue())
        assert parsed["malformed_lines"] == 1

    def test_empty_buckets_for_no_errors(self):
        text = "2026-10-01 09:00:00 INFO ok\n"
        buf = io.StringIO()
        write_timeline_json(_timeline_result(text), buf)
        parsed = json.loads(buf.getvalue())
        assert parsed["buckets"] == []


# ---------------------------------------------------------------------------
# JSON — grep (lazy streaming)
# ---------------------------------------------------------------------------

class TestWriteGrepJson:
    def test_produces_valid_json(self):
        buf = io.StringIO()
        write_grep_json(_grep_result(SAMPLE_TEXT, "ERROR"), buf)
        parsed = json.loads(buf.getvalue())
        assert isinstance(parsed, dict)

    def test_contains_matches_array(self):
        buf = io.StringIO()
        write_grep_json(_grep_result(SAMPLE_TEXT, "ERROR"), buf)
        parsed = json.loads(buf.getvalue())
        assert "matches" in parsed
        assert isinstance(parsed["matches"], list)

    def test_matches_count_correct(self):
        buf = io.StringIO()
        write_grep_json(_grep_result(SAMPLE_TEXT, "ERROR"), buf)
        parsed = json.loads(buf.getvalue())
        assert len(parsed["matches"]) == 2

    def test_matches_are_raw_strings(self):
        buf = io.StringIO()
        write_grep_json(_grep_result(SAMPLE_TEXT, "ERROR"), buf)
        parsed = json.loads(buf.getvalue())
        assert all(isinstance(m, str) for m in parsed["matches"])
        assert all("ERROR" in m for m in parsed["matches"])

    def test_malformed_lines_written_after_iterator(self):
        buf = io.StringIO()
        write_grep_json(_grep_result(SAMPLE_TEXT, "ERROR"), buf)
        parsed = json.loads(buf.getvalue())
        assert parsed["malformed_lines"] == 1

    def test_level_field_present(self):
        buf = io.StringIO()
        write_grep_json(_grep_result(SAMPLE_TEXT, "ERROR"), buf)
        parsed = json.loads(buf.getvalue())
        assert parsed["level"] == "ERROR"

    def test_since_null_when_not_set(self):
        buf = io.StringIO()
        write_grep_json(_grep_result(SAMPLE_TEXT, "ERROR"), buf)
        parsed = json.loads(buf.getvalue())
        assert parsed["since"] is None

    def test_since_serialised_when_set(self):
        since = datetime(2026, 10, 1, 9, 0)
        buf = io.StringIO()
        write_grep_json(_grep_result(SAMPLE_TEXT, "ERROR", since), buf)
        parsed = json.loads(buf.getvalue())
        assert parsed["since"] == "2026-10-01 09:00"

    def test_no_matches_produces_empty_array(self):
        text = "2026-10-01 09:00:00 INFO ok\n"
        buf = io.StringIO()
        write_grep_json(_grep_result(text, "ERROR"), buf)
        parsed = json.loads(buf.getvalue())
        assert parsed["matches"] == []

    def test_grep_json_is_lazy(self):
        """write_grep_json must consume matches lazily — verify generator not pre-collected."""
        result = _grep_result(SAMPLE_TEXT, "ERROR")
        # matches must still be a generator before write_grep_json is called
        assert isinstance(result.matches, types.GeneratorType)
        buf = io.StringIO()
        write_grep_json(result, buf)
        # after write the generator is exhausted but the output is still valid JSON
        assert json.loads(buf.getvalue())


# ---------------------------------------------------------------------------
# Markdown — summary
# ---------------------------------------------------------------------------

class TestWriteSummaryMd:
    def test_creates_report_file(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_summary_md(_summary_result(SAMPLE_TEXT), log)
        assert path.exists()

    def test_report_filename(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_summary_md(_summary_result(SAMPLE_TEXT), log)
        assert path.name == "app_summary_report.md"

    def test_contains_level_counts(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_summary_md(_summary_result(SAMPLE_TEXT), log)
        content = path.read_text(encoding="utf-8")
        assert "INFO" in content
        assert "ERROR" in content
        assert "WARN" in content

    def test_contains_top_errors_section(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_summary_md(_summary_result(SAMPLE_TEXT), log)
        content = path.read_text(encoding="utf-8")
        assert "Top Errors" in content
        assert "DB failed" in content

    def test_contains_timestamps(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_summary_md(_summary_result(SAMPLE_TEXT), log)
        content = path.read_text(encoding="utf-8")
        assert "2026-10-01 09:00:00" in content
        assert "2026-10-01 09:03:00" in content

    def test_contains_malformed_count(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_summary_md(_summary_result(SAMPLE_TEXT), log)
        content = path.read_text(encoding="utf-8")
        assert "Malformed" in content
        assert "1" in content

    def test_no_errors_shows_placeholder(self, tmp_path):
        log = tmp_path / "app.log"
        text = "2026-10-01 09:00:00 INFO ok\n"
        log.write_text(text)
        path = write_summary_md(_summary_result(text), log)
        content = path.read_text(encoding="utf-8")
        assert "No errors" in content


# ---------------------------------------------------------------------------
# Markdown — timeline
# ---------------------------------------------------------------------------

class TestWriteTimelineMd:
    def test_creates_report_file(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_timeline_md(_timeline_result(SAMPLE_TEXT), log)
        assert path.exists()

    def test_report_filename(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_timeline_md(_timeline_result(SAMPLE_TEXT), log)
        assert path.name == "app_timeline_report.md"

    def test_contains_bar_chart(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_timeline_md(_timeline_result(SAMPLE_TEXT), log)
        content = path.read_text(encoding="utf-8")
        assert "2026-10-01" in content

    def test_contains_bucket_size(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_timeline_md(_timeline_result(SAMPLE_TEXT, "15m"), log)
        content = path.read_text(encoding="utf-8")
        assert "15m" in content

    def test_contains_malformed_count(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_timeline_md(_timeline_result(SAMPLE_TEXT), log)
        content = path.read_text(encoding="utf-8")
        assert "Malformed" in content

    def test_no_errors_shows_placeholder(self, tmp_path):
        log = tmp_path / "app.log"
        text = "2026-10-01 09:00:00 INFO ok\n"
        log.write_text(text)
        path = write_timeline_md(_timeline_result(text), log)
        content = path.read_text(encoding="utf-8")
        assert "no errors" in content


# ---------------------------------------------------------------------------
# Markdown — grep (lazy streaming)
# ---------------------------------------------------------------------------

class TestWriteGrepMd:
    def test_creates_report_file(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_grep_md(_grep_result(SAMPLE_TEXT, "ERROR"), log)
        assert path.exists()

    def test_report_filename(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_grep_md(_grep_result(SAMPLE_TEXT, "ERROR"), log)
        assert path.name == "app_grep_report.md"

    def test_contains_matching_lines(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_grep_md(_grep_result(SAMPLE_TEXT, "ERROR"), log)
        content = path.read_text(encoding="utf-8")
        assert "DB failed" in content

    def test_contains_level(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_grep_md(_grep_result(SAMPLE_TEXT, "ERROR"), log)
        content = path.read_text(encoding="utf-8")
        assert "ERROR" in content

    def test_contains_malformed_count_after_matches(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_grep_md(_grep_result(SAMPLE_TEXT, "ERROR"), log)
        content = path.read_text(encoding="utf-8")
        assert "Malformed" in content
        # malformed section must appear after matching lines section
        assert content.index("Malformed") > content.index("Matching Lines")

    def test_since_shown_in_report(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        since = datetime(2026, 10, 1, 9, 1)
        path = write_grep_md(_grep_result(SAMPLE_TEXT, "ERROR", since), log)
        content = path.read_text(encoding="utf-8")
        assert "2026-10-01 09:01" in content

    def test_no_matches_produces_empty_code_block(self, tmp_path):
        log = tmp_path / "app.log"
        text = "2026-10-01 09:00:00 INFO ok\n"
        log.write_text(text)
        path = write_grep_md(_grep_result(text, "ERROR"), log)
        content = path.read_text(encoding="utf-8")
        assert "```" in content
        assert "Malformed" in content

    def test_grep_md_is_lazy(self, tmp_path):
        """write_grep_md must consume matches lazily — generator not pre-collected."""
        result = _grep_result(SAMPLE_TEXT, "ERROR")
        assert isinstance(result.matches, types.GeneratorType)
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        write_grep_md(result, log)
        # After write the generator is exhausted; calling list() on it gives empty.
        assert list(result.matches) == []

    def test_raw_lines_written_verbatim(self, tmp_path):
        log = tmp_path / "app.log"
        log.write_text(SAMPLE_TEXT)
        path = write_grep_md(_grep_result(SAMPLE_TEXT, "ERROR"), log)
        content = path.read_text(encoding="utf-8")
        assert "2026-10-01 09:01:00 ERROR DB failed" in content
        assert "2026-10-01 09:02:00 ERROR DB failed" in content
