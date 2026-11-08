# Bootstrap renderer — spec

confidence: INFERRED

## Intent

Render dummyindex's project guidance as one managed, marker-delimited region
that keeps user text intact. The core is a deterministic body, a strict marker
parser, and a byte-preserving writer. Argument and print handling is CLI
plumbing. Claude's body points agents at `.context/` and carries the shared
output and skill-routing policies. The same renderer serves Codex guidance
through custom markers and placement
(`dummyindex/context/output/bootstrap.py:14-23`,
`dummyindex/context/output/bootstrap.py:155-205`).

## User-visible behavior

### Managed body and shared output policy

`generate_managed_block()` returns the Claude body without markers. It points
agents at `.context/HOW_TO_USE.md`. It separates deterministic rebuild from
curated reconciliation. Code and current user intent outrank stale context.
Generated-doc GC stays explicit (`dummyindex/context/output/bootstrap.py:106-118`).

Every Claude project block carries `ALWAYS_ON_OUTPUT_POLICY`, in two paragraphs
for the ten-line cap. Human replies use the `i-have-adhd`
shape at minimum verbosity, not the `caveman` chat voice. Rules are stated in
full, so they hold with neither plugin installed.

Replies lead with the outcome or next action. The old `file:line`-first rule is
gone. Multi-step work is numbered, with at most 5 items per group. Prose
stays compact: no preamble, recap, pleasantries, or empty hedges. Tangents and
untaken options are suppressed. Each turn restates state. Prefer specific
quantities over vague ones. Finished work shows one next action when work remains. Technical, safety, and error text stays verbatim.
Explanations may be fuller. Destructive actions get full sentences.

Subagent prompts and SendMessage bodies use
concise Chinese with caveman rules. Code, commits, PRs, docs, and final reports
stay English. Repo docs use English caveman style, at most 20 words per sentence.
That rule overrides caveman's plain-prose rule for persisted text.

The policy holds for the whole session. When unsure whether it applies, it applies. It yields to explicit user formatting
requests and to safety requirements. It stops on "normal mode", "stop caveman",
or "stop adhd mode", and acknowledges in one line.

The upstream `i-have-adhd`
skill ships `disable-model-invocation: true`. Its plugin's `SessionStart` shell
hook is inert without a per-profile `.i-have-adhd-always` flag, so the plugin
alone is not enough. The project policy is the profile-independent carrier. An
reference-only revision left the ADHD half silently inert, while caveman kept its
own `SessionStart` and `UserPromptSubmit` hooks. The output policy is one constant, inserted once into
the Claude body (`dummyindex/context/output/bootstrap.py:33-62`,
`tests/context/output/test_bootstrap.py:205-217`). Codex's project block reuses
it (`dummyindex/context/output/agents_md.py:17-56`).

`ALWAYS_ON_SKILL_POLICY` makes the host compare each request with exposed skill
triggers. It invokes each match before acting, and treats a user-named skill as
mandatory. It routes dummyindex plan, build, audit, equip, update, remember, and
GC work to the matching family member. `i-have-adhd` is the non-invokable
exception, so its behavior is applied directly.

`ALWAYS_ON_TURN_REMINDER` is injected by the `UserPromptSubmit` hook beside every
prompt. It restates both contracts in short sentences. It is not a third policy
source. `ALWAYS_ON_OUTPUT_POLICY` and `ALWAYS_ON_TURN_REMINDER` pass `lint_text`.
The workflow list in
`ALWAYS_ON_SKILL_POLICY` predates the shipped `dummyindex-fleet` and
`dummyindex-evolve` families (see concerns).

### `context bootstrap`

`dummyindex context bootstrap [path] [--root DIR] [--platform
claude|agents|both]` resolves the project root through shared CLI helpers. Claude
writes `<root>/.claude/CLAUDE.md`. Codex writes its active project instruction
file. Unknown arguments, duplicate `--platform`, and unsupported host values
return exit 2 (`dummyindex/cli/bootstrap.py:10-36`).

`--platform both` is one logical operation. Both targets are preflighted before
either is written. The preflight catches marker, path-boundary, Codex ownership,
and instruction-budget failures. A preflight or write failure returns exit 3 with
an actionable error. Filesystem state can still race after preflight. The command
does not knowingly perform a deterministic partial cross-host write
(`dummyindex/cli/bootstrap.py:50-74`).

After all host writes succeed, platform `claude|both` folds a dangling legacy
root `CLAUDE.md` into the canonical file. It calls `migrate_claude_md_location`,
gated by `has_foldable_legacy_claude_md` (`dummyindex/cli/migrate.py`). The gate
never creates Codex-only guidance or deletes an active Codex instruction
candidate. Platform `agents` never folds. A fold failure warns on stderr and
exits 0, because the primary write already succeeded
(`dummyindex/cli/bootstrap.py:76-86`,
`tests/cli/test_bootstrap_migration.py`).

### Managed-block rendering

On a missing file, the renderer creates parents and writes exactly one managed
block with a trailing newline. On an existing file without a block, it appends
the block after user content. With exactly one block, it replaces that block in
place. `place_first=True` moves the block before user content and keeps a UTF-8
BOM. Codex project guidance uses this mode
(`dummyindex/context/output/bootstrap.py:155-205`,
`dummyindex/context/output/bootstrap.py:256-299`).

Only a begin or end marker that occupies a whole line, after whitespace, is
control syntax. Inline quotations are user prose. Direct bootstrap accepts zero
or one complete pair. It raises `UnbalancedMarkersError` before writing on
duplicates, dangling markers, or reversed order
(`dummyindex/context/output/bootstrap.py:333-379`,
`dummyindex/context/output/bootstrap.py:446-466`). Re-running an unchanged body
is byte-identical. Refreshing the policy preserves user content on both sides of
the region (`tests/context/output/test_bootstrap.py:68-104`,
`tests/context/output/test_bootstrap.py:222-244`).

Reads disable universal-newline translation, so CRLF and mixed endings outside
the region survive. Writes use an exclusive unique sibling temp. They keep the target's mode, replace a symlink's target rather than the link,
and respect the umask for new files. The temp is removed on success or
failure
(`dummyindex/context/output/bootstrap.py:469-515`,
`tests/context/output/test_bootstrap.py:165-183`,
`tests/context/output/test_bootstrap.py:186-200`). A guidance path resolving
outside the project root is rejected before mutation
(`dummyindex/context/output/bootstrap.py:121-137`).

### Removal

`remove_managed_block` removes one validated standalone block and keeps all
surrounding content. If the block is the only non-whitespace content, it deletes
a regular file. For a symlink, it keeps the link and atomically clears the
target. Missing paths and files without a block return `False`. Malformed layouts
raise before any mutation
(`dummyindex/context/output/bootstrap.py:208-253`).

### Root-to-canonical Claude consolidation

`reconcile_claude_md(out_root)` owns legacy layout repair. It reads root
`CLAUDE.md` and canonical `.claude/CLAUDE.md`. It strips every sequential balanced
managed block, merges both files' user residue, and emits one fresh
policy-bearing block. It atomically writes canonical, then deletes root
(`dummyindex/context/output/claude_md.py:75-93`,
`dummyindex/context/output/claude_md.py:124-269`).

Malformed markers, unreadable files, out-of-project symlinks, and write failures
degrade to `NOOP` with warnings and keep the root. If root and canonical are one
inode, the helper refreshes that file and never deletes it. A failed root
deletion is recoverable. Canonical is already written, so the next run recognizes
the folded residue and does not duplicate it
(`dummyindex/context/output/claude_md.py:109-133`,
`dummyindex/context/output/claude_md.py:135-231`,
`dummyindex/context/output/claude_md.py:244-336`).

## Contracts

- `ALWAYS_ON_OUTPUT_POLICY: str` is the single shared project-response policy
  inserted into the generated Claude body. Its rules are stated in full, not
  delegated, because `i-have-adhd` cannot self-invoke
  (`dummyindex/context/output/bootstrap.py:33-62`).
- `ALWAYS_ON_SKILL_POLICY: str` is the shared project skill-routing policy
  (`:69-81`). `ALWAYS_ON_TURN_REMINDER: str` is a bounded per-prompt recurrence of
  both contracts (`:87-103`).
- `generate_managed_block() -> str` returns the marker-free deterministic Claude
  body (`dummyindex/context/output/bootstrap.py:116-118`).
- `ensure_guidance_target_in_scope(project_root: Path, path: Path) -> None`
  rejects writes whose fully resolved target escapes the project root
  (`dummyindex/context/output/bootstrap.py:121-137`).
- `preflight_claude_md(path: Path) -> None` validates an existing target's marker
  grammar without writing (`dummyindex/context/output/bootstrap.py:140-152`).
- `bootstrap_claude_md(path: Path, *, block_body: str | None = None,
  begin_marker: str = BEGIN_MARKER, end_marker: str = END_MARKER,
  place_first: bool = False) -> str` creates, appends, replaces, or prepends one
  managed block and returns the exact final content
  (`dummyindex/context/output/bootstrap.py:155-205`).
- `remove_managed_block(path: Path, *, begin_marker: str = BEGIN_MARKER,
  end_marker: str = END_MARKER, placed_first: bool = False) -> bool` removes one
  validated block without touching unrelated prose
  (`dummyindex/context/output/bootstrap.py:208-253`).
- `run(args: list[str]) -> int` is the host-aware bootstrap CLI boundary. Exit 0
  is success, 2 is argument misuse, and 3 is preflight or write failure
  (`dummyindex/cli/bootstrap.py:10-86`).
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
