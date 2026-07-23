# Bootstrap renderer — plan

confidence: INFERRED

## Where it lives

`dummyindex/context/output/bootstrap.py` owns the shared managed-block primitive:
Claude's deterministic body, the caveman/i-have-adhd policy, marker parsing,
append/replace/remove behavior, path containment, exact text I/O, and atomic
replacement. `dummyindex/cli/bootstrap.py` owns host selection, root resolution,
cross-host preflight, output, and exit codes. `dummyindex/context/output/claude_md.py`
owns the higher-level root-to-canonical Claude layout migration, while
`tests/context/output/test_bootstrap.py`, `test_claude_md.py`, and
`test_claude_md_build.py` lock the unit and real-path contracts.

## Architecture in three sentences

The CLI resolves the selected project guidance targets and, for a both-host run,
preflights every deterministic conflict before invoking either writer. The
renderer builds one marker-wrapped deterministic body and creates, appends,
replaces, prepends, or removes that region while preserving every unrelated byte
and filesystem property it promises to preserve. The Claude layout reconciler
uses the same marker grammar and fresh body to fold legacy root guidance into one
canonical file through write-then-delete ordering.

## Data model

- `ALWAYS_ON_OUTPUT_POLICY` is immutable shared prose, not user state. Claude's
  `_V0_BLOCK_BODY` interpolates it once, and Codex's project block imports the
  same constant (`dummyindex/context/output/bootstrap.py:26-40`,
  `dummyindex/context/output/agents_md.py:17-52`).
- `BEGIN_MARKER` and `END_MARKER` delimit the owned region. Marker identity is
  stable API; body revisions do not need a migration ladder because replacement
  is marker-keyed (`dummyindex/context/output/bootstrap.py:14-18`,
  `dummyindex/context/output/bootstrap.py:97-129`).
- `_MarkerLine(start, content_end, line_end)` and
  `_ManagedBlockSpan(start, content_end, remove_end)` are compact internal offset
  records. `_managed_block_span` enforces zero-or-one direct-render blocks;
  `_managed_block_spans` permits sequential complete duplicates so legacy
  reconciliation can repair them (`dummyindex/context/output/bootstrap.py:238-370`).
- `ClaudeMdAction` is the closed result alphabet: `created`, `consolidated`,
  `updated`, or `noop`. `ClaudeMdReconcileResult` carries that action, both paths,
  a printable message, and warning tuples
  (`dummyindex/context/output/claude_md.py:33-72`).
- User content is deliberately opaque. The renderer does not parse Markdown; it
  recognizes only standalone control-marker lines and otherwise preserves exact
  text, including BOM and newline style
  (`dummyindex/context/output/bootstrap.py:215-226`,
  `dummyindex/context/output/bootstrap.py:260-306`,
  `dummyindex/context/output/bootstrap.py:418-425`).

## Key decisions

- Keep the output behavior policy in one constant. Claude and Codex project
  guidance cannot drift on the caveman/i-have-adhd rules, and explicit user and
  safety requirements remain the stated override
  (`dummyindex/context/output/bootstrap.py:26-40`,
  `dummyindex/context/output/agents_md.py:33-52`).
- Treat markers as control syntax only on complete lines. This prevents quoted
  examples and diagnostics from becoming destructive splice anchors while still
  allowing surrounding indentation (`dummyindex/context/output/bootstrap.py:260-306`,
  `dummyindex/context/output/bootstrap.py:373-393`).
- Fail before write on ambiguous direct-render layouts. Duplicate, dangling, and
  reversed markers require manual resolution; legacy consolidation alone may
  collapse multiple sequential balanced blocks
  (`dummyindex/context/output/bootstrap.py:276-306`,
  `dummyindex/context/output/bootstrap.py:309-370`).
- Preserve the host's placement needs through one renderer. Claude keeps its
  historical append/in-place behavior; Codex uses `place_first=True` so the
  managed block remains within its instruction-byte budget
  (`dummyindex/context/output/bootstrap.py:82-132`).
- Preflight both hosts as one operation. Marker, path, ownership, and budget
  failures that are knowable before writing must not leave a deterministic
  half-applied both-host bootstrap (`dummyindex/cli/bootstrap.py:41-52`).
- Make writes collision-resistant and filesystem-aware. Unique exclusive temp
  creation avoids clobbering a user-owned fixed `.tmp`; symlink targets and file
  modes survive replacement, and a new file follows process umask
  (`dummyindex/context/output/bootstrap.py:396-442`).
- Make consolidation write-then-delete and exact-deduping. Root user content is
  not removed until canonical is safe, and a failed-delete rerun cannot duplicate
  an already-folded exact residue (`dummyindex/context/output/claude_md.py:190-231`,
  `dummyindex/context/output/claude_md.py:244-269`).
- Keep the managed body terse and route detail into `.context/HOW_TO_USE.md`.
  Tests cap it at ten lines and require exactly one shared output-policy string
  (`tests/context/output/test_bootstrap.py:200-212`).

## Open questions

- Should `bootstrap_claude_md` skip the atomic replace when generated bytes are
  already identical? Content is idempotent today, but a no-op call still performs
  a replacement and can change inode metadata observable by external tools.
- Should the CLI expose `--check`, `--dry-run`, or a structured action result so
  users can distinguish create, append, refresh, and byte-identical runs before
  or after mutation? It currently prints the same “managed block written” message
  for each success path.
- Should cross-host bootstrap gain rollback for filesystem races after successful
  preflight? Current preflight eliminates deterministic partial writes but cannot
  make two independent files transactionally atomic.
- Is `_V0_BLOCK_BODY` still the right name now that the body has accumulated
  explicit rebuild/reconcile/GC and response-policy contracts? Marker-keyed
  replacement makes a version rename unnecessary for behavior, but the name
  understates the live contract.
