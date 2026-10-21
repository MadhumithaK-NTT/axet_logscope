# Logscope Specification

## Goal
Build a command-line tool that analyses application log files without loading
the full file into memory.

## Supported log format
Each valid line uses this format:

YYYY-MM-DD HH:MM:SS LEVEL message

Example:
2026-10-01 09:15:00 INFO Service started
2026-10-01 09:16:12 ERROR Database connection failed

Lines that do not match this format are malformed. They must be counted and
skipped without terminating the program.

## Commands

### Summary
Command:
logscope summary app.log

Output:
- Count of INFO, WARN, and ERROR lines
- Top five ERROR messages by frequency
- First valid timestamp
- Last valid timestamp
- Malformed-line count

### Timeline
Command:
logscope timeline app.log --bucket 15m

Output:
- ERROR count in each time bucket
- Text bar chart
- Malformed-line count

Supported bucket values: 15m, 30m, 1h.

### Grep
Command:
logscope grep app.log --level ERROR --since "2026-10-01 09:00"

Output:
- Matching original log lines
- Supports level filtering
- Supports an optional inclusive `--since` timestamp
- Reports malformed-line count

## Output formats
Every command supports:

--format json
--format md

JSON prints structured output to stdout.
Markdown writes a report file and confirms its path.

## Performance
The implementation must process logs line by line and must not load the entire
file into memory. It must process a 100 MB synthetic log in under 60 seconds
with stable memory usage.

## Quality
- Unit tests for parser and each command
- Invalid files or invalid arguments return helpful errors
- The project uses small, focused commits
