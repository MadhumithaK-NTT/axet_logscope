"""JSON output layer for Logscope.

Public API
----------
write_summary_json   - serialise a summary result dict to *out*.
write_timeline_json  - serialise a timeline result dict to *out*.
write_grep_json      - consume GrepResult.matches lazily; write JSON to *out*.

All functions write to any text-mode file-like object (stdout, StringIO, etc.).
``datetime`` values are serialised as ISO-format strings via *default=str*.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import IO

from logscope.commands.grep import GrepResult


def _default(obj: object) -> str:
    """JSON serialisation fallback: convert datetime to ISO string."""
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


def write_summary_json(result: dict, out: IO[str]) -> None:
    """Write *result* (from :func:`logscope.commands.summary.summarise`) as JSON.

    The full summary dict is serialised in one call; it is small (counters,
    five strings, two timestamps) so buffering it is safe.
    """
    out.write(json.dumps(result, indent=2, default=_default))
    out.write("\n")


def write_timeline_json(result: dict, out: IO[str]) -> None:
    """Write *result* (from :func:`logscope.commands.timeline.timeline`) as JSON."""
    out.write(json.dumps(result, indent=2, default=_default))
    out.write("\n")


def write_grep_json(result: GrepResult, out: IO[str]) -> None:
    """Write *result* as JSON, consuming ``result.matches`` line by line.

    The ``matches`` array is built incrementally so that no full list is held
    in memory.  ``malformed_lines`` is written *after* the iterator is
    exhausted so the counter is final.

    Output shape::

        {
          "level": "ERROR",
          "since": "2026-10-01 09:00",
          "matches": [
            "...",
            "..."
          ],
          "malformed_lines": 3
        }
    """
    since_str = result.since.strftime("%Y-%m-%d %H:%M") if result.since else None

    out.write("{\n")
    out.write(f'  "level": {json.dumps(result.level)},\n')
    out.write(f'  "since": {json.dumps(since_str)},\n')
    out.write('  "matches": [\n')

    first = True
    for raw_line in result.matches:          # lazy: one line at a time
        if not first:
            out.write(",\n")
        out.write(f"    {json.dumps(raw_line)}")
        first = False

    # iterator exhausted — malformed counter is now final
    out.write("\n  ],\n")
    out.write(f'  "malformed_lines": {result.malformed[0]}\n')
    out.write("}\n")
