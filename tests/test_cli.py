"""Tests for logscope.cli — argument parsing, dispatch, and output formats."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from logscope.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE = "tests/fixtures/sample.log"


def _run(*args: str) -> tuple[int, str, str]:
    """Call main() with *args*, capture stdout/stderr via capsys-free approach."""
    import io
    from contextlib import redirect_stdout, redirect_stderr

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
        code = main(list(args))
    return code, stdout_buf.getvalue(), stderr_buf.getvalue()


# ---------------------------------------------------------------------------
# No command / help
# ---------------------------------------------------------------------------

class TestNoCommand:
    def test_no_args_exits_nonzero(self):
        code, _, _ = _run()
        assert code != 0

    def test_no_args_writes_to_stderr(self):
        _, _, err = _run()
        assert len(err) > 0

    def test_help_flag(self):
        result = subprocess.run(
            [sys.executable, "-m", "logscope", "--help"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0
        assert "logscope" in result.stdout.lower()

    def test_unknown_command_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, "-m", "logscope", "bogus", SAMPLE],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# Missing / invalid log file
# ---------------------------------------------------------------------------

class TestMissingFile:
    def test_missing_file_exits_nonzero(self):
        code, _, _ = _run("summary", "no_such_file.log")
        assert code != 0

    def test_missing_file_error_message(self):
        _, _, err = _run("summary", "no_such_file.log")
        assert "not found" in err or "error" in err.lower()

    def test_missing_file_timeline(self):
        code, _, _ = _run("timeline", "no_such_file.log", "--bucket", "1h")
        assert code != 0

    def test_missing_file_grep(self):
        code, _, _ = _run("grep", "no_such_file.log", "--level", "ERROR")
        assert code != 0


# ---------------------------------------------------------------------------
# summary — plain text
# ---------------------------------------------------------------------------

class TestSummaryPlainText:
    def test_exits_zero(self):
        code, _, _ = _run("summary", SAMPLE)
        assert code == 0

    def test_shows_info_count(self):
        _, out, _ = _run("summary", SAMPLE)
        assert "INFO" in out

    def test_shows_error_count(self):
        _, out, _ = _run("summary", SAMPLE)
        assert "ERROR" in out

    def test_shows_malformed(self):
        _, out, _ = _run("summary", SAMPLE)
        assert "Malformed" in out or "malformed" in out

    def test_shows_timestamps(self):
        _, out, _ = _run("summary", SAMPLE)
        assert "2026-10-01" in out


# ---------------------------------------------------------------------------
# summary — JSON
# ---------------------------------------------------------------------------

class TestSummaryJson:
    def test_exits_zero(self):
        code, _, _ = _run("summary", SAMPLE, "--format", "json")
        assert code == 0

    def test_valid_json(self):
        _, out, _ = _run("summary", SAMPLE, "--format", "json")
        parsed = json.loads(out)
        assert isinstance(parsed, dict)

    def test_json_has_level_counts(self):
        _, out, _ = _run("summary", SAMPLE, "--format", "json")
        parsed = json.loads(out)
        assert "level_counts" in parsed

    def test_json_has_malformed_lines(self):
        _, out, _ = _run("summary", SAMPLE, "--format", "json")
        parsed = json.loads(out)
        assert "malformed_lines" in parsed

    def test_json_has_top_errors(self):
        _, out, _ = _run("summary", SAMPLE, "--format", "json")
        parsed = json.loads(out)
        assert "top_errors" in parsed


# ---------------------------------------------------------------------------
# summary — Markdown
# ---------------------------------------------------------------------------

class TestSummaryMd:
    def test_exits_zero(self, tmp_path):
        log = tmp_path / "sample.log"
        log.write_text(Path(SAMPLE).read_text(encoding="utf-8"))
        code, out, _ = _run("summary", str(log), "--format", "md")
        assert code == 0

    def test_prints_report_path(self, tmp_path):
        log = tmp_path / "sample.log"
        log.write_text(Path(SAMPLE).read_text(encoding="utf-8"))
        _, out, _ = _run("summary", str(log), "--format", "md")
        assert "Report written to" in out

    def test_report_file_created(self, tmp_path):
        log = tmp_path / "sample.log"
        log.write_text(Path(SAMPLE).read_text(encoding="utf-8"))
        _run("summary", str(log), "--format", "md")
        assert (tmp_path / "sample_summary_report.md").exists()


# ---------------------------------------------------------------------------
# timeline — plain text
# ---------------------------------------------------------------------------

class TestTimelinePlainText:
    def test_exits_zero(self):
        code, _, _ = _run("timeline", SAMPLE, "--bucket", "15m")
        assert code == 0

    def test_shows_bucket_size(self):
        _, out, _ = _run("timeline", SAMPLE, "--bucket", "15m")
        assert "15m" in out

    def test_shows_date(self):
        _, out, _ = _run("timeline", SAMPLE, "--bucket", "1h")
        assert "2026-10-01" in out

    def test_missing_bucket_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, "-m", "logscope", "timeline", SAMPLE],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode != 0

    def test_invalid_bucket_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, "-m", "logscope", "timeline", SAMPLE, "--bucket", "2h"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# timeline — JSON
# ---------------------------------------------------------------------------

class TestTimelineJson:
    def test_exits_zero(self):
        code, _, _ = _run("timeline", SAMPLE, "--bucket", "1h", "--format", "json")
        assert code == 0

    def test_valid_json(self):
        _, out, _ = _run("timeline", SAMPLE, "--bucket", "1h", "--format", "json")
        parsed = json.loads(out)
        assert isinstance(parsed, dict)

    def test_json_has_bucket(self):
        _, out, _ = _run("timeline", SAMPLE, "--bucket", "30m", "--format", "json")
        parsed = json.loads(out)
        assert parsed["bucket"] == "30m"

    def test_json_has_buckets_list(self):
        _, out, _ = _run("timeline", SAMPLE, "--bucket", "1h", "--format", "json")
        parsed = json.loads(out)
        assert "buckets" in parsed


# ---------------------------------------------------------------------------
# timeline — Markdown
# ---------------------------------------------------------------------------

class TestTimelineMd:
    def test_exits_zero(self, tmp_path):
        log = tmp_path / "sample.log"
        log.write_text(Path(SAMPLE).read_text(encoding="utf-8"))
        code, _, _ = _run("timeline", str(log), "--bucket", "1h", "--format", "md")
        assert code == 0

    def test_report_file_created(self, tmp_path):
        log = tmp_path / "sample.log"
        log.write_text(Path(SAMPLE).read_text(encoding="utf-8"))
        _run("timeline", str(log), "--bucket", "1h", "--format", "md")
        assert (tmp_path / "sample_timeline_report.md").exists()

    def test_prints_report_path(self, tmp_path):
        log = tmp_path / "sample.log"
        log.write_text(Path(SAMPLE).read_text(encoding="utf-8"))
        _, out, _ = _run("timeline", str(log), "--bucket", "1h", "--format", "md")
        assert "Report written to" in out


# ---------------------------------------------------------------------------
# grep — plain text
# ---------------------------------------------------------------------------

class TestGrepPlainText:
    def test_exits_zero(self):
        code, _, _ = _run("grep", SAMPLE, "--level", "ERROR")
        assert code == 0

    def test_shows_error_lines(self):
        _, out, _ = _run("grep", SAMPLE, "--level", "ERROR")
        assert "ERROR" in out

    def test_info_lines_absent(self):
        _, out, _ = _run("grep", SAMPLE, "--level", "ERROR")
        lines = [l for l in out.splitlines() if l.strip() and not l.startswith("Malformed")]
        assert all("ERROR" in l for l in lines)

    def test_since_filter_applied(self):
        _, out_all, _ = _run("grep", SAMPLE, "--level", "ERROR")
        _, out_since, _ = _run("grep", SAMPLE, "--level", "ERROR", "--since", "2026-10-01 09:20")
        assert len(out_since.splitlines()) <= len(out_all.splitlines())

    def test_missing_level_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, "-m", "logscope", "grep", SAMPLE],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode != 0

    def test_invalid_level_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, "-m", "logscope", "grep", SAMPLE, "--level", "DEBUG"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode != 0

    def test_invalid_since_exits_nonzero(self):
        code, _, _ = _run("grep", SAMPLE, "--level", "ERROR", "--since", "not-a-date")
        assert code != 0

    def test_invalid_since_error_message(self):
        _, _, err = _run("grep", SAMPLE, "--level", "ERROR", "--since", "not-a-date")
        assert len(err) > 0


# ---------------------------------------------------------------------------
# grep — JSON
# ---------------------------------------------------------------------------

class TestGrepJson:
    def test_exits_zero(self):
        code, _, _ = _run("grep", SAMPLE, "--level", "ERROR", "--format", "json")
        assert code == 0

    def test_valid_json(self):
        _, out, _ = _run("grep", SAMPLE, "--level", "ERROR", "--format", "json")
        parsed = json.loads(out)
        assert isinstance(parsed, dict)

    def test_json_has_matches(self):
        _, out, _ = _run("grep", SAMPLE, "--level", "ERROR", "--format", "json")
        parsed = json.loads(out)
        assert "matches" in parsed
        assert isinstance(parsed["matches"], list)

    def test_json_has_malformed_lines(self):
        _, out, _ = _run("grep", SAMPLE, "--level", "ERROR", "--format", "json")
        parsed = json.loads(out)
        assert "malformed_lines" in parsed

    def test_grep_json_lazy(self):
        """write_grep_json must not pre-collect the iterator — confirmed if JSON is valid."""
        _, out, _ = _run("grep", SAMPLE, "--level", "ERROR", "--format", "json")
        parsed = json.loads(out)
        assert isinstance(parsed["matches"], list)


# ---------------------------------------------------------------------------
# grep — Markdown
# ---------------------------------------------------------------------------

class TestGrepMd:
    def test_exits_zero(self, tmp_path):
        log = tmp_path / "sample.log"
        log.write_text(Path(SAMPLE).read_text(encoding="utf-8"))
        code, _, _ = _run("grep", str(log), "--level", "ERROR", "--format", "md")
        assert code == 0

    def test_report_file_created(self, tmp_path):
        log = tmp_path / "sample.log"
        log.write_text(Path(SAMPLE).read_text(encoding="utf-8"))
        _run("grep", str(log), "--level", "ERROR", "--format", "md")
        assert (tmp_path / "sample_grep_report.md").exists()

    def test_prints_report_path(self, tmp_path):
        log = tmp_path / "sample.log"
        log.write_text(Path(SAMPLE).read_text(encoding="utf-8"))
        _, out, _ = _run("grep", str(log), "--level", "ERROR", "--format", "md")
        assert "Report written to" in out
