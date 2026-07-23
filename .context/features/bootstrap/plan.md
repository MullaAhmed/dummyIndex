# Bootstrap renderer — plan

confidence: INFERRED

## Bounded context

The bootstrap renderer owns one marker-delimited region inside a project guidance
file. It owns marker grammar, placement, exact surrounding-text preservation,
safe removal, and atomic filesystem replacement. It also owns Claude's default
managed body and the shared project response policy, but it does not own project
root resolution, Codex target selection/ownership/budget, or legacy root-file
consolidation (`dummyindex/context/output/bootstrap.py:14-180`,
`dummyindex/cli/bootstrap.py:10-71`,
`dummyindex/context/output/claude_md.py:96-269`).

The renderer treats user content as opaque text. Markdown semantics are outside
the boundary; only standalone marker lines are control syntax. That constraint is
the basis for every create, update, prepend, append, and removal operation
(`dummyindex/context/output/bootstrap.py:260-306`,
`dummyindex/context/output/bootstrap.py:373-425`).

## Where it lives

- `dummyindex/context/output/bootstrap.py` is the reusable managed-region engine
  and Claude body provider: shared policy, default/parameterized markers,
  validation, string assembly, exact reads, and atomic writes.
- `dummyindex/cli/bootstrap.py` is the application boundary: path/root parsing,
  host selection, both-host preflight, error mapping, and user-visible output
  (`dummyindex/cli/bootstrap.py:10-71`).
- `dummyindex/context/output/agents_md.py` is a consumer. It supplies Codex
  markers/body/ownership and invokes the same renderer with `place_first=True`;
  the project block imports the shared response policy
  (`dummyindex/context/output/agents_md.py:17-52`,
  `dummyindex/context/output/agents_md.py:110-161`).
- `dummyindex/context/output/claude_md.py` is a second consumer. It repairs the
  historical root/canonical layout with a multi-block parser and structured
  outcomes, then emits the current Claude body
  (`dummyindex/context/output/claude_md.py:33-124`).
- `dummyindex/context/__init__.py` re-exports the Claude markers and direct
  renderer, making their identities package-level compatibility contracts
  (`dummyindex/context/__init__.py:48-54`,
  `dummyindex/context/__init__.py:76-105`).

## Architecture in three sentences

The CLI resolves host-specific targets and preflights both files before a
both-host write, while each host module owns its body, target policy, and
ownership rules. The renderer converts one body plus markers and placement into
an exact updated text, validates a single unambiguous managed region, and commits
through a symlink-aware unique-temp replacement. The Claude reconciler reuses the
same body and marker grammar but deliberately accepts sequential legacy duplicates
so it can fold root and canonical files into one recoverable final layout.

## Rendering and update flow

1. `generate_managed_block` returns the deterministic Claude body. The body
   interpolates `ALWAYS_ON_OUTPUT_POLICY` once and routes detailed navigation to
   `.context/HOW_TO_USE.md` (`dummyindex/context/output/bootstrap.py:26-45`).
2. The CLI parses root and platform. A both-host invocation resolves and
   preflights Claude marker/path state plus Codex ownership/path/budget before
   either write (`dummyindex/cli/bootstrap.py:17-52`).
3. `bootstrap_claude_md` normalizes only the managed body boundary, constructs
   the marker-wrapped block, and reads existing content without newline
   translation (`dummyindex/context/output/bootstrap.py:82-112`,
   `dummyindex/context/output/bootstrap.py:418-425`).
4. `_managed_block_span` recognizes complete marker lines and returns zero or one
   validated span. Duplicate, dangling, or reversed control markers raise before
   text assembly or write (`dummyindex/context/output/bootstrap.py:260-306`).
5. The renderer creates a missing file, appends an absent block, replaces an
   existing block in place, or prepends a host-requested block while retaining
   BOM and user bytes (`dummyindex/context/output/bootstrap.py:100-132`,
   `dummyindex/context/output/bootstrap.py:183-235`).
6. `_atomic_write` resolves a symlink leaf to preserve the link, captures an
   existing target mode, writes through an exclusive unique sibling temp, applies
   the mode, replaces atomically, and cleans up the temp
   (`dummyindex/context/output/bootstrap.py:396-442`).
7. `remove_managed_block` uses the same single-span grammar in reverse. It removes
   only the owned region, deletes an otherwise-empty regular file, or clears a
   symlink target without deleting the link
   (`dummyindex/context/output/bootstrap.py:135-180`).

## Source-evidenced patterns

- **Policy single source.** `ALWAYS_ON_OUTPUT_POLICY` is interpolated by Claude
  and imported by Codex project guidance. Response behavior changes have one
  source and one explicit user/safety override
  (`dummyindex/context/output/bootstrap.py:26-40`,
  `dummyindex/context/output/agents_md.py:17-52`).
- **Parameterized managed-region engine.** `block_body`, `begin_marker`,
  `end_marker`, and `place_first` are strategy inputs. Claude uses defaults;
  Codex supplies its own region identity and front placement
  (`dummyindex/context/output/bootstrap.py:82-132`,
  `dummyindex/context/output/agents_md.py:121-129`).
- **Standalone-marker control plane.** `_standalone_marker_lines` separates
  control syntax from inline quotations and returns exact offsets; mutation code
  consumes spans rather than searching arbitrary substrings
  (`dummyindex/context/output/bootstrap.py:238-306`,
  `dummyindex/context/output/bootstrap.py:373-393`).
- **Strict editor / tolerant repair split.** Direct update accepts at most one
  block and fails on ambiguity; legacy consolidation accepts multiple sequential
  balanced blocks but still rejects nested, interleaved, reversed, or dangling
  layouts (`dummyindex/context/output/bootstrap.py:260-370`).
- **Pure assembly before side effect.** Append, prepend, replace, prefix handling,
  and separator cleanup produce the complete final string before `_atomic_write`
  runs (`dummyindex/context/output/bootstrap.py:114-132`,
  `dummyindex/context/output/bootstrap.py:183-235`).
- **Filesystem-aware atomic replace.** Unique exclusive temps prevent adjacent
  temp collisions; symlink and mode handling preserve the intended guidance
  target rather than replacing filesystem structure
  (`dummyindex/context/output/bootstrap.py:396-442`).
- **Write-then-delete migration.** Claude consolidation writes canonical before
  deleting root, so failed writes cannot lose the legacy source
  (`dummyindex/context/output/claude_md.py:207-269`).
- **Exact-segment idempotence.** Reconciliation treats root residue as already
  folded only when it equals canonical residue or its exact final segment; loose
  substring coincidence never authorizes deletion
  (`dummyindex/context/output/claude_md.py:190-219`).
- **Closed outcome model.** Layout migration returns `ClaudeMdAction` plus paths,
  message, and warnings; callers choose how to report or degrade
  (`dummyindex/context/output/claude_md.py:33-72`).

## Dependencies and contracts

- `cli/bootstrap.run` is the direct user entry. It treats argument errors as exit
  2 and deterministic preflight/read/write errors as exit 3
  (`dummyindex/cli/bootstrap.py:10-71`).
- `agents_md.py` depends on the generic renderer and shared policy, but owns Codex
  filename precedence, project ownership, instruction budget, and its separate
  global body (`dummyindex/context/output/agents_md.py:17-65`,
  `dummyindex/context/output/agents_md.py:110-180`).
- `claude_md.py` depends on the default Claude body, marker identity, path-scope
  guard, and multi-span parser. It adds inode identity, residue merge, structured
  degradation, and root deletion (`dummyindex/context/output/claude_md.py:22-30`,
  `dummyindex/context/output/claude_md.py:96-336`).
- The build pipeline calls `reconcile_claude_md` when bootstrap is requested and
  converts warnings into build warnings rather than direct-render exceptions
  (`dummyindex/context/build/runner.py:280-288`). Install's enriched-refresh path
  calls the same reconciler and reports its message
  (`dummyindex/installer/install.py:404-409`).
- Legacy layout migration is a wire-only wrapper over the reconciler
  (`dummyindex/cli/migrate.py:74-89`).
- Preflight inventory uses `BEGIN_MARKER` as a coarse read-only presence sentinel,
  not as proof of a valid block. Mutation must continue to use the standalone
  parser (`dummyindex/context/domains/preflight/inventory.py:162-166`).
- The managed body depends on `.context/HOW_TO_USE.md` remaining the detailed
  navigation authority. Tests cap the body at ten lines and require exactly one
  shared policy occurrence (`tests/context/output/test_bootstrap.py:200-212`).

## Data model

- `ALWAYS_ON_OUTPUT_POLICY` is immutable project guidance shared across host
  project blocks; it is not config or runtime state
  (`dummyindex/context/output/bootstrap.py:26-40`).
- `BEGIN_MARKER`/`END_MARKER` identify Claude's owned region. Codex supplies a
  separate marker pair to the same engine, preventing cross-host ownership
  collisions (`dummyindex/context/output/bootstrap.py:14-18`,
  `dummyindex/context/output/agents_md.py:24-28`).
- `_MarkerLine` carries a standalone line's start/content-end/line-end offsets;
  `_ManagedBlockSpan` carries replacement and removal boundaries
  (`dummyindex/context/output/bootstrap.py:238-257`).
- `ClaudeMdAction` distinguishes create/consolidate/update/noop;
  `ClaudeMdReconcileResult` retains paths, a printable message, and non-fatal
  warning tuples (`dummyindex/context/output/claude_md.py:33-72`).
- Existing file content remains an opaque UTF-8 string. BOM and exact newline
  sequences are preserved outside the owned region
  (`dummyindex/context/output/bootstrap.py:215-226`,
  `dummyindex/context/output/bootstrap.py:418-425`).

## Key decisions

- **Project response behavior is shared, host wrapper prose is not.** Claude and
  Codex project blocks consume one caveman/i-have-adhd policy, while host-specific
  navigation, ownership, and global guidance remain in their host modules
  (`dummyindex/context/output/bootstrap.py:26-40`,
  `dummyindex/context/output/agents_md.py:33-65`).
- **Marker identity is stable; body text is replaceable.** A policy or navigation
  update converges through the existing region without parsing the old body
  (`dummyindex/context/output/bootstrap.py:97-129`).
- **Only complete marker lines own bytes.** Quoted markers are user content; this
  closes the destructive ambiguity of substring-based replacement
  (`dummyindex/context/output/bootstrap.py:260-306`,
  `dummyindex/context/output/bootstrap.py:373-393`).
- **Ambiguity policy follows the operation.** Direct editing refuses duplicate
  regions because ownership is unclear; migration repairs sequential complete
  duplicates because its explicit purpose is consolidation
  (`dummyindex/context/output/bootstrap.py:276-370`).
- **Both-host preflight prevents knowable partial writes.** It cannot make two
  filesystem writes transactional, but it rejects every deterministic conflict
  before the first write (`dummyindex/cli/bootstrap.py:41-52`).
- **Filesystem structure is user state.** Symlink identity, existing target mode,
  process umask for new files, BOM, newline style, and unrelated bytes are part of
  the preservation contract (`dummyindex/context/output/bootstrap.py:193-226`,
  `dummyindex/context/output/bootstrap.py:396-442`).
- **Migration prioritizes recoverability over strict direct-edit failure.** Expected
  marker/filesystem errors become `NOOP` plus warnings; canonical is written before
  root is removed; inode-shared layouts are refreshed without deletion
  (`dummyindex/context/output/claude_md.py:96-133`,
  `dummyindex/context/output/claude_md.py:135-269`,
  `dummyindex/context/output/claude_md.py:282-336`).
- **Detailed instructions remain out of the host block.** The body is a short
  stable pointer and policy carrier; `.context/HOW_TO_USE.md` owns navigation
  depth (`tests/context/output/test_bootstrap.py:200-212`).

## Open questions

- Should direct bootstrap skip `_atomic_write` when the assembled bytes already
  match? Content is idempotent, but the current successful no-op path still
  replaces the target and can alter inode-level metadata.
- Should the renderer return a structured create/append/replace/prepend/noop
  action instead of only final text? The CLI currently prints the same success
  line for every direct-render outcome.
- Should `context bootstrap --platform both` implement rollback for a race after
  successful preflight? Preflight eliminates knowable partial writes, not
  cross-file transactional failure.
- Should the read-only inventory sentinel adopt `_managed_block_span` so status
  distinguishes a valid managed block from an inline quotation or malformed
  marker layout?
- Should `_V0_BLOCK_BODY` be renamed to reflect its current durable policy and
  lifecycle contract? Marker-keyed updates make the name behaviorally inert, but
  it understates the body's role.
