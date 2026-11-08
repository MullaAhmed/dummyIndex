# Bootstrap renderer — plan

confidence: INFERRED

## Bounded context

The renderer owns one marker-delimited region inside a project guidance file. It
owns marker grammar, placement, exact text preservation, safe removal, and atomic
replacement. It also owns Claude's default body and the shared project response
policy. It does not own root resolution, Codex target selection or budget, or
legacy root consolidation (`dummyindex/context/output/bootstrap.py:14-253`,
`dummyindex/cli/bootstrap.py:10-86`, `dummyindex/context/output/claude_md.py:96-269`).

The renderer treats user content as opaque text. Markdown semantics are outside
the boundary. Only standalone marker lines are control syntax. Every create,
update, prepend, append, and removal relies on that rule
(`dummyindex/context/output/bootstrap.py:333-379`,
`dummyindex/context/output/bootstrap.py:446-466`).

## Where it lives

- `dummyindex/context/output/bootstrap.py` is the reusable managed-region engine
  and Claude body provider. It holds the shared policy, markers, validation,
  string assembly, exact reads, and atomic writes.
- `dummyindex/cli/bootstrap.py` is the application boundary. It handles path and
  root parsing, host selection, both-host preflight, error mapping, and output
  (`dummyindex/cli/bootstrap.py:10-86`).
- `dummyindex/context/output/agents_md.py` is a consumer. It supplies Codex
  markers, body, and ownership, and calls the renderer with `place_first=True`
  (`dummyindex/context/output/agents_md.py:17-56`,
  `dummyindex/context/output/agents_md.py:115-167`).
- `dummyindex/context/output/claude_md.py` is a second consumer. It repairs the
  historical root and canonical layout, then emits the current Claude body
  (`dummyindex/context/output/claude_md.py:33-124`).
- `dummyindex/context/__init__.py` re-exports the Claude markers and direct
  renderer, making them package-level compatibility contracts
  (`dummyindex/context/__init__.py:48-54`,
  `dummyindex/context/__init__.py:76-125`).

## Architecture in three sentences

The CLI resolves host targets and preflights both files before a both-host write.
The renderer turns a body and markers into exact text, then commits it through a
symlink-aware unique-temp replace. The Claude reconciler reuses that grammar but
accepts legacy duplicates, folding root and canonical into one recoverable file.

## Rendering and update flow

1. `generate_managed_block` returns the deterministic Claude body. It interpolates
   `ALWAYS_ON_OUTPUT_POLICY` and `ALWAYS_ON_SKILL_POLICY` once each. It routes
   detailed navigation to `.context/HOW_TO_USE.md`
   (`dummyindex/context/output/bootstrap.py:106-118`).
2. The CLI parses root and platform. A both-host run preflights Claude marker and
   path state. It also preflights Codex ownership, path, and budget, before any
   write (`dummyindex/cli/bootstrap.py:20-57`).
3. `bootstrap_claude_md` normalizes the managed body boundary and wraps it in
   markers. It reads existing text without newline translation
   (`dummyindex/context/output/bootstrap.py:155-171`,
   `dummyindex/context/output/bootstrap.py:491-498`).
4. `_managed_block_span` recognizes complete marker lines and returns zero or one
   validated span. Duplicate, dangling, or reversed markers raise before any write
   (`dummyindex/context/output/bootstrap.py:333-379`).
5. The renderer creates a missing file, appends an absent block, replaces a block
   in place, or prepends a host-requested block. It keeps the BOM and user bytes
   (`dummyindex/context/output/bootstrap.py:155-205`,
   `dummyindex/context/output/bootstrap.py:256-299`).
6. `_atomic_write` resolves a symlink leaf to keep the link. It captures the
   target's mode. It writes an exclusive unique sibling temp, replaces atomically,
   and cleans up (`dummyindex/context/output/bootstrap.py:469-515`).
7. `remove_managed_block` uses the same single-span grammar in reverse. It removes
   only the owned region. It deletes an otherwise-empty regular file, or clears a
   symlink target and keeps the link
   (`dummyindex/context/output/bootstrap.py:208-253`).

## Source-evidenced patterns

- **Policy single source, stated not delegated.** `ALWAYS_ON_OUTPUT_POLICY` is
  interpolated by Claude and imported by Codex project guidance. It spells out
  every rule. The upstream `i-have-adhd` skill sets `disable-model-invocation: true`.
  Its SessionStart hook is inert without an opt-in flag, so a reference-only policy
  would leave it inert (`dummyindex/context/output/bootstrap.py:26-62`,
  `dummyindex/context/output/agents_md.py:17-56`).
- **Parameterized managed-region engine.** `block_body`, `begin_marker`,
  `end_marker`, and `place_first` are strategy inputs. Claude uses the defaults.
  Codex supplies its own region identity and front placement
  (`dummyindex/context/output/bootstrap.py:155-205`,
  `dummyindex/context/output/agents_md.py:124-131`).
- **Standalone-marker control plane.** `_standalone_marker_lines` separates control
  syntax from inline quotations and returns exact offsets. Mutation consumes those
  spans, never arbitrary substring searches
  (`dummyindex/context/output/bootstrap.py:333-379`,
  `dummyindex/context/output/bootstrap.py:446-466`).
- **Strict editor, tolerant repair.** Direct update accepts at most one block and
  fails on ambiguity. Legacy consolidation accepts sequential balanced blocks but
  rejects nested, interleaved, reversed, or dangling layouts
  (`dummyindex/context/output/bootstrap.py:333-443`).
- **Pure assembly before side effect.** Append, prepend, replace, prefix handling,
  and separator cleanup build the full final string before `_atomic_write` runs
  (`dummyindex/context/output/bootstrap.py:256-308`,
  `dummyindex/context/output/bootstrap.py:155-205`).
- **Filesystem-aware atomic replace.** Unique exclusive temps prevent adjacent
  collisions. Symlink and mode handling keep the intended guidance target
  (`dummyindex/context/output/bootstrap.py:469-515`).
- **Write-then-delete migration.** Claude consolidation writes canonical before
  deleting root, so a failed write cannot lose the legacy source
  (`dummyindex/context/output/claude_md.py:207-269`).
- **Exact-segment idempotence.** Root residue counts as already folded only when it
  equals canonical residue or its exact final segment. Loose substring coincidence
  never authorizes deletion (`dummyindex/context/output/claude_md.py:190-219`).
- **Closed outcome model.** Layout migration returns `ClaudeMdAction` plus paths,
  message, and warnings. Callers choose how to report or degrade
  (`dummyindex/context/output/claude_md.py:33-72`).

## Dependencies and contracts

- `cli/bootstrap.run` is the direct user entry. It maps argument errors to exit 2
  and preflight, read, or write errors to exit 3
  (`dummyindex/cli/bootstrap.py:10-86`).
- `agents_md.py` depends on the generic renderer and shared policies. It owns Codex
  filename precedence, project ownership, instruction budget, and its separate
  global body (`dummyindex/context/output/agents_md.py:17-73`,
  `dummyindex/context/output/agents_md.py:115-167`,
  `dummyindex/context/output/agents_md.py:360-409`).
- `claude_md.py` depends on the default Claude body, marker identity, the path-scope
  guard, and the multi-span parser. It adds inode identity, residue merge,
  structured degradation, and root deletion
  (`dummyindex/context/output/claude_md.py:22-30`,
  `dummyindex/context/output/claude_md.py:96-336`).
- The build pipeline calls `reconcile_claude_md` when bootstrap is requested. It
  turns warnings into build warnings, not direct-render exceptions
  (`dummyindex/context/build/runner.py:297-303`). Install's enriched refresh
  calls the same reconciler and reports its message
  (`dummyindex/installer/install/project_init.py:96-101`).
- Legacy layout migration is a wire-only wrapper over the reconciler
  (`dummyindex/cli/migrate.py:95-110`).
- Preflight inventory uses `BEGIN_MARKER` as a coarse read-only presence sentinel,
  not proof of a valid block. Mutation must still use the standalone parser
  (`dummyindex/context/domains/preflight/inventory.py:162-166`).
- The managed body depends on `.context/HOW_TO_USE.md` as the navigation authority.
  Tests cap the body at ten lines and require one occurrence of each shared policy
  (`tests/context/output/test_bootstrap.py:205-217`).

## Data model

- `ALWAYS_ON_OUTPUT_POLICY` is immutable project guidance shared by host project
  blocks. It is not config or runtime state
  (`dummyindex/context/output/bootstrap.py:33-62`).
- `BEGIN_MARKER` and `END_MARKER` identify Claude's owned region. Codex supplies a
  separate pair to the same engine, which prevents cross-host ownership collisions
  (`dummyindex/context/output/bootstrap.py:14-18`,
  `dummyindex/context/output/agents_md.py:25-29`).
- `_MarkerLine` carries a standalone line's start, content-end, and line-end
  offsets. `_ManagedBlockSpan` carries replacement and removal boundaries
  (`dummyindex/context/output/bootstrap.py:311-330`).
- `ClaudeMdAction` distinguishes create, consolidate, update, and noop.
  `ClaudeMdReconcileResult` retains paths, a printable message, and warning tuples
  (`dummyindex/context/output/claude_md.py:33-72`).
- Existing content stays an opaque UTF-8 string. BOM and exact newline sequences
  survive outside the owned region
  (`dummyindex/context/output/bootstrap.py:274-291`,
  `dummyindex/context/output/bootstrap.py:469-488`).

## Key decisions

- **Response behavior is shared; host wrapper prose is not.** Claude and Codex
  project blocks consume one output policy and one skill-routing policy. The output
  policy sets three audiences: human replies, subagent and SendMessage text, and
  persisted artifacts. Host navigation, ownership, and global guidance stay in host
  modules (`dummyindex/context/output/bootstrap.py:33-62`,
  `dummyindex/context/output/agents_md.py:33-73`).
- **Per-turn reminder stays short.** `ALWAYS_ON_TURN_REMINDER` restates both
  contracts in short sentences for the UserPromptSubmit hook
  (`dummyindex/context/output/bootstrap.py:87-103`).
- **Marker identity is stable; body text is replaceable.** A policy or navigation
  update converges through the existing region without parsing the old body
  (`dummyindex/context/output/bootstrap.py:155-205`).
- **Only complete marker lines own bytes.** Quoted markers are user content. This
  closes the destructive ambiguity of substring-based replacement
  (`dummyindex/context/output/bootstrap.py:333-379`,
  `dummyindex/context/output/bootstrap.py:446-466`).
- **Ambiguity policy follows the operation.** Direct editing refuses duplicate
  regions because ownership is unclear. Migration repairs sequential complete
  duplicates because consolidation is its purpose
  (`dummyindex/context/output/bootstrap.py:333-443`).
- **Both-host preflight prevents knowable partial writes.** It cannot make two writes
  transactional, but it rejects every deterministic conflict before the first write
  (`dummyindex/cli/bootstrap.py:50-57`).
- **Filesystem structure is user state.** Symlink identity, target mode, umask,
  BOM, newline style, and unrelated bytes are preserved (`dummyindex/context/output/bootstrap.py:229-240`,
  `dummyindex/context/output/bootstrap.py:469-488`).
- **Migration prioritizes recoverability.** Expected marker or filesystem errors
  become `NOOP` plus warnings. Canonical is written before root is removed.
  Inode-shared layouts are refreshed without deletion
  (`dummyindex/context/output/claude_md.py:96-133`,
  `dummyindex/context/output/claude_md.py:135-269`,
  `dummyindex/context/output/claude_md.py:282-336`).
- **Detailed instructions stay out of the host block.** The body is a short stable
  pointer and policy carrier. `.context/HOW_TO_USE.md` owns navigation depth
  (`tests/context/output/test_bootstrap.py:205-217`).

## Open questions

- Should direct bootstrap skip `_atomic_write` when assembled bytes already match?
  Content is idempotent, but the no-op path still replaces the target and can alter
  inode-level metadata.
- Should the renderer return a structured create, append, replace, prepend, or noop
  action? The CLI prints the same success line for every direct-render outcome.
- Should `context bootstrap --platform both` roll back a race after preflight?
  Preflight prevents knowable partial writes, not cross-file transactional failure.
- Should the read-only inventory sentinel adopt `_managed_block_span`? Status would
  then separate a valid block from an inline quotation or malformed layout.
- Should `_V0_BLOCK_BODY` be renamed? Marker-keyed updates make the name behaviorally
  inert, but it understates the body's durable role.
