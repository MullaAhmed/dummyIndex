# Architect notes — bootstrap (stage 2)

## What I changed

- Defined the renderer boundary as one managed region plus safe text/filesystem
  update. Root resolution, Codex ownership/budget, and legacy layout repair are
  explicit consumers, not renderer responsibilities.
- Separated host-neutral engine inputs (`block_body`, marker pair, placement) from
  Claude's default body and Codex's host-specific wrapper policy.
- Added the full update pipeline from deterministic policy rendering through
  standalone-marker validation, pure text assembly, and atomic replacement.
- Made direct editing and legacy repair separate modes: one rejects duplicate
  regions; the other accepts only sequential balanced duplicates so it can
  consolidate old layouts safely.
- Replaced generic idempotency claims with byte, marker, inode, symlink, mode,
  BOM, newline, and write-then-delete contracts backed by current source.
- Removed stale substring-marker/fixed-temp architecture inherited from the old
  plan and corrected every cited symbol/range against the live map and source.

## Patterns named

- **Policy single source** — one caveman/i-have-adhd project policy is consumed
  by Claude and Codex project bodies
  (`dummyindex/context/output/bootstrap.py:26-40`,
  `dummyindex/context/output/agents_md.py:17-52`).
- **Parameterized managed-region engine** — body, markers, and placement are
  injected strategies (`dummyindex/context/output/bootstrap.py:82-132`).
- **Standalone-marker control plane** — exact line offsets distinguish owned
  syntax from quoted prose (`dummyindex/context/output/bootstrap.py:238-306`,
  `dummyindex/context/output/bootstrap.py:373-393`).
- **Strict editor / tolerant repair split** — single-span direct update versus
  sequential multi-span legacy repair
  (`dummyindex/context/output/bootstrap.py:260-370`).
- **Pure assembly before side effect** — append/prepend/replace compute complete
  output before one writer call (`dummyindex/context/output/bootstrap.py:114-235`).
- **Filesystem-aware atomic replace** — exclusive unique temp, symlink-target
  preservation, mode restoration, and cleanup
  (`dummyindex/context/output/bootstrap.py:396-442`).
- **Write-then-delete migration** — canonical is safe before root removal
  (`dummyindex/context/output/claude_md.py:207-269`).
- **Exact-segment idempotence** — failed-delete retries do not duplicate residue
  or authorize deletion from loose substring matches
  (`dummyindex/context/output/claude_md.py:190-219`).

## Dependencies surfaced

- `cli/bootstrap.py` owns project resolution, platform selection, preflight,
  exit codes, and printing (`dummyindex/cli/bootstrap.py:10-71`).
- `agents_md.py` owns Codex markers, target precedence, ownership, byte budget,
  and host wrapper prose; it consumes the shared engine and project policy
  (`dummyindex/context/output/agents_md.py:17-65`,
  `dummyindex/context/output/agents_md.py:110-180`).
- `claude_md.py` consumes Claude markers/body and the multi-span parser, adding
  inode-aware merge and structured degradation
  (`dummyindex/context/output/claude_md.py:22-30`,
  `dummyindex/context/output/claude_md.py:96-336`).
- Build, install, and legacy migration call `reconcile_claude_md`, not the direct
  block editor, when whole-layout convergence is required
  (`dummyindex/context/build/runner.py:280-288`,
  `dummyindex/installer/install.py:404-409`,
  `dummyindex/cli/migrate.py:74-89`).
- `context/__init__.py` publicly re-exports Claude markers and direct renderer;
  marker identity is therefore compatibility surface
  (`dummyindex/context/__init__.py:48-54`,
  `dummyindex/context/__init__.py:76-105`).
- Preflight inventory's substring probe is a coarse read-only sentinel and must
  not be reused for mutation (`dummyindex/context/domains/preflight/inventory.py:162-166`).

## Decisions promoted

- Share response behavior, not entire host blocks.
- Keep marker identity stable and body text replaceable.
- Recognize ownership only through complete marker lines.
- Select ambiguity policy by operation: strict editor, repair-capable migration.
- Preflight every deterministic both-host conflict before the first write.
- Treat filesystem structure and exact surrounding text as user state.
- Favor recoverability in migration through structured warnings,
  write-then-delete ordering, exact dedupe, and inode safety.
- Keep detailed navigation in `.context/HOW_TO_USE.md`; host guidance remains a
  terse pointer and policy carrier.
