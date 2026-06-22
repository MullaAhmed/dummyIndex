# Bootstrap renderer — spec

confidence: INFERRED

## Intent

Render and idempotently regenerate the dummyindex-managed block inside `<root>/.claude/CLAUDE.md` so a freshly-indexed repo always carries a short, current pointer at `.context/HOW_TO_USE.md`. The renderer owns exactly one delimited region of the file and never touches surrounding content; re-running it converges on the same output (`dummyindex/context/output/bootstrap.py:1-5`).

A sibling helper, `reconcile_claude_md` (`dummyindex/context/output/claude_md.py:1-13`), raises the unit of work from "the block inside one file" to "the whole CLAUDE.md *layout*": it folds a pre-existing root `<root>/CLAUDE.md` (a legacy managed block, plain hand-written content, or both) AND any existing canonical `<root>/.claude/CLAUDE.md` into ONE canonical `.claude/CLAUDE.md` carrying exactly one fresh managed block, then deletes the root file. It is now the single consolidation seam the real build/install/migrate paths call (`build/runner.py:263`, `installer/install.py:276`, `cli/migrate.py:84`), so a dangling root `CLAUDE.md` is never left behind. Like the block renderer it is a domain helper, not a CLI — it returns a frozen result and never prints (`claude_md.py:10-12`).

## User-visible behavior

### The bootstrap CLI
`dummyindex context bootstrap [path] [--root R]` resolves the target via the shared scope helpers, writes the managed block, and prints a one-line confirmation with the resolved absolute path (`dummyindex/cli/bootstrap.py:7-25`). Resolution: `parse_path_and_root` splits the args, and `resolve_context_root` decides where `.context/`/`CLAUDE.md` live — explicit `--root` wins, an absolute `path` is treated as the project root, a relative `path` under cwd returns the enclosing repo root (`dummyindex/cli/bootstrap.py:13-18`, `dummyindex/cli/common.py:13-45`). The target file is always `<out_root>/.claude/CLAUDE.md` (`dummyindex/cli/bootstrap.py:18`). Unknown trailing args exit `2`; `UnbalancedMarkersError` is caught and printed to stderr with exit `3` (`dummyindex/cli/bootstrap.py:14-23`).

### The managed-block write
On a missing file, parent dirs are created and the block is written as the whole file with a trailing newline (`dummyindex/context/output/bootstrap.py:41-45`). On an existing file with no block, the block is appended after existing content with spacing normalized to one blank line (`dummyindex/context/output/bootstrap.py:61-62,70-77`). On an existing file with exactly one block, the block is replaced in place, preserving text before and after it (`dummyindex/context/output/bootstrap.py:63-64,80-83`). Re-running with unchanged body is a no-op on content (idempotent); the write is atomic via a `.tmp` sibling + `replace` so no partial/temp file remains (`dummyindex/context/output/bootstrap.py:86-89`). Malformed markers raise `UnbalancedMarkersError`: begin/end counts differ, or more than one block exists (`dummyindex/context/output/bootstrap.py:48-59`).

### Legacy migration
The body is versioned (`_V0_BLOCK_BODY`) and emitted by `generate_managed_block`; because replace is keyed on the stable begin/end markers rather than body text, an older/larger block is swapped for the current short pointer in place on the next run (`dummyindex/context/output/bootstrap.py:22-30,80-83`). The body is intentionally a terse pointer (≤10 lines, references `.context/HOW_TO_USE.md` and `dummyindex context rebuild --changed`); detailed navigation lives in `HOW_TO_USE.md`, not duplicated here — duplicating it was the bug the shrink fixed (`tests/context/output/test_bootstrap.py:121-132`).

### Root → canonical consolidation
`reconcile_claude_md(out_root)` reads the root `<out_root>/CLAUDE.md` and the canonical `<out_root>/.claude/CLAUDE.md`, computes each file's *user residue* (the text with every managed block stripped, trimmed — `claude_md.py:136-138`), folds them above one fresh managed block, writes the canonical atomically via `write_text_atomic`, then deletes the root file — **only after** the write succeeds (`claude_md.py:255-301`). It reuses `BEGIN_MARKER`/`END_MARKER`/`generate_managed_block` from `bootstrap.py` (`claude_md.py:22-26`) so both seams share one marker grammar and one block body. Behavior is governed by four guarantees:
- **Inode-safety (R1)**: if root and canonical resolve to the same inode (a symlink or hardlink), there is nothing to consolidate and deleting would destroy the only copy — the managed block is refreshed in place and the file is never deleted (`claude_md.py:163-166,304-367`).
- **Strip-all-blocks (R2/R3)**: `_strip_all_managed_blocks` loops over *every* BEGIN→END block (not just the first), anchored to whole-line markers, so duplicate blocks all collapse and prose that merely quotes a marker substring mid-line is preserved verbatim (`claude_md.py:86-112`).
- **Never crash on malformed markers (R2)**: unbalanced standalone markers degrade to a `NOOP` result with a warning, leaving the offending file untouched — they never raise (`claude_md.py:123-133,183-221`).
- **Idempotent merge / user content never lost (R4)**: the root residue is folded only when it was not already folded; the guard matches the *exact* folded form (equal to, or the trailing appended segment of, the canonical residue) rather than a loose substring, so a failed-delete + rerun never doubles content and a coincidental fragment is never silently dropped (`claude_md.py:224-243`).
A second run on unchanged input is a `NOOP` (`claude_md.py:245-253`). Filesystem failures — unreadable root, unreadable/failed-write canonical, failed delete — each degrade to a non-fatal result with a warning; a failed delete still reports `CONSOLIDATED` because the canonical write already succeeded (`claude_md.py:174-210,256-294`).

## Contracts

Public functions in `dummyindex/context/output/bootstrap.py`:
- `BEGIN_MARKER` / `END_MARKER` — module-level marker strings delimiting the region (`:11-15`).
- `class UnbalancedMarkersError(ValueError)` — malformed/duplicate markers (`:18-19`).
- `generate_managed_block() -> str` — returns the body without markers (`:28-30`).
- `bootstrap_claude_md(path: Path, *, block_body: Optional[str] = None) -> str` — write/update the managed block, return the final file content (`:33-67`).

Private helpers: `_append_block(existing, managed) -> str` (`:70-77`), `_replace_block(existing, managed) -> str` (`:80-83`), `_atomic_write(path, content) -> None` (`:86-89`).

CLI entry: `run(args: list[str]) -> int` in `dummyindex/cli/bootstrap.py:7-25` (exit codes `0`/`2`/`3`).

Public surface in `dummyindex/context/output/claude_md.py`:
- `class ClaudeMdAction(str, Enum)` — closed alphabet of outcomes: `CREATED` / `CONSOLIDATED` / `UPDATED` / `NOOP`; `__str__` is pinned to the str value so it renders as `"consolidated"`, never `ClaudeMdAction.CONSOLIDATED` (`:29-49`).
- `@dataclass(frozen=True) class ClaudeMdReconcileResult` — `action`, `root_path`, `canonical_path`, `message` (CLI-printable), `warnings: tuple[str, ...]` (`:52-68`).
- `reconcile_claude_md(out_root: Path) -> ClaudeMdReconcileResult` — fold root + canonical into one canonical managed file; never raises for expected fs/marker conditions (`:141-301`).

Callers: `build/runner.py:263` (final step of `build_all` when `bootstrap=True`; `init` dispatch routes here), `installer/install.py:276` (`_auto_init_project`, including the `status.enriched` re-install branch), and `cli/migrate.py:84` — the single consolidation seam.

## Examples

- Fresh repo: `dummyindex context bootstrap` → creates `.claude/CLAUDE.md` with the marker-wrapped pointer, trailing newline (`tests/context/output/test_bootstrap.py:28-35`).
- Existing CLAUDE.md, no block: block appended after existing content (`tests/context/output/test_bootstrap.py:38-48`).
- Re-run unchanged: output byte-identical to first run (`tests/context/output/test_bootstrap.py:52-57`).
- Block mid-file: surrounding "Before"/"After" text preserved, body swapped (`tests/context/output/test_bootstrap.py:72-87`).
- Unbalanced / duplicate markers: `UnbalancedMarkersError` (`tests/context/output/test_bootstrap.py:89-111`).

Consolidation (`reconcile_claude_md`):
- Root has a legacy block + user residue: `CONSOLIDATED`, root deleted, old block stripped, exactly one fresh block in canonical (`tests/context/output/test_claude_md.py:44-59`).
- Pre-existing canonical (user + block) AND a root file: both bodies merged, neither duplicated, one block (`tests/context/output/test_claude_md.py:102-122`).
- Idempotent second run: `NOOP`, byte-identical canonical (`tests/context/output/test_claude_md.py:128-140`).
- Inode-shared (symlink/hardlink) root↔canonical: file survives, never deleted, residue preserved (`tests/context/output/test_claude_md.py:146-167`).
- Unbalanced markers in root or canonical: `NOOP` + warning, file untouched, never raises (`tests/context/output/test_claude_md.py:173-203`).
- Duplicate balanced blocks: all stripped, exactly one re-emitted (`tests/context/output/test_claude_md.py:208-224`).
- Prose quoting markers mid-line: preserved verbatim, not counted as a block (`tests/context/output/test_claude_md.py:230-250`).
- Unreadable root / injected write failure: `NOOP` + warning, root content intact (`tests/context/output/test_claude_md.py:256-291`).
- Real build/install seams (`build_all`, `init` dispatch, `_auto_init_project` incl. the enriched re-install branch) fold a seeded root file into one canonical block (`tests/context/output/test_claude_md_build.py:72-205`).
