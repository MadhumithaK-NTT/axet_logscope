"""Markdown output layer for Logscope.

Public API
----------
report_path          - derive ``<stem>_<command>_report.md`` from a log path.
write_summary_md     - write summary report file; return path.
write_timeline_md    - write timeline report file; return path.
write_grep_md        - consume GrepResult.matches lazily; write report; return path.

Each writer opens the report file, writes content, closes it, and returns the
resolved path so the caller (CLI) can confirm it to the user.
"""

from __future__ import annotations

from pathlib import Path

from logscope.commands.grep import GrepResult


def report_path(log_path: str | Path, command: str) -> Path:
    """Return ``<stem>_<command>_report.md`` in the same directory as *log_path*."""
    p = Path(log_path)
    return p.parent / f"{p.stem}_{command}_report.md"


def write_summary_md(result: dict, log_path: str | Path) -> Path:
    """Write a Markdown summary report and return its path.

    Parameters
    ----------
    result:
        Dict returned by :func:`logscope.commands.summary.summarise`.
    log_path:
        Path to the original log file (used to derive the report filename).
    """
    out_path = report_path(log_path, "summary")
    counts = result["level_counts"]
    first_ts = result["first_timestamp"]
    last_ts = result["last_timestamp"]

    first_str = first_ts.strftime("%Y-%m-%d %H:%M:%S") if first_ts else "N/A"
    last_str = last_ts.strftime("%Y-%m-%d %H:%M:%S") if last_ts else "N/A"

    lines: list[str] = [
        "# Logscope Summary Report\n\n",
        "## Level Counts\n\n",
        f"| Level | Count |\n",
        f"|-------|-------|\n",
        f"| INFO  | {counts.get('INFO', 0)} |\n",
        f"| WARN  | {counts.get('WARN', 0)} |\n",
        f"| ERROR | {counts.get('ERROR', 0)} |\n",
        "\n",
        "## Top Errors\n\n",
    ]

    top = result.get("top_errors", [])
    if top:
        lines.append("| Message | Count |\n")
        lines.append("|---------|-------|\n")
        for msg, count in top:
            lines.append(f"| {msg} | {count} |\n")
    else:
        lines.append("_No errors found._\n")

    lines += [
        "\n",
        "## Timestamps\n\n",
        f"- **First:** {first_str}\n",
        f"- **Last:**  {last_str}\n",
        "\n",
        "## Malformed Lines\n\n",
        f"{result['malformed_lines']}\n",
    ]

    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return out_path


def write_timeline_md(result: dict, log_path: str | Path) -> Path:
    """Write a Markdown timeline report and return its path.

    Parameters
    ----------
    result:
        Dict returned by :func:`logscope.commands.timeline.timeline`.
    log_path:
        Path to the original log file.
    """
    out_path = report_path(log_path, "timeline")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Logscope Timeline Report\n\n")
        f.write(f"Bucket size: **{result['bucket']}**\n\n")
        f.write("## Error Distribution\n\n")
        f.write("```\n")
        if result["bar_chart"]:
            f.write(result["bar_chart"])
            f.write("\n")
        else:
            f.write("(no errors)\n")
        f.write("```\n\n")
        f.write("## Malformed Lines\n\n")
        f.write(f"{result['malformed_lines']}\n")

    return out_path


def write_grep_md(result: GrepResult, log_path: str | Path) -> Path:
    """Write a Markdown grep report incrementally and return its path.

    ``result.matches`` is consumed line by line so the full match set is never
    held in memory.  ``malformed_lines`` is written after the iterator is
    exhausted.

    Parameters
    ----------
    result:
        :class:`logscope.commands.grep.GrepResult` with a lazy ``matches``
        iterator.
    log_path:
        Path to the original log file.
    """
    out_path = report_path(log_path, "grep")
    since_str = (
        result.since.strftime("%Y-%m-%d %H:%M") if result.since else "N/A"
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Logscope Grep Report\n\n")
        f.write(f"- **Level:** {result.level}\n")
        f.write(f"- **Since:** {since_str}\n\n")
        f.write("## Matching Lines\n\n")
        f.write("```\n")

        for raw_line in result.matches:      # lazy: one line at a time
            f.write(raw_line)
            f.write("\n")

        # iterator exhausted — malformed counter is now final
        f.write("```\n\n")
        f.write("## Malformed Lines\n\n")
        f.write(f"{result.malformed[0]}\n")

    return out_path
