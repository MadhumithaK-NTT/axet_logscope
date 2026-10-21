# Logscope Implementation Plan

## 1. Package Structure

```
logscope/
├── logscope/
│   ├── __init__.py
│   ├── parser.py          # Line-by-line streaming parser, LogEntry dataclass
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── summary.py     # summary command logic
│   │   ├── timeline.py    # timeline command logic
│   │   └── grep.py        # grep command logic
│   ├── output/
│   │   ├── __init__.py
│   │   ├── json_output.py # JSON serialisation helpers
│   │   └── md_output.py   # Markdown report writer
│   └── cli.py             # argparse entry point; thin — delegates to commands
├── tests/
│   ├── fixtures/
│   │   └── sample.log         # small curated log used for end-to-end smoke tests
│   ├── conftest.py        # shared fixtures (sample log lines, tmp files)
│   ├── test_parser.py
│   ├── test_summary.py
│   ├── test_timeline.py
│   ├── test_grep.py
│   ├── test_output.py
│   └── test_cli.py
├── pyproject.toml         # build metadata, entry point: logscope = logscope.cli:main
└── IMPLEMENTATION_PLAN.md
```

## 2. Data Model

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class LogEntry:
    timestamp: datetime
    level: str          # "INFO" | "WARN" | "ERROR"
    message: str
    raw: str            # original line, preserved for grep output
```

A parse result is represented as a tagged union via a simple pair of generators:

- `parse_stream(file_obj)` yields `LogEntry` for valid lines.
- Callers receive a `ParseResult` tuple: `(entries_iter, malformed_counter)` where
  `malformed_counter` is a mutable `Counter`-like object updated as iteration proceeds.

In practice this is implemented as a single generator that also increments a
shared `[int]` cell (a one-element list) so callers can read the malformed count
after exhausting the iterator.

## 3. Streaming Parser Design

```
open file → iterate lines (io.TextIOWrapper, default buffer)
  for each line:
    strip newline
    attempt regex match: r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (INFO|WARN|ERROR) (.+)$'
    on match  → attempt datetime.fromisoformat(g1)
                  success → yield LogEntry(timestamp=..., level=g2, message=g3, raw=line)
                  ValueError → increment malformed count, continue  ← invalid calendar date
    no match  → increment malformed count, continue
```

A line that matches the regex but contains an invalid calendar date (e.g.
`2026-02-30`) passes the pattern check but fails `datetime.fromisoformat()`.
This `ValueError` is caught and the line is treated as malformed — it increments
the counter and is skipped. The program never crashes on such input.

- One compiled `re.Pattern` at module level (compiled once).
- Files opened with `open(path, "r", encoding="utf-8", errors="replace")` so
  encoding errors are handled gracefully rather than crashing.
- No list accumulation inside the parser; each entry is yielded immediately.

## 4. Implementation Order

| Step | Deliverable | Tests written first |
|------|-------------|---------------------|
| 1 | `parser.py` + `LogEntry` | `test_parser.py` |
| 2 | `commands/summary.py` | `test_summary.py` |
| 3 | `commands/timeline.py` | `test_timeline.py` |
| 4 | `commands/grep.py` | `test_grep.py` |
| 5 | `output/json_output.py` + `output/md_output.py` | `test_output.py` |
| 6 | `cli.py` (wire everything together) | `test_cli.py` |
| 7 | Performance verification script | — |

Each step ends with `pytest tests/` passing before the next begins.

## 5. Test Plan

### test_parser.py
- Valid INFO / WARN / ERROR lines parse to correct `LogEntry` fields.
- Malformed lines (missing level, wrong date format, empty) increment counter.
- A line matching the regex but containing an invalid calendar date (e.g. `2026-02-30 10:00:00 ERROR msg`) is counted as malformed, not raised as an exception.
- Mixed file yields correct entries and correct malformed count.
- Timestamps are `datetime` objects (not strings).

### test_summary.py
- Correct level counts for a known fixture.
- Top-5 errors ranked by frequency; ties broken lexicographically.
- First/last timestamp extracted correctly.
- Malformed count propagated.

### test_grep.py
- `--level ERROR` filters to ERROR lines only.
- `--since "2026-10-01 09:00"` includes the boundary timestamp (inclusive).
- Combined `--level` + `--since` filter works.
- Output preserves raw lines (not reformatted).

### test_timeline.py
- 15m, 30m, 1h bucket boundaries are correct.
- Errors on bucket boundary are attributed to the correct bucket.
- Bar chart output contains expected bucket labels.

### test_output.py
- JSON output is valid JSON and contains all required keys.
- Markdown output writes a file and returns its path.
- Both formats work for all three commands.

### test_cli.py
- Unknown subcommand exits with a non-zero exit code and prints a usage message.
- Missing required positional argument (log file) exits with a non-zero exit code.
- Non-existent log file path exits with a non-zero exit code and a human-readable error message.
- Valid invocations exit with code 0.
- `--format json` produces valid JSON on stdout; exit code 0.
- `--format md` writes a `.md` report file and prints its path to stdout; exit code 0.

**Fixture strategy:**
- Parser, command logic, and output tests use `io.StringIO` — no disk I/O needed.
- CLI tests (`test_cli.py`) write temporary real files via `tmp_path` (pytest built-in)
  so that the full argument-parsing and file-opening path is exercised.
- `tests/fixtures/sample.log` is a small, curated real file used only for
  end-to-end smoke tests that run the CLI against a known input and assert on
  stdout/file output.

## 6. JSON and Markdown Output

### JSON (`--format json`)
Each command returns a plain Python dict from its logic function.  
`json_output.py` serialises it with `json.dumps(..., indent=2, default=str)`
(the `default=str` handles `datetime` objects) and writes to `stdout`.

Example structure for `summary`:
```json
{
  "level_counts": {"INFO": 120, "WARN": 5, "ERROR": 18},
  "top_errors": [["Database connection failed", 12], ["Timeout", 4]],
  "first_timestamp": "2026-10-01 09:15:00",
  "last_timestamp": "2026-10-01 23:59:55",
  "malformed_lines": 3
}
```

### Markdown (`--format md`)
`md_output.py` receives the same dict and a command name, renders a `.md` file
using an f-string template per command (no external templating library), writes
it to `<logfile_stem>_<command>_report.md` in the current directory, and prints
`Report written to <path>` to stdout.

## 7. Performance Verification

A helper script `scripts/gen_log.py` generates a synthetic 100 MB log file with
a realistic mix of INFO / WARN / ERROR lines and a small percentage (~2 %) of
malformed lines. Generation uses `random` from the standard library.

Verification is run with PowerShell:
```powershell
python scripts/gen_log.py --size-mb 100 --out $env:TEMP\big.log
Measure-Command { python -m logscope summary $env:TEMP\big.log }
```

`Measure-Command` reports total wall-clock time. To observe memory, run the
command under Task Manager or use:
```powershell
$proc = Start-Process python -ArgumentList "-m logscope summary $env:TEMP\big.log" -PassThru
$proc.WaitForExit()
"Peak working set: $([math]::Round($proc.PeakWorkingSet64 / 1MB, 1)) MB"
```

Pass criteria:
- Wall time < 60 s on a standard developer laptop.
- Peak memory remains stable and substantially below the 100 MB input size,
  confirming that the file is processed as a stream and not loaded into memory.

The same script can be invoked in CI with a smaller size (e.g. 10 MB) to keep
pipeline time reasonable while still exercising the streaming path.
