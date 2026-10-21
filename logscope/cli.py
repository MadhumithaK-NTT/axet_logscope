"""Command-line interface for Logscope.

Entry points
------------
main()           - called by the ``logscope`` console script (pyproject.toml).
logscope/__main__.py calls main() so ``python -m logscope`` also works.

Design
------
cli.py only:
  1. parses arguments,
  2. opens the log file,
  3. calls the appropriate command function,
  4. delegates formatting to the output layer.

All business logic lives in logscope.commands.*  All formatting lives in
logscope.output.*  This file contains no analysis or serialisation logic.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from logscope.parser import parse_stream
from logscope.commands.summary import summarise
from logscope.commands.timeline import timeline
from logscope.commands.grep import grep, parse_since
from logscope.output.json_output import (
    write_summary_json,
    write_timeline_json,
    write_grep_json,
)
from logscope.output.md_output import (
    write_summary_md,
    write_timeline_md,
    write_grep_md,
)


# ---------------------------------------------------------------------------
# Plain-text formatters (default output, no --format flag)
# ---------------------------------------------------------------------------

def _print_summary(result: dict) -> None:
    counts = result["level_counts"]
    print("=== Summary ===")
    print(f"  INFO   : {counts.get('INFO', 0)}")
    print(f"  WARN   : {counts.get('WARN', 0)}")
    print(f"  ERROR  : {counts.get('ERROR', 0)}")

    first = result["first_timestamp"]
    last = result["last_timestamp"]
    print(f"  First  : {first.strftime('%Y-%m-%d %H:%M:%S') if first else 'N/A'}")
    print(f"  Last   : {last.strftime('%Y-%m-%d %H:%M:%S') if last else 'N/A'}")

    print("\nTop errors:")
    top = result.get("top_errors", [])
    if top:
        for msg, count in top:
            print(f"  [{count:>4}] {msg}")
    else:
        print("  (none)")

    print(f"\nMalformed lines: {result['malformed_lines']}")


def _print_timeline(result: dict) -> None:
    print(f"=== Timeline (bucket: {result['bucket']}) ===")
    if result["bar_chart"]:
        print(result["bar_chart"])
    else:
        print("  (no errors)")
    print(f"\nMalformed lines: {result['malformed_lines']}")


def _print_grep(result) -> None:
    """Print grep matches lazily, then the malformed count."""
    for raw_line in result.matches:        # consumes the iterator once
        print(raw_line)
    print(f"\nMalformed lines: {result.malformed[0]}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logscope",
        description="Analyse application log files without loading them into memory.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ---- summary -----------------------------------------------------------
    p_summary = sub.add_parser("summary", help="Show log summary statistics.")
    p_summary.add_argument("logfile", help="Path to the log file.")
    p_summary.add_argument(
        "--format",
        choices=["json", "md"],
        default=None,
        help="Output format: json (stdout) or md (report file).",
    )

    # ---- timeline ----------------------------------------------------------
    p_timeline = sub.add_parser("timeline", help="Show ERROR counts per time bucket.")
    p_timeline.add_argument("logfile", help="Path to the log file.")
    p_timeline.add_argument(
        "--bucket",
        required=True,
        choices=["15m", "30m", "1h"],
        help="Bucket size: 15m, 30m, or 1h.",
    )
    p_timeline.add_argument(
        "--format",
        choices=["json", "md"],
        default=None,
        help="Output format: json (stdout) or md (report file).",
    )

    # ---- grep --------------------------------------------------------------
    p_grep = sub.add_parser("grep", help="Filter log lines by level and/or timestamp.")
    p_grep.add_argument("logfile", help="Path to the log file.")
    p_grep.add_argument(
        "--level",
        required=True,
        choices=["INFO", "WARN", "ERROR"],
        help="Log level to filter on.",
    )
    p_grep.add_argument(
        "--since",
        default=None,
        metavar="YYYY-MM-DD HH:MM",
        help="Only show entries at or after this timestamp (inclusive).",
    )
    p_grep.add_argument(
        "--format",
        choices=["json", "md"],
        default=None,
        help="Output format: json (stdout) or md (report file).",
    )

    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _handle_summary(args: argparse.Namespace) -> int:
    malformed: list[int] = [0]
    with open(args.logfile, encoding="utf-8", errors="replace") as fh:
        result = summarise(parse_stream(fh, malformed), malformed)

    fmt = args.format
    if fmt == "json":
        write_summary_json(result, sys.stdout)
    elif fmt == "md":
        path = write_summary_md(result, args.logfile)
        print(f"Report written to {path}")
    else:
        _print_summary(result)
    return 0


def _handle_timeline(args: argparse.Namespace) -> int:
    malformed: list[int] = [0]
    with open(args.logfile, encoding="utf-8", errors="replace") as fh:
        result = timeline(parse_stream(fh, malformed), malformed, args.bucket)

    fmt = args.format
    if fmt == "json":
        write_timeline_json(result, sys.stdout)
    elif fmt == "md":
        path = write_timeline_md(result, args.logfile)
        print(f"Report written to {path}")
    else:
        _print_timeline(result)
    return 0


def _handle_grep(args: argparse.Namespace) -> int:
    since = None
    if args.since:
        try:
            since = parse_since(args.since)
        except ValueError as exc:
            print(f"logscope grep: error: {exc}", file=sys.stderr)
            return 2

    malformed: list[int] = [0]
    fh = open(args.logfile, encoding="utf-8", errors="replace")  # noqa: WPS515
    # File stays open while the lazy iterator is consumed by the output layer.
    try:
        result = grep(parse_stream(fh, malformed), malformed, args.level, since)
        fmt = args.format
        if fmt == "json":
            write_grep_json(result, sys.stdout)
        elif fmt == "md":
            path = write_grep_md(result, args.logfile)
            print(f"Report written to {path}")
        else:
            _print_grep(result)
    finally:
        fh.close()
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Parse *argv* (defaults to sys.argv[1:]), run the command, return exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help(sys.stderr)
        return 2

    # Validate log file existence early for all commands.
    if not Path(args.logfile).exists():
        print(
            f"logscope {args.command}: error: file not found: {args.logfile}",
            file=sys.stderr,
        )
        return 2

    dispatch = {
        "summary": _handle_summary,
        "timeline": _handle_timeline,
        "grep": _handle_grep,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
