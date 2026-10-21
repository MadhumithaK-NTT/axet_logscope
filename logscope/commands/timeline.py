"""Timeline analysis for Logscope.

Public API
----------
VALID_BUCKETS   - frozenset of accepted bucket strings.
bucket_minutes  - convert a bucket string to its integer minute width.
timeline        - consume a parse_stream generator; return a plain dict
                  with per-bucket ERROR counts and a text bar chart.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Generator, TypedDict

from logscope.parser import LogEntry

VALID_BUCKETS: frozenset[str] = frozenset({"15m", "30m", "1h"})

_BUCKET_MINUTES: dict[str, int] = {"15m": 15, "30m": 30, "1h": 60}

_BAR_CHAR = "█"
_BAR_SCALE = 1  # one character per ERROR; keeps output readable for unit tests


class TimelineResult(TypedDict):
    bucket: str
    buckets: list[tuple[str, int]]   # [(label, error_count), ...]
    bar_chart: str                   # multi-line text ready for printing
    malformed_lines: int


def bucket_minutes(bucket: str) -> int:
    """Return the width in minutes for *bucket*.

    Raises
    ------
    ValueError
        If *bucket* is not one of ``15m``, ``30m``, ``1h``.
    """
    if bucket not in _BUCKET_MINUTES:
        raise ValueError(
            f"Invalid bucket {bucket!r}. Supported values: "
            + ", ".join(sorted(_BUCKET_MINUTES))
        )
    return _BUCKET_MINUTES[bucket]


def _floor_timestamp(ts: datetime, width_minutes: int) -> datetime:
    """Return the bucket-start datetime for *ts* given *width_minutes*.

    The floor is computed against the epoch of the day (midnight) so that
    bucket boundaries fall on predictable clock times:
      - 15 m → :00, :15, :30, :45
      - 30 m → :00, :30
      - 1 h  → whole hours
    A timestamp that falls exactly on a boundary belongs to that bucket.
    """
    total_minutes = ts.hour * 60 + ts.minute
    floored_minutes = (total_minutes // width_minutes) * width_minutes
    return ts.replace(
        hour=floored_minutes // 60,
        minute=floored_minutes % 60,
        second=0,
        microsecond=0,
    )


def _label(bucket_start: datetime, width_minutes: int) -> str:
    """Human-readable label for a bucket, e.g. ``2026-10-01 09:15``."""
    end = bucket_start + timedelta(minutes=width_minutes)
    return f"{bucket_start.strftime('%Y-%m-%d %H:%M')}–{end.strftime('%H:%M')}"


def timeline(
    entries: Generator[LogEntry, None, None],
    malformed: list[int],
    bucket: str,
) -> TimelineResult:
    """Count ERROR entries per time bucket in a single streaming pass.

    Parameters
    ----------
    entries:
        Generator from :func:`logscope.parser.parse_stream`.  Consumed once.
    malformed:
        Shared ``[int]`` counter from ``parse_stream``; read after exhaustion.
    bucket:
        One of ``"15m"``, ``"30m"``, ``"1h"``.

    Returns
    -------
    TimelineResult
        ``buckets`` is a chronologically ordered list of ``(label, count)``
        pairs.  ``bar_chart`` is a multi-line string with one row per bucket.

    Raises
    ------
    ValueError
        If *bucket* is not a supported value.
    """
    width = bucket_minutes(bucket)          # validates; raises on bad input

    # Only a Counter-like dict of datetime→int is kept — not a list of entries.
    counts: dict[datetime, int] = defaultdict(int)

    for entry in entries:                   # stream: one entry at a time
        if entry.level == "ERROR":
            key = _floor_timestamp(entry.timestamp, width)
            counts[key] += 1

    # Build chronological output.
    sorted_keys = sorted(counts)
    bucket_list: list[tuple[str, int]] = [
        (_label(k, width), counts[k]) for k in sorted_keys
    ]

    # Text bar chart.
    lines: list[str] = []
    for label, count in bucket_list:
        bar = _BAR_CHAR * count
        lines.append(f"{label} | {bar} ({count})")
    bar_chart = "\n".join(lines)

    return TimelineResult(
        bucket=bucket,
        buckets=bucket_list,
        bar_chart=bar_chart,
        malformed_lines=malformed[0],
    )
