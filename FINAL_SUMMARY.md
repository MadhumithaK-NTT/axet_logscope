# Logscope — Final Project Summary

## 1. Project Overview

**Logscope** is a Python 3.11+ command-line tool for streaming application-log
analysis. It processes log files line by line using generator-based pipelines
and avoids loading the full log file into memory at any point during execution.

---

## 2. Features Delivered

| Command | Description |
|---------|-------------|
| `summary <logfile>` | INFO / WARN / ERROR counts, top five error messages by frequency (ties broken lexicographically), first and last valid timestamp, malformed-line count |
| `timeline <logfile> --bucket 15m\|30m\|1h` | ERROR counts grouped into time buckets; displayed as an ASCII text bar chart |
| `grep <logfile> --level INFO\|WARN\|ERROR [--since "YYYY-MM-DD HH:MM"]` | Stream-filters raw log lines by level and optional inclusive timestamp; output is written incrementally |

All three commands support:

- **`--format json`** — writes structured JSON to stdout.
- **`--format md`** — writes a Markdown report file (`<stem>_<command>_report.md`) and prints the file path to stdout.
- Default (no flag) — human-readable plain text to stdout.

---

## 3. Architecture and Streaming Design

```
log file (disk)
  │
  ▼
parse_stream()          ← generator; yields LogEntry one line at a time
  │  malformed [int]    ← shared counter updated during iteration
  ▼
command function        ← summary / timeline / grep
  │
  ▼
output layer            ← json_output / md_output / plain text
```

### Component memory characteristics

| Component | Memory model |
|-----------|-------------|
| **Parser** (`parser.py`) | Single compiled regex; yields one `LogEntry` at a time; no list accumulation |
| **Summary** (`summary.py`) | Stores three integer counters + a `Counter` of distinct error message strings; does **not** store all entries |
| **Timeline** (`timeline.py`) | Stores one integer per distinct bucket start-time; does **not** store all entries |
| **Grep** (`grep.py`) | Returns a `GrepResult` whose `matches` field is a lazy generator; matching raw lines are yielded one at a time to the output layer — no list is built |
| **JSON grep output** | Writes the `matches` JSON array incrementally, one line per `out.write()` call; `malformed_lines` is written after the iterator is exhausted |
| **Markdown grep output** | Writes each matching line to the report file inside the iteration loop; `malformed_lines` is appended after exhaustion |

> **Note:** Summary and timeline aggregate results (counters, message strings,
> bucket keys) are bounded by the number of distinct values in the log, not by
> the total line count. They do not operate in O(1) memory, but in practice
> their footprint is negligible compared with the input file size.

### Malformed-line handling

Lines that fail the regex match **or** that pass the regex but contain an
invalid calendar date (e.g. `2026-02-30`) are counted and skipped without
raising an exception. The count is reported by every command.

---

## 4. Test Evidence

```
python -m pytest -v
```

**Result: 248 passed in ~2.25 seconds** (Python 3.12.10, pytest 9.1.1,
Windows 11).

Test coverage spans six test files:

| File | What is tested |
|------|---------------|
| `tests/test_parser.py` | `LogEntry` dataclass, regex matching, invalid calendar dates, streaming laziness, `sample.log` smoke test |
| `tests/test_summary.py` | Level counts, top-five ranking, tie-breaking, first/last timestamp, malformed propagation |
| `tests/test_timeline.py` | Bucket floor calculation, boundary attribution, all three bucket sizes, chronological order, bar chart content |
| `tests/test_grep.py` | Level filtering, inclusive `--since` boundary, combined filters, raw-line preservation, lazy iterator contract, `parse_since` validation |
| `tests/test_output.py` | JSON validity for all three commands, Markdown report creation and content, streaming grep output |
| `tests/test_cli.py` | Plain-text / JSON / Markdown runs for all three commands, missing file, invalid bucket/level/since, missing arguments, unknown command, `--help` |

---

## 5. Acceptance Criteria

| Criterion | Evidence | Status |
|-----------|----------|--------|
| All three commands work on `tests/fixtures/sample.log` | Smoke tests produce correct output: 10 valid lines, 1 malformed line (see §6) | **PASS** |
| Unit tests for parser and each command pass | 248 tests passed in 2.25 s | **PASS** |
| 100 MB log processed in under 60 s with stable memory | 104,857,615 bytes / 2,222,979 lines processed in **3.53 s**; peak working set **28.7 MB** (well below the 100 MB input) | **PASS** |
| Malformed-line count reported by every command | `sample.log` reports 1 malformed; 100 MB generated file reports 44,779 malformed (~2 %) | **PASS** |
| Git history demonstrates plan-then-build and small commits | View with `git log --oneline` in the repository — commit history is not reproduced here to avoid inventing hashes or dates | **VERIFY IN REPO** |

---

## 6. Commands to Reproduce

### Run all tests

```bash
python -m pytest -v
```

### Run all three commands against the sample fixture

```bash
python -m logscope summary  tests/fixtures/sample.log
python -m logscope timeline tests/fixtures/sample.log --bucket 15m
python -m logscope grep     tests/fixtures/sample.log --level ERROR
```

### JSON output

```bash
python -m logscope summary  tests/fixtures/sample.log --format json
python -m logscope timeline tests/fixtures/sample.log --bucket 1h  --format json
python -m logscope grep     tests/fixtures/sample.log --level ERROR --format json
```

### Markdown report output

```bash
python -m logscope summary  tests/fixtures/sample.log --format md
python -m logscope timeline tests/fixtures/sample.log --bucket 30m --format md
python -m logscope grep     tests/fixtures/sample.log --level WARN  --format md
# Report files are written to the same directory as the log file.
```

### Generate a 100 MB synthetic log (Windows PowerShell)

```powershell
python scripts/gen_log.py --size-mb 100 --out $env:TEMP\logscope_big.log --seed 42
```

### Performance measurement (Windows PowerShell)

```powershell
# Wall-clock time
Measure-Command { python -m logscope summary $env:TEMP\logscope_big.log --format json }

# Peak working set (polled during execution)
$p = Start-Process python -ArgumentList "-m","logscope","summary",$env:TEMP\logscope_big.log,"--format","json" -PassThru
$peak = 0
while (-not $p.HasExited) {
    $p.Refresh()
    if ($p.WorkingSet64 -gt $peak) { $peak = $p.WorkingSet64 }
    Start-Sleep -Milliseconds 50
}
"Peak working set: $([math]::Round($peak / 1MB, 1)) MB"
```

**Measured:** 3.53 s wall-clock, 28.7 MB peak — see `PERFORMANCE.md` for the
full output.

---

## 7. Key Project Files

| Path | Purpose |
|------|---------|
| `SPEC.md` | Original assignment specification |
| `AXET_CODE_INSTRUCTIONS.md` | Project coding standards and constraints |
| `IMPLEMENTATION_PLAN.md` | Pre-implementation design: package structure, data model, streaming design, implementation order, test plan |
| `README.md` | Installation, log format, all command examples, malformed-line explanation, generator usage |
| `PERFORMANCE.md` | Actual measured wall-clock time and peak memory for 100 MB input |
| `scripts/gen_log.py` | Synthetic log generator; standard-library only |
| `logscope/` | Application package: `parser.py`, `commands/`, `output/`, `cli.py`, `__main__.py` |
| `tests/` | 248 pytest tests across six files + `fixtures/sample.log` |

---

## 8. Evidence Checklist

The following screenshots / terminal captures should be included when
submitting this assignment:

- [ ] `python -m pytest -v` — all 248 tests passing
- [ ] `python -m logscope summary tests/fixtures/sample.log` — plain-text output
- [ ] `python -m logscope timeline tests/fixtures/sample.log --bucket 15m` — bar chart output
- [ ] `python -m logscope grep tests/fixtures/sample.log --level ERROR` — raw filtered lines
- [ ] `python -m logscope summary tests/fixtures/sample.log --format json` — JSON output
- [ ] `python -m logscope summary tests/fixtures/sample.log --format md` — Markdown report created
- [ ] `python scripts/gen_log.py --size-mb 100 --out ... --seed 42` — generator output (bytes, lines, malformed count)
- [ ] Performance measurement showing **3.53 s** and **28.7 MB** peak
- [ ] `git log --oneline` — commit history showing incremental, plan-then-build approach
