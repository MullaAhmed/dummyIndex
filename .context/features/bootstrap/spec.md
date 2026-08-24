# Bootstrap renderer — spec

confidence: INFERRED

## Intent

Render dummyindex's project guidance as one managed, marker-delimited region
without disturbing user-authored instructions around it. The core contract is a
deterministic body plus a strict marker parser and byte-preserving writer;
argument parsing and success/error printing are CLI plumbing. Claude's managed
body points agents at `.context/` and carries the shared always-on
caveman/i-have-adhd output policy plus automatic skill-routing policy, while
the same renderer remains reusable for Codex project guidance through custom
markers, body, and placement
(`dummyindex/context/output/bootstrap.py:14-23`,
`dummyindex/context/output/bootstrap.py:143-193`).

## User-visible behavior

### Managed body and shared output policy

`generate_managed_block()` returns the Claude body without begin/end markers.
It tells agents to read `.context/HOW_TO_USE.md`, distinguishes deterministic
rebuild from curated reconciliation, makes code and current user intent
authoritative over stale context, and keeps generated-doc garbage collection
explicit (`dummyindex/context/output/bootstrap.py:94-106`).

Every generated Claude project block also applies one always-on response policy.
It names the combined caveman/i-have-adhd behavior but **states every rule
self-containedly**, so it holds with neither plugin installed: lead with the
outcome or next action (command, path, or `file:line` first); keep prose compact;
number multi-step work one bounded action per step; suppress tangents and
untaken options; restate current state each turn; prefer specific quantities to
vague ones; make finished work visible and end with one concrete next action; and
compress prose but never substance, keeping identifiers, commands, and error
strings verbatim. A persistence clause stops it lapsing across turns or topic
changes, and it stops on explicit request ("normal mode", "stop caveman", "stop
adhd mode"). Explicit user formatting and safety requirements always win.

Self-containment is load-bearing, not stylistic. The upstream `i-have-adhd`
skill ships `disable-model-invocation: true`; its current plugin also has a
`SessionStart` shell hook, but that hook is inert without a per-profile
`.i-have-adhd-always` flag. Enabling the plugin alone is therefore not enough,
and the project policy is the profile-independent carrier. An earlier revision
only *referenced* the two skills, which left the ADHD half silently inert while
caveman still worked through its own `SessionStart`/`UserPromptSubmit` hooks.
The output policy is one
constant inserted exactly once into the Claude body
(`dummyindex/context/output/bootstrap.py:33-53`,
`tests/context/output/test_bootstrap.py:202-216`) and is reused by Codex's
project block rather than duplicated (`dummyindex/context/output/agents_md.py:17-56`).

The adjacent always-on skill-routing policy requires the host to compare every
request with its exposed skill descriptions and trigger rules, invoke each
match before acting, and treat a user-named skill as mandatory. It explicitly
routes dummyindex plan/build/audit/equip/update/remember/GC work to the matching
family member while treating `i-have-adhd` as the non-invokable exception whose
behavior is applied directly. `ALWAYS_ON_TURN_REMINDER` is a bounded recurrence
of both contracts for Claude's per-prompt hook; it is not a third policy source.
(The enumeration in both constants predates the shipped `dummyindex-fleet` and
`dummyindex-evolve` families — see concerns.)

### `context bootstrap`

`dummyindex context bootstrap [path] [--root DIR] [--platform
claude|agents|both]` resolves the project root through shared CLI helpers. Claude
writes `<root>/.claude/CLAUDE.md`; Codex writes its active project instruction
file. Unknown arguments, duplicate `--platform`, and unsupported host values
return exit 2 (`dummyindex/cli/bootstrap.py:10-34`).

`--platform both` is one logical operation: both targets are preflighted before
either is written. The preflight catches deterministic marker, path-boundary,
Codex ownership, and instruction-budget failures up front; a preflight or write
failure returns exit 3 and prints an actionable error. Filesystem state can still
race after preflight, but the command does not knowingly perform a deterministic
partial cross-host write (`dummyindex/cli/bootstrap.py:35-69`).

### Managed-block rendering

On a missing file, the renderer creates parents and writes exactly one managed
block with a trailing newline. On an existing file without a managed block, it
appends the block after user content; with exactly one block, it replaces that
block in place. `place_first=True` moves the block before user content while
preserving a UTF-8 BOM and is the mode used by Codex project guidance
(`dummyindex/context/output/bootstrap.py:143-193`,
`dummyindex/context/output/bootstrap.py:244-287`).

Only a begin or end marker that occupies a complete line after whitespace is
control syntax. Inline quotations are user prose. Direct bootstrap accepts zero
or one complete pair and raises `UnbalancedMarkersError` before writing on
duplicates, dangling markers, or reversed order
(`dummyindex/context/output/bootstrap.py:321-367`,
`dummyindex/context/output/bootstrap.py:434-454`). Re-running an unchanged body
is byte-identical, and refreshing the policy preserves user content on both sides
of the managed region (`tests/context/output/test_bootstrap.py:68-104`,
`tests/context/output/test_bootstrap.py:218-241`).

Reads disable universal-newline translation, so CRLF and mixed line endings
outside the managed region survive. Writes use a unique sibling temp created
with exclusive creation, preserve the target's existing mode, replace a symlink
target rather than the link itself, respect process umask for a new file, and
remove any temp on failure or success
(`dummyindex/context/output/bootstrap.py:457-503`,
`tests/context/output/test_bootstrap.py:165-183`,
`tests/context/output/test_bootstrap.py:186-200`). A guidance path resolving
outside the project root is rejected before mutation
(`dummyindex/context/output/bootstrap.py:109-125`).

### Removal

`remove_managed_block` removes only one validated standalone block and preserves
all surrounding content. If the block is the only non-whitespace content, it
deletes a regular file; for a symlink it retains the link and atomically clears
the target. Missing paths and files without a block return `False`; malformed
marker layouts raise before mutation
(`dummyindex/context/output/bootstrap.py:196-241`).

### Root-to-canonical Claude consolidation

`reconcile_claude_md(out_root)` owns legacy layout repair. It reads root
`CLAUDE.md` and canonical `.claude/CLAUDE.md`, strips every sequential balanced
managed block using the same whole-line grammar, merges both files' user residue,
emits one fresh policy-bearing block, atomically writes canonical, and only then
deletes root (`dummyindex/context/output/claude_md.py:75-107`,
`dummyindex/context/output/claude_md.py:124-269`).

Malformed markers, unreadable files, out-of-project symlinks, and write failures
degrade to `NOOP` with warnings and preserve the root. If root and canonical are
the same inode, the helper refreshes that one file and never deletes it. A failed
root deletion is recoverable because the canonical write already succeeded and
the next run recognizes an exact previously-folded residue instead of duplicating
it (`dummyindex/context/output/claude_md.py:109-133`,
`dummyindex/context/output/claude_md.py:135-231`,
`dummyindex/context/output/claude_md.py:244-336`).

## Contracts

- `ALWAYS_ON_OUTPUT_POLICY: str` is the single shared project-response policy
  inserted into the generated Claude body. Its rules are stated in full rather
  than delegated to the named skills, because `i-have-adhd` cannot self-invoke
  (`dummyindex/context/output/bootstrap.py:33-53`).
- `ALWAYS_ON_SKILL_POLICY: str` is the shared project skill-routing policy
  (`:60-72`), and `ALWAYS_ON_TURN_REMINDER: str` is its bounded Claude
  per-prompt recurrence alongside the output shape (`:78-91`).
- `generate_managed_block() -> str` returns the marker-free deterministic Claude
  body (`dummyindex/context/output/bootstrap.py:104-106`).
- `ensure_guidance_target_in_scope(project_root: Path, path: Path) -> None`
  rejects writes whose fully resolved target escapes the project root
  (`dummyindex/context/output/bootstrap.py:109-125`).
- `preflight_claude_md(path: Path) -> None` validates an existing target's marker
  grammar without writing (`dummyindex/context/output/bootstrap.py:128-140`).
- `bootstrap_claude_md(path: Path, *, block_body: str | None = None,
  begin_marker: str = BEGIN_MARKER, end_marker: str = END_MARKER,
  place_first: bool = False) -> str` creates, appends, replaces, or prepends one
  managed block and returns the exact final content
  (`dummyindex/context/output/bootstrap.py:143-193`).
- `remove_managed_block(path: Path, *, begin_marker: str = BEGIN_MARKER,
  end_marker: str = END_MARKER, placed_first: bool = False) -> bool` removes one
  validated block without touching unrelated prose
  (`dummyindex/context/output/bootstrap.py:196-241`).
- `run(args: list[str]) -> int` is the host-aware bootstrap CLI boundary; exit 0
  is success, 2 is argument misuse, and 3 is deterministic preflight/write
  failure (`dummyindex/cli/bootstrap.py:10-74`).
- `reconcile_claude_md(out_root: Path) -> ClaudeMdReconcileResult` consolidates
  legacy and canonical Claude guidance and returns a frozen result rather than
  printing (`dummyindex/context/output/claude_md.py:57-72`,
  `dummyindex/context/output/claude_md.py:96-269`).

## Examples

```bash
dummyindex context bootstrap
dummyindex context bootstrap ./repo --platform claude
dummyindex context bootstrap ./repo --platform agents   # `codex` accepted as deprecated alias
dummyindex context bootstrap ./repo --platform both
dummyindex context bootstrap --root /work/repo --platform both
```

- Missing Claude target: creates `.claude/CLAUDE.md` with one managed block and
  trailing newline (`tests/context/output/test_bootstrap.py:32-41`).
- Existing user prose: appends or replaces the managed region without moving the
  prose (`tests/context/output/test_bootstrap.py:55-104`).
- Inline marker quotation: remains prose and does not count as control syntax
  (`tests/context/output/test_bootstrap.py:133-148`).
- Legacy root plus canonical file: merges both user bodies, emits one fresh
  block, and removes root (`tests/context/output/test_claude_md.py:101-121`).
- Real build, init, and enriched reinstall paths converge on the same canonical
  layout (`tests/context/output/test_claude_md_build.py:73-205`).
