# Cross-Platform Path Handling

Purpose: record a CI failure caused by Windows/Linux path separator differences so the lesson is available to future sessions and bots.

## What Happened

Local CI passed on Windows but GitHub Actions failed after push due to path separator differences.

Root cause: Windows tolerates backslashes (`\`) in path strings that Python constructs or passes to `os.path` functions. Linux does not — it treats `\` as a literal character. The failure surfaced as a file-not-found or import error that did not reproduce locally.

## Rules to Follow

- Always use `pathlib.Path` for path construction; never concatenate paths with string literals or `os.sep`.
- When building relative path strings for display or comparison (for example in `layer_check.py`), normalise with `.as_posix()` so the result is always forward-slash regardless of OS.
- When asserting against path strings in tests, compare `.as_posix()` values or use `pathlib.Path` equality, not raw string equality.
- Run `python -m scripts.run_checks --profile ci` before pushing; also verify that any new path-handling code follows the above rules before assuming local green means CI green.
