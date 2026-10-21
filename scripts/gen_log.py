"""Synthetic log generator for Logscope performance testing.

Usage
-----
python scripts/gen_log.py --size-mb 100 --out /tmp/big.log
python scripts/gen_log.py --size-mb 10  --out test.log --seed 42

Generates a log file with:
- A realistic mix of INFO, WARN, and ERROR lines (~80 / 15 / 5 %).
- ~2 % malformed lines interspersed throughout.
- A bounded pool of recurring error messages so top-five analysis is realistic.
- Lines written one at a time; the full file is never held in memory.

Uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Content pools
# ---------------------------------------------------------------------------

_INFO_MESSAGES = [
    "Service started",
    "Request processed successfully",
    "Health check passed",
    "Cache cleared",
    "Configuration reloaded",
    "Worker thread ready",
    "Connection pool initialised",
    "Scheduled task completed",
    "User session created",
    "Metrics flushed",
]

_WARN_MESSAGES = [
    "Disk usage above 80%",
    "Memory usage high",
    "Response time elevated",
    "Retry attempt 1 of 3",
    "Deprecated API endpoint called",
    "Queue depth exceeding threshold",
    "Certificate expiring in 30 days",
]

# Bounded pool so top-five errors are meaningful.
_ERROR_MESSAGES = [
    "Database connection failed",
    "Timeout waiting for response",
    "Null pointer exception in worker",
    "File not found: config.yaml",
    "Authentication token expired",
    "Out of memory in request handler",
    "Unexpected EOF from upstream",
]

_MALFORMED_LINES = [
    "Exception in thread main java.lang.NullPointerException",
    "  at com.example.App.main(App.java:12)",
    "WARN no timestamp here",
    "2026-13-01 25:00:00 ERROR bad calendar",
    "completely free text with no structure",
    "",
]

# Level weights: ~80 % INFO, ~15 % WARN, ~5 % ERROR.
_LEVELS = ["INFO"] * 80 + ["WARN"] * 15 + ["ERROR"] * 5
_MALFORMED_RATE = 0.02   # 2 % of lines are malformed


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def generate(
    out_path: str | Path,
    target_bytes: int,
    seed: int | None,
) -> tuple[int, int, int]:
    """Write log lines to *out_path* until *target_bytes* is reached.

    Returns
    -------
    (bytes_written, total_lines, malformed_lines)
    """
    rng = random.Random(seed)
    out = Path(out_path)

    # Start timestamp: 2026-10-01 00:00:00, advance ~1 s per line.
    ts = datetime(2026, 10, 1, 0, 0, 0)
    delta = timedelta(seconds=1)

    bytes_written = 0
    total_lines = 0
    malformed_count = 0

    with out.open("w", encoding="utf-8") as fh:
        while bytes_written < target_bytes:
            if rng.random() < _MALFORMED_RATE:
                line = rng.choice(_MALFORMED_LINES)
                malformed_count += 1
            else:
                level = rng.choice(_LEVELS)
                if level == "INFO":
                    msg = rng.choice(_INFO_MESSAGES)
                elif level == "WARN":
                    msg = rng.choice(_WARN_MESSAGES)
                else:
                    msg = rng.choice(_ERROR_MESSAGES)
                line = f"{ts.strftime('%Y-%m-%d %H:%M:%S')} {level} {msg}"
                ts += delta

            encoded = (line + "\n").encode("utf-8")
            fh.write(line + "\n")
            bytes_written += len(encoded)
            total_lines += 1

    return bytes_written, total_lines, malformed_count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate a synthetic log file for Logscope performance testing."
    )
    p.add_argument(
        "--size-mb",
        type=int,
        default=100,
        metavar="MB",
        help="Target file size in megabytes (default: 100).",
    )
    p.add_argument(
        "--out",
        required=True,
        metavar="PATH",
        help="Output file path.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="INT",
        help="Optional random seed for deterministic output.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    target = args.size_mb * 1024 * 1024
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating ~{args.size_mb} MB log -> {out_path} ...", flush=True)
    written, lines, malformed = generate(out_path, target, args.seed)

    print(f"Done.")
    print(f"  Path          : {out_path.resolve()}")
    print(f"  Bytes written : {written:,}")
    print(f"  Total lines   : {lines:,}")
    print(f"  Malformed     : {malformed:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
