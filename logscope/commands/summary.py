"""Summary analysis for Logscope.

Public API
----------
summarise   - consumes a parse_stream generator and returns a plain dict
              suitable for JSON/Markdown formatting by the output layer.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Generator, TypedDict

from logscope.parser import LogEntry


class SummaryResult(TypedDict):
    level_counts: dict[str, int]
    top_errors: list[tuple[str, int]]
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    malformed_lines: int


def summarise(
    entries: Generator[LogEntry, None, None],
    malformed: list[int],
) -> SummaryResult:
    """Analyse *entries* in a single streaming pass.

    Parameters
    ----------
    entries:
        Generator produced by :func:`logscope.parser.parse_stream`.  Consumed
        exactly once; no list is built.
    malformed:
        The shared ``[int]`` counter passed to ``parse_stream``.  Read after
        the generator is exhausted so the final count is captured.

    Returns
    -------
    SummaryResult
        A plain ``TypedDict`` (dict subclass) ready for the output layer.
        ``top_errors`` contains at most five ``(message, count)`` pairs,
        ordered by descending frequency then ascending lexicographic order on
        ties.
    """
    level_counts: dict[str, int] = {"INFO": 0, "WARN": 0, "ERROR": 0}
    error_counter: Counter[str] = Counter()
    first_ts: datetime | None = None
    last_ts: datetime | None = None

    for entry in entries:                       # one entry at a time — no list
        level_counts[entry.level] = level_counts.get(entry.level, 0) + 1

        if entry.level == "ERROR":
            error_counter[entry.message] += 1

        if first_ts is None or entry.timestamp < first_ts:
            first_ts = entry.timestamp
        if last_ts is None or entry.timestamp > last_ts:
            last_ts = entry.timestamp

    # Top-5: primary sort descending count, secondary sort ascending message.
    top_errors: list[tuple[str, int]] = sorted(
        error_counter.items(),
        key=lambda item: (-item[1], item[0]),
    )[:5]

    return SummaryResult(
        level_counts=level_counts,
        top_errors=top_errors,
        first_timestamp=first_ts,
        last_timestamp=last_ts,
        malformed_lines=malformed[0],
    )
