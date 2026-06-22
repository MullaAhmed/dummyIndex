# Bootstrap renderer — spec

confidence: INFERRED

## Intent

Render and idempotently regenerate the dummyindex-managed block inside `<root>/.claude/CLAUDE.md` so a freshly-indexed repo always carries a short, current pointer at `.context/HOW_TO_USE.md`. The renderer owns exactly one delimited region of the file and never touches surrounding content; re-running it converges on the same output (`dummyindex/context/output/bootstrap.py:1-5`).

## User-visible behavior

### The bootstrap CLI
`dummyindex context bootstrap [path] [--root R]` resolves the target via the shared scope helpers, writes the managed block, and prints a one-line confirmation with the resolved absolute path (`dummyindex/cli/bootstrap.py:7-25`). Resolution: `parse_path_and_root` splits the args, and `resolve_context_root` decides where `.context/`/`CLAUDE.md` live — explicit `--root` wins, an absolute `path` is treated as the project root, a relative `path` under cwd returns the enclosing repo root (`dummyindex/cli/bootstrap.py:13-18`, `dummyindex/cli/common.py:13-45`). The target file is always `<out_root>/.claude/CLAUDE.md` (`dummyindex/cli/bootstrap.py:18`). Unknown trailing args exit `2`; `UnbalancedMarkersError` is caught and printed to stderr with exit `3` (`dummyindex/cli/bootstrap.py:14-23`).

### The managed-block write
On a missing file, parent dirs are created and the block is written as the whole file with a trailing newline (`dummyindex/context/output/bootstrap.py:41-45`). On an existing file with no block, the block is appended after existing content with spacing normalized to one blank line (`dummyindex/context/output/bootstrap.py:61-62,70-77`). On an existing file with exactly one block, the block is replaced in place, preserving text before and after it (`dummyindex/context/output/bootstrap.py:63-64,80-83`). Re-running with unchanged body is a no-op on content (idempotent); the write is atomic via a `.tmp` sibling + `replace` so no partial/temp file remains (`dummyindex/context/output/bootstrap.py:86-89`). Malformed markers raise `UnbalancedMarkersError`: begin/end counts differ, or more than one block exists (`dummyindex/context/output/bootstrap.py:48-59`).

### Legacy migration
The body is versioned (`_V0_BLOCK_BODY`) and emitted by `generate_managed_block`; because replace is keyed on the stable begin/end markers rather than body text, an older/larger block is swapped for the current short pointer in place on the next run (`dummyindex/context/output/bootstrap.py:22-30,80-83`). The body is intentionally a terse pointer (≤10 lines, references `.context/HOW_TO_USE.md` and `dummyindex context rebuild --changed`); detailed navigation lives in `HOW_TO_USE.md`, not duplicated here — duplicating it was the bug the shrink fixed (`tests/context/output/test_bootstrap.py:121-132`).

## Contracts

Public functions in `dummyindex/context/output/bootstrap.py`:
- `BEGIN_MARKER` / `END_MARKER` — module-level marker strings delimiting the region (`:11-15`).
- `class UnbalancedMarkersError(ValueError)` — malformed/duplicate markers (`:18-19`).
- `generate_managed_block() -> str` — returns the body without markers (`:28-30`).
- `bootstrap_claude_md(path: Path, *, block_body: Optional[str] = None) -> str` — write/update the managed block, return the final file content (`:33-67`).

Private helpers: `_append_block(existing, managed) -> str` (`:70-77`), `_replace_block(existing, managed) -> str` (`:80-83`), `_atomic_write(path, content) -> None` (`:86-89`).

CLI entry: `run(args: list[str]) -> int` in `dummyindex/cli/bootstrap.py:7-25` (exit codes `0`/`2`/`3`).

## Examples

- Fresh repo: `dummyindex context bootstrap` → creates `.claude/CLAUDE.md` with the marker-wrapped pointer, trailing newline (`tests/context/output/test_bootstrap.py:28-35`).
- Existing CLAUDE.md, no block: block appended after existing content (`tests/context/output/test_bootstrap.py:38-48`).
- Re-run unchanged: output byte-identical to first run (`tests/context/output/test_bootstrap.py:52-57`).
- Block mid-file: surrounding "Before"/"After" text preserved, body swapped (`tests/context/output/test_bootstrap.py:72-87`).
- Unbalanced / duplicate markers: `UnbalancedMarkersError` (`tests/context/output/test_bootstrap.py:89-111`).
