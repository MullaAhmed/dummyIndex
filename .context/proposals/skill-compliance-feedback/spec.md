# Spec — Make always-on skill policies self-enforcing through Headroom correction feedback

> Scaffolded by `dummyindex context propose`. Flesh out the intent
> and contracts below, then keep the **Acceptance** checklist honest.

## Intent

dummyindex already installs a profile-independent per-turn instruction telling
Claude to inspect and invoke matching skills, but it has no feedback loop when
the model ignores that instruction. The Headroom-derived failure miner is a
deterministic, repo-scoped pilot that is not consumed by any runtime path. That
is why a user can repeatedly say “use the ADHD skill” across standard Claude
and alternate profiles without the miss becoming durable corrective context.

Add a privacy-safe Headroom-derived branch for skill compliance: mine repeated,
explicit human corrections about any named skill into local generated state,
and inject a bounded reminder beside future prompts. The current prompt is also
checked so the first explicit correction affects that same response.
`i-have-adhd` remains the documented non-invokable exception: its reminder says
to apply the output behavior directly. Other exposed skills remain
model-invoked according to their trigger rules.

## Contracts

### Deterministic correction signal

- A candidate comes only from a root-level main transcript and an external
  human `user` event whose row-level `cwd` resolves exactly to the target repo.
  Tool results, assistant content, sidechains, nested `subagents/`, meta/task
  events, `last-prompt` cache rows, and rows with absent/foreign `cwd` never
  count. The row-level check closes collisions in Claude's lossy
  separator-to-hyphen project-directory encoding.
- A high-confidence positive directive must be either a direct imperative or a
  complaint that explicitly pairs `use`, `invoke`, `apply`, or `follow` with a
  named `... skill`. Questions about creating/explaining a skill, quoted/code
  examples, and negated instructions are rejected.
- `do not`/`don't`/`never`/`stop ... <name> skill`, `normal mode`, and
  `stop adhd mode` are revocations. Events are ordered by their transcript
  timestamp with a deterministic file/line fallback. A revocation clears older
  positives for that skill; durable feedback requires two distinct positive
  events after the latest revocation.
- Event UUIDs are deduplicated across resumed/forked transcripts. Older
  transcript rows without UUIDs use a stable content-event fingerprint so the
  same copied row still counts once. Repeating the same request at a different
  timestamp remains a distinct correction.
- Skill names normalize to `[a-z0-9][a-z0-9-]{0,63}`. `adhd`, `adhd-mode`, and
  `i have adhd` normalize to `i-have-adhd`; detection is otherwise generic and
  does not carry a fixed allowlist.

### Profile aggregation and bounded work

- An explicit config-dir override scans only that directory. Normal hook runs
  aggregate a sorted, deduplicated set containing the active
  `CLAUDE_CONFIG_DIR`, `~/.claude`, and home sibling directories matching
  `.claude-*` that contain the target repo's exact project directory. This makes
  standard Claude and claude-os one feedback source instead of last-writer-wins
  profiles.
- Historical mining opens only root-level `*.jsonl` main transcripts in those
  exact project directories; it never recursively opens subagent transcripts.
  The BOS evidence used to select this seam is 62 main files/about 97 MiB and
  about 0.58 seconds across both profiles, versus 1,150 recursive files/about
  560 MiB. Tests enforce the file-work boundary, not a flaky wall-clock limit.
- `failure-patterns.md` and the legacy tool-signature miner remain explicit and
  unwired. Structured tool inputs can contain commands, edit bodies, prompts,
  and tokens, so an automatic hook must not render them into a tracked report.

### Local cache and prompt-safety boundary

- Historical feedback is generated at
  `.context/cache/skill-feedback.json` **(NEW)**, the existing gitignored,
  per-machine cache layer. Schema version 1 stores at most 64 entries shaped
  exactly as `{"skill": <safe slug>, "corrections": <positive int>,
  "sessions": <positive int>}` in deterministic
  `(-corrections, skill)` order. It stores no prompt text, path, UUID,
  timestamp, profile name, tool input/output, or excerpt.
- The cache is serialized through the indexed `write_text_atomic` seam, upgraded
  in this proposal to use unique same-directory temporary files so concurrent
  session writers cannot collide on one `.tmp` name. First-run empty mining
  creates no cache; an existing non-empty cache transitions to a valid empty
  payload when revoked/stale; byte-identical output is not rewritten.
- Runtime reads reject symlinks, files over 32 KiB, unknown schema/keys, invalid
  types/counts/slugs/order, and more than 64 entries. They never inject cache
  bytes directly: validated records are re-rendered into fixed product text.
- Prompt feedback includes at most 8 skills and 1,600 characters, ordered by
  `(-corrections, skill)`. A recurring generic skill is a conditional rule:
  invoke it when currently exposed and its trigger matches or the user names
  it. `i-have-adhd` says to apply its behavior directly unless the user opted
  out. A positive directive in the current prompt is mandatory on that same
  turn even before the durable two-event threshold; a current revocation
  suppresses that skill.

### Runtime delivery

- `dummyindex context memory mine [path] [--root DIR]` **(NEW)** performs the
  historical, multi-profile, main-thread-only cache refresh best-effort.
  `SessionStart` runs it silently once; `Stop` remains unchanged and never
  rescans history.
- `dummyindex context memory prompt-context [path] [--root DIR]` **(NEW)** reads
  `UserPromptSubmit` stdin through the indexed `read_hook_stdin` seam, combines
  a safe current directive with validated cached feedback, and emits one compact
  `hookSpecificOutput.additionalContext` JSON payload or nothing.
- The existing static UserPromptSubmit command retains no local CLI self-gate
  and remains the cross-profile fallback. The CLI-backed command is independently
  valid, fail-open, and silent when the CLI/cache/transcripts are unavailable;
  no execution ordering between matching Claude hook commands is assumed.
  Local/global defer behavior and the exact five-event `HookStatus` contract do
  not change.
- Hook commands never call a model, network service, plugin registry, or
  deterministic backbone rebuild.

### Index drift noted during planning

The current source contains the Headroom-derived `memory/miner/` pilot, but
`.context/map/symbols.json` predates those modules and does not list
`mine_and_feed`, `scan_transcript_store`, or `render_report`. The code is
authoritative. `_hooks_for_scope` is indexed as `hooks_hooks_for_scope`, but its
map line is stale; source at `dummyindex/context/hooks.py:386` wins. The opened
`.context/PROJECT.md` is also stale at version 0.28.0 versus `pyproject.toml`
0.34.0, and the related equip spec's old SHA-pin statement contradicts
`dummyindex/context/default_plugins.py`. None governs this implementation;
normal post-build reconciliation will refresh the index.

## Acceptance

- [ ] `.venv/bin/python -m pytest tests/context/domains/memory/miner -q
  --tb=short -p no:cacheprovider` proves positive/revocation parsing,
  false-positive rejection, event deduplication, two-profile union, row-level
  repo scoping (including an encoded-name collision), main-only file work,
  deterministic aggregation, strict cache validation, concurrent atomic writes,
  no-rewrite/empty transitions, exact 64/8/1,600/32-KiB bounds, and zero raw
  prompt leakage.
- [ ] `.venv/bin/python -m pytest
  tests/context/domains/memory/test_memory_cli.py -q --tb=short
  -p no:cacheprovider` proves the two new verbs, current-prompt same-turn
  feedback/revocation, fail-open behavior, and exact silent-or-valid
  `UserPromptSubmit` JSON.
- [ ] `.venv/bin/python -m pytest tests/cli/test_cli_doc_sync.py -q --tb=short
  -p no:cacheprovider` proves every `MemoryVerb` value appears in context help.
- [ ] `.venv/bin/python -m pytest tests/context/test_hooks.py -q --tb=short
  -p no:cacheprovider` proves local/global installs wire one SessionStart miner
  and one independent dynamic per-prompt command, do not add a Stop scan,
  execute safely with missing/malformed state, preserve the static fallback and
  user hooks, and remain byte-idempotent.
- [ ] A fixture shaped like the BOS Claude transcript
  (`origin.kind=human`, `userType=external`, string content containing repeated
  ADHD corrections) yields `i-have-adhd` feedback, while a second generic skill
  yields its own slug; this is asserted in
  `tests/context/domains/memory/miner/test_corrections.py`.
- [ ] `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q
  --tb=short -p no:cacheprovider`, `ruff check --no-cache .`, and
  `ruff format --check .` all pass after implementation and documentation.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `session-memory`
- `install-surface`
- `equip`
- `agent-instructions`
- `bootstrap`
- `council`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
