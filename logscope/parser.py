"""Streaming log parser for Logscope.

Public API
----------
LogEntry      - frozen dataclass representing one valid log line.
parse_stream  - generator; yields LogEntry values and tracks malformed lines
                via a shared one-element list counter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Generator, IO

# Compiled once at import time.
_LINE_RE: re.Pattern[str] = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|WARN|ERROR) (.+)$"
)


@dataclass(frozen=True)
class LogEntry:
    """A single successfully parsed log line."""

    timestamp: datetime
    level: str   # "INFO" | "WARN" | "ERROR"
    message: str
    raw: str     # original line text, preserved for grep output


def parse_stream(
    file_obj: IO[str],
    malformed: list[int],
) -> Generator[LogEntry, None, None]:
    """Yield :class:`LogEntry` for every valid line in *file_obj*.

    Parameters
    ----------
    file_obj:
        Any text-mode file-like object (``open(...)`` or ``io.StringIO``).
    malformed:
        A one-element ``[int]`` list.  The parser increments ``malformed[0]``
        for every line that cannot be parsed (regex miss **or** invalid
        calendar date).  Callers read the count after exhausting the generator.

    The parser never raises on bad input; all errors increment the counter and
    continue.
    """
    for raw_line in file_obj:
        line = raw_line.rstrip("\n").rstrip("\r")
        match = _LINE_RE.match(line)
        if match is None:
            malformed[0] += 1
            continue
        ts_str, level, message = match.group(1), match.group(2), match.group(3)
        try:
            timestamp = datetime.fromisoformat(ts_str)
        except ValueError:
            # Regex matched but calendar date is invalid, e.g. 2026-02-30.
            malformed[0] += 1
            continue
        yield LogEntry(timestamp=timestamp, level=level, message=message, raw=line)
