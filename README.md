# Logscope

A command-line tool that analyses application log files **without loading the
full file into memory**. All commands stream input line by line and are suitable
for arbitrarily large log files.

---

## Installation

Requires Python 3.11 or newer. No third-party dependencies.

```bash
# Clone the repo and install in editable mode
pip install -e .

# Verify
python -m logscope --help
```

To run the tests, install pytest:

```bash
pip install --user pytest
python -m pytest -v
```

---

## Log format

Each valid line must follow this exact pattern:

```
YYYY-MM-DD HH:MM:SS LEVEL message
```

Where `LEVEL` is one of `INFO`, `WARN`, or `ERROR`. Examples:

```
2026-10-01 09:15:00 INFO  Service started
2026-10-01 09:16:12 ERROR Database connection failed
2026-10-01 09:17:05 WARN  Disk usage above 80%
```

Lines that do not match this format are **malformed**. They are counted and
skipped; they never cause the program to crash. Every command reports the total
number of malformed lines encountered.

---

## Commands

### `summary`

Show log statistics: level counts, top five error messages by frequency,
first and last valid timestamps, and malformed-line count.

```bash
# Plain text (default)
python -m logscope summary app.log

# JSON to stdout
python -m logscope summary app.log --format json

# Markdown report file
python -m logscope summary app.log --format md
```

**Plain text output:**

```
=== Summary ===
  INFO   : 4
  WARN   : 2
  ERROR  : 4
  First  : 2026-10-01 09:15:00
  Last   : 2026-10-01 09:22:30

Top errors:
  [   3] Database connection failed
  [   1] Timeout waiting for response

Malformed lines: 1
```

**JSON output (`--format json`):**

```json
{
  "level_counts": {"INFO": 4, "WARN": 2, "ERROR": 4},
  "top_errors": [
    ["Database connection failed", 3],
    ["Timeout waiting for response", 1]
  ],
  "first_timestamp": "2026-10-01 09:15:00",
  "last_timestamp":  "2026-10-01 09:22:30",
  "malformed_lines": 1
}
```

**Markdown (`--format md`):**

Creates `<logfile_stem>_summary_report.md` in the same directory as the log
file and prints the path:

```
Report written to app_summary_report.md
```

---

### `timeline`

Count ERROR entries per time bucket and display a text bar chart.

```bash
# Plain text (default)
python -m logscope timeline app.log --bucket 15m

# Supported bucket sizes: 15m, 30m, 1h
python -m logscope timeline app.log --bucket 1h --format json
python -m logscope timeline app.log --bucket 30m --format md
```

**Plain text output:**

```
=== Timeline (bucket: 15m) ===
2026-10-01 09:15-09:30 | #### (4)

Malformed lines: 1
```

**JSON output:**

```json
{
  "bucket": "15m",
  "buckets": [["2026-10-01 09:15-09:30", 4]],
  "bar_chart": "2026-10-01 09:15-09:30 | #### (4)",
  "malformed_lines": 1
}
```

---

### `grep`

Filter log lines by level and optionally by an inclusive start timestamp.
Matching raw log lines are written directly to output — they are **never
reconstructed** from parsed fields.

```bash
# Filter by level
python -m logscope grep app.log --level ERROR

# Filter with an inclusive since timestamp
python -m logscope grep app.log --level ERROR --since "2026-10-01 09:20"

# JSON output
python -m logscope grep app.log --level INFO --format json

# Markdown report
python -m logscope grep app.log --level WARN --format md
```

**Plain text output:**

```
2026-10-01 09:16:12 ERROR Database connection failed
2026-10-01 09:18:45 ERROR Database connection failed
2026-10-01 09:19:30 ERROR Timeout waiting for response
2026-10-01 09:21:00 ERROR Database connection failed

Malformed lines: 1
```

**Streaming behaviour:** grep output is streamed — matching lines are written to
stdout (or the report file) one at a time as they are read from the source file.
No list of matching lines is held in memory. The `malformed_lines` count is
reported only after the stream is fully consumed.

---

## Malformed-line reporting

Every command counts lines that do not conform to the expected format:

- Missing or wrong level token (e.g. `DEBUG`, `TRACE`)
- Incorrect date/time format
- Lines with no timestamp at all
- Lines that match the regex pattern but contain an impossible calendar date
  (e.g. February 30th)

Malformed lines are **counted and skipped**; they do not terminate the program
or affect the counts/output for valid lines.

---

## Synthetic log generator

Use `scripts/gen_log.py` to generate large test files:

```bash
# Generate a ~100 MB file with a fixed seed
python scripts/gen_log.py --size-mb 100 --out big.log --seed 42

# Options
#   --size-mb  Target file size in MB (default: 100)
#   --out      Output path (required)
#   --seed     Optional integer seed for reproducible output
```

Output example:

```
Generating ~100 MB log -> big.log ...
Done.
  Path          : C:\...\big.log
  Bytes written : 104,857,615
  Total lines   : 2,222,979
  Malformed     : 44,779
```

---

## Performance verification (Windows PowerShell)

```powershell
# Generate the file
python scripts/gen_log.py --size-mb 100 --out $env:TEMP\big.log --seed 42

# Time the summary command
Measure-Command { python -m logscope summary $env:TEMP\big.log --format json }
```

**Measured result on this machine:** 3.53 s wall-clock, 28.7 MB peak memory
for a 100 MB input file. Full details in [PERFORMANCE.md](PERFORMANCE.md).

Requirement: < 60 s with stable memory substantially below the input file size.
Status: **PASS**.

---

## Project structure

```
logscope/
├── logscope/
│   ├── parser.py          # streaming parser, LogEntry dataclass
│   ├── commands/
│   │   ├── summary.py     # summary analysis
│   │   ├── timeline.py    # timeline bucket analysis
│   │   └── grep.py        # level + since filtering
│   ├── output/
│   │   ├── json_output.py # JSON serialisation
│   │   └── md_output.py   # Markdown report writer
│   ├── cli.py             # argparse entry point
│   └── __main__.py        # enables python -m logscope
├── tests/
│   ├── fixtures/sample.log
│   ├── test_parser.py
│   ├── test_summary.py
│   ├── test_timeline.py
│   ├── test_grep.py
│   ├── test_output.py
│   └── test_cli.py
├── scripts/
│   └── gen_log.py         # synthetic log generator
├── PERFORMANCE.md
└── pyproject.toml
```
