"""Grep analysis for Logscope.

Public API
----------
VALID_LEVELS  - frozenset of accepted level strings.
parse_since   - parse a ``YYYY-MM-DD HH:MM`` string into a datetime.
GrepResult    - dataclass returned by ``grep``; ``matches`` is a lazy iterator.
grep          - stream-filter entries by level and optional since timestamp.

Design note — lazy ``matches``
-------------------------------
``GrepResult.matches`` is an ``Iterator[str]``, not a list.  This means the
output layer (CLI, JSON, Markdown) can consume one raw line at a time without
loading the full result set into memory.  The ``malformed`` field is the shared
``[int]`` counter passed to ``parse_stream``; its value is only final once the
``matches`` iterator (and therefore the underlying ``parse_stream`` generator)
has been fully exhausted.  Callers must exhaust ``matches`` before reading
``malformed[0]`` for the definitive count.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generator, Iterator

from logscope.parser import LogEntry

VALID_LEVELS: frozenset[str] = frozenset({"INFO", "WARN", "ERROR"})

_SINCE_FORMAT = "%Y-%m-%d %H:%M"


@dataclass
class GrepResult:
    """Result returned by :func:`grep`.

    Attributes
    ----------
    level:
        The level filter that was applied.
    since:
        The inclusive lower-bound timestamp, or ``None``.
    matches:
        Lazy iterator of raw log line strings in source order.
        Consume this fully before reading ``malformed[0]``.
    malformed:
        Shared ``[int]`` counter from ``parse_stream``.  Final value is
        available only after ``matches`` is exhausted.
    """

    level: str
    since: datetime | None
    matches: Iterator[str]
    malformed: list[int]


def parse_since(since_str: str) -> datetime:
    """Parse *since_str* (``YYYY-MM-DD HH:MM``) into a :class:`datetime`.

    Raises
    ------
    ValueError
        With a human-readable message if the string does not match the
        expected format or contains an invalid calendar date.
    """
    try:
        return datetime.strptime(since_str, _SINCE_FORMAT)
    except ValueError:
        raise ValueError(
            f"Invalid --since value {since_str!r}. "
            f"Expected format: YYYY-MM-DD HH:MM  (e.g. '2026-10-01 09:00')"
        )


def _match_generator(
    entries: Generator[LogEntry, None, None],
    level: str,
    since: datetime | None,
) -> Iterator[str]:
    """Yield raw lines from *entries* that satisfy the filter criteria."""
    for entry in entries:
        if entry.level != level:
            continue
        if since is not None and entry.timestamp < since:
            continue
        yield entry.raw          # original text, never reconstructed


def grep(
    entries: Generator[LogEntry, None, None],
    malformed: list[int],
    level: str,
    since: datetime | None = None,
) -> GrepResult:
    """Return a :class:`GrepResult` whose ``matches`` is a lazy iterator.

    Parameters
    ----------
    entries:
        Generator from :func:`logscope.parser.parse_stream`.
    malformed:
        Shared ``[int]`` counter from ``parse_stream``.
    level:
        One of ``"INFO"``, ``"WARN"``, ``"ERROR"``.  Case-sensitive.
    since:
        If provided, only entries whose timestamp >= *since* are yielded.
        The boundary is inclusive.

    Returns
    -------
    GrepResult
        ``matches`` is a generator — no lines are buffered until the caller
        iterates it.

    Raises
    ------
    ValueError
        Immediately (before any I/O) if *level* is not a valid level string.
    """
    if level not in VALID_LEVELS:
        raise ValueError(
            f"Invalid level {level!r}. "
            f"Supported values: {', '.join(sorted(VALID_LEVELS))}"
        )

    return GrepResult(
        level=level,
        since=since,
        matches=_match_generator(entries, level, since),
        malformed=malformed,
    )
