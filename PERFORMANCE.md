# Logscope Performance Report

## Environment

| Item | Value |
|------|-------|
| Platform | Windows 10/11 (64-bit) |
| Python | 3.12.10 |
| logscope version | 0.1.0 |

## Synthetic Log File

Generated with:

```powershell
python scripts/gen_log.py --size-mb 100 --out $env:TEMP\logscope_big.log --seed 42
```

| Metric | Value |
|--------|-------|
| File size | 104,857,615 bytes (~100 MB) |
| Total lines | 2,222,979 |
| Malformed lines | 44,779 (~2 %) |
| Level mix | INFO 78.4 %, WARN 14.7 %, ERROR 4.9 % |

## Measurement — `summary --format json`

Command:

```powershell
Measure-Command { python -m logscope summary $env:TEMP\logscope_big.log --format json }
```

| Metric | Measured value | Requirement |
|--------|---------------|-------------|
| Wall-clock time | **3.53 s** | < 60 s |
| Peak working set | **28.7 MB** | Substantially below 100 MB |

### Result: PASS

Both criteria are met by a large margin:

- Wall-clock time (3.53 s) is **17× faster** than the 60-second limit.
- Peak memory (28.7 MB) is **71 MB below** the 100 MB input file size,
  confirming that the file is processed as a stream and never loaded in full.

## Summary JSON output (actual)

```json
{
  "level_counts": {
    "INFO": 1742713,
    "WARN": 326274,
    "ERROR": 109213
  },
  "top_errors": [
    ["Unexpected EOF from upstream",    15742],
    ["Null pointer exception in worker", 15726],
    ["Timeout waiting for response",    15593],
    ["File not found: config.yaml",     15559],
    ["Out of memory in request handler", 15554]
  ],
  "first_timestamp": "2026-10-01 00:00:00",
  "last_timestamp":  "2026-10-26 05:03:19",
  "malformed_lines": 44779
}
```

## Memory measurement method

Because `PeakWorkingSet64` is zeroed once a process exits, memory was polled
every 50 ms while the process ran via PowerShell:

```powershell
$p = Start-Process python -ArgumentList "-m","logscope","summary",$big,"--format","json" -PassThru
$peak = 0
while (-not $p.HasExited) {
    $p.Refresh()
    if ($p.WorkingSet64 -gt $peak) { $peak = $p.WorkingSet64 }
    Start-Sleep -Milliseconds 50
}
"Peak working set: $([math]::Round($peak / 1MB, 1)) MB"
```

## Reproducing on a CI machine

For CI pipelines where a 100 MB file is too slow, use a 10 MB file:

```powershell
python scripts/gen_log.py --size-mb 10 --out $env:TEMP\logscope_ci.log --seed 42
Measure-Command { python -m logscope summary $env:TEMP\logscope_ci.log --format json }
```
