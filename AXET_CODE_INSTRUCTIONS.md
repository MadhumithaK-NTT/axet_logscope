# aXet Code Project Instructions

- Use Python 3.11+ and the standard library unless a dependency is justified.
- Keep the CLI layer separate from parsing and business logic.
- Process input files as streams; never read a full log file into memory.
- Use type hints for public functions.
- Write pytest tests before or alongside each feature.
- Preserve raw log lines for grep output.
- Count and skip malformed lines; do not crash on them.
- Do not modify passing tests merely to make implementation changes pass.
- Before editing files, state the planned files and expected behaviour.
- Run the relevant tests after each implementation step.
- Keep commits small and focused.
