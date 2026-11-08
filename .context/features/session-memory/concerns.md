## Data integrity

- **[HIGH]** `memory/roll.py:84-98`: the roll writes `now.md` without `now_down` before `recent.md` gains it, and does the same from recent to archive. A failed Windows `replace` (6 retries, `atomic_io.py:55-67`) or a crash between writes loses those sections. Fix: write archive → recent → now, and have a re-run skip sections already present.
- **[HIGH]** `memory/transcript.py:101-119,130-154`: strict UTF-8 decoding with only `except OSError`. A tail cut mid-multibyte raises `UnicodeDecodeError` (reproduced), which disables gate, nudge and breadcrumb. Every call re-parses all files (73 subagent files, 113 MB this session). Fix: `errors="replace"`, the `"type":` prefilter (`miner/scan.py:104-121`), and a per-file cache keyed on `(path, st_size, st_mtime_ns)`.
- `memory/breadcrumb.py:49-50`: any top `(auto-breadcrumb)` section is replaced, whatever its day or session, and no hook rolls. The 19:24Z compaction erased the 19:22Z one. Fix: replace only on same date and same session id, else prepend (conflict 4).
- `breadcrumb.py:46-54`, `roll.py:64-98`, `nudge.py:60-67`, `reconcile_gate.py:230-244`, `store.py:25-29`: unlocked read-modify-writes lose updates across profiles. `_replace_bytes` (`atomic_io.py:37-67`) also never fsyncs and leaves files at 0600. Fix: one memory-local writer with an `O_EXCL` lock (`fleetrun._acquire_lock`), fsync, and the original mode kept.
- `memory/parse.py:21,35-48,52-55` + `roll.py:39-41,76-78`: a date like `2026-02-30` makes `_ordinal` raise before any write, so every later roll fails. Also, `## ` inside a code fence splits a section, and the round-trip reflows sections it did not move. Fix: check dates with `date.fromisoformat`, track fence state, and preserve or document whitespace.
- `memory/nudge.py:38-46,62-66` + `reconcile_gate.py:209-217,237-243`: the memos have no shape check and no `schema_version`. Past 100 sessions, one non-dict value raises in the `kv[1].get` prune on every mark, and the `nudge` CLI has no catch (`cli/memory.py:124-136`). Fix: drop bad entries on load (as `feedback.py:136-200` does) and add `schema_version: 1`.

## Security

- **[HIGH]** `miner/scan.py:206-209` + `corrections.py:44-51` + `feedback.py:25-37`: rows with no `origin` (161 here: `<command-name>`, `<local-command-stdout>`, `<ci-monitor-event>`, `<bash-stdout>`…) pass as human. Two `! git log` outputs saying `You must use the X skill.` mint a hidden standing directive for every prompt. Fix: treat a missing `origin` as non-human (version-gated), reject leading harness tags, and add a max-age window.
- **[HIGH]** `memory/emit.py:36-42` + `parse.py:16-18`: tiers are read through symlinks, in full, and injected as `=== MEMORY ===`. A global hook does this in any clone (`dummyindex/context/hooks.py:238-242`), so `core-memories.md -> ~/.aws/credentials` lands in context. Writes follow a symlinked parent (`atomic_io.py:43-52`). Fix: refuse `is_link` on `.context`, `session-memory` and `cache`; assert containment; cap `st_size`; add a provenance header.
- `cli/memory.py:20-50` + `reconcile_gate.py:339-350`: hook stdin is trusted. Piping `{"session_id":"$CLAUDE_CODE_SESSION_ID","transcript_path":"/nonexistent"}` into `reconcile-gate` spends the block-once memo without a diff. Also: stdin is uncapped (`:27`), a `*` session id globs any project (`transcript.py:66-67`), and a FIFO stalls until the host's hook timeout. Fix: allow `transcript_path` only as a regular file under `<config>/projects/`, require `session_id` to match `^[0-9a-f-]{1,64}$`, cap stdin at 1 MiB.
- `miner/signatures.py:47-70` + `scope.py:43-73` + `render.py:28-72`: the failure-pattern report would commit tool inputs verbatim (`.env` content, bearer headers), and only paths are redacted. It is safe only while unwired. Fix: render `tool_name` + `sha256(signature)[:12]` before wiring it, and narrow plan decision 4.

## Product surface

- **[HIGH]** `context/reconcile_gate.py:372-377`: the nothing-owned advisory is never memoized. Any subagent edit, `.context/` docs included (`:265-266`), arms it, and the same line hit 60 Stops in `dcba02dd`. The only off switch also disables the block. Fix: a separate advisory memo keyed on the drift signature (conflict 2).
- **[HIGH]** `reconcile_gate.py:329-336` vs `:352-358`: `compute_drift` (2.06 s in-process) runs before the cheap significance and ownership checks, so `reconcile-gate` costs 3.50 s and `nudge` 0.75 s on every Stop. Fix: check the transcript signal first, once its per-file cache exists (conflict 3).
- `dummyindex/context/hooks.py:78-221` + `emit.py:46-60`: no hook runs `roll`. A 139-day-old `2026-06-22` handoff is emitted as current, and the tail cut drops `core-memories.md` first. On Codex the store is write-only (`output/agents_md.py:34-56`). Fix: roll at SessionStart after the roll HIGH lands, reserve a core budget, and point AGENTS at the store.
- `context/drift.py:310-317` + `:170-187`: the SessionStart drift list is uncapped (11,192 chars). "Drift clears naturally" is false for basis-covered pairs, which clear only via stamp or ack. `drift-ack` without `--path` bulk-acks a whole feature (`cli/drift_ack.py:100-110`). Fix: cap per feature, fix the hint, add a dry run for bulk acks.
- `breadcrumb.py:76-106` + `nudge.py:26-30,70-79,118-127`: the breadcrumb describes the whole working tree, not the session's `edited_paths`. The nudge fires once, minutes in, and the day-scoped "saved" check lets one session mute concurrent ones. Fix: use `edited_paths` and key on the session.
- `cli/memory.py:81-88` + `dummyindex/cli/status.py:54,326` + `miner/scope.py:28-40` + `feedback.py:209-225`: skill feedback is opaque and sticky. Errors are swallowed and there is no show or clear verb. Worktree slugs never match (`--claude-` vs `-.claude-`). `normal mode` lasts one turn. `docs/COMMANDS.md:225-226` promises a failure-pattern command that does not exist. Fix: add `memory feedback --show/--clear`, a status line, and one slug encoder.

## Cross-review notes

- Confirmed HIGH with fresh evidence: decode repro; 73 files / 113 MB; no-origin counts 56/44/37/8/6/5/5 (match the security critic); advisory 60× (was 52); drift 2.06 s in-process.
- Refuted or corrected:
  - Half-written lines break only when cut mid-multibyte; ASCII-boundary partial lines are skipped (`transcript.py:136-139`). The re-read is not the main Stop cost (0.51 s vs 2.06 s for drift).
  - Prior claims dropped: "bad date moves down first" (it raises before any write); "`origin` absent on all 220 rows" (the host now stamps 610 rows `human`); "foreign benchmarks / polluted backbone" (removed at HEAD in `404654a`; 5,814 first-party symbols).
  - "Pattern 1 unanchored" (security critique) actually refers to the requirement pattern `:44-51`.
- Merged:
  - Drift-engine reconcile bullets → Product 4; advisory memo → Product 1; emit core cut → Product 3.
  - Breadcrumb overwrite → Data integrity 3; lock, fsync and mode → Data integrity 4.
  - Read- and write-side containment → Security 2; same-turn exemption (`feedback.py:226-230`) → Security 1.
- Conflicts between fixes:
  1. Durable per-slug counts (database critique) let a planted promotion outlive host retention, today its only decay. Filter on origin first, then add `last_seen` with a dummyindex-side max-age.
  2. Memoizing the advisory via `mark_blocked` masks a later real block (`reconcile_gate.py:323-324`).
  3. Moving the significance check before drift needs the transcript cache first, or the 113 MB parse runs every Stop.
  4. Prepending breadcrumbs or hooking `roll` grows exposure: core is cut sooner and the delete-first roll runs every session. Land the roll fix and core budget first.
  5. Requiring `session_id` == `CLAUDE_CODE_SESSION_ID` assumes that variable is set inside hooks (unverified). If it is unset, the memo never matches and the gate blocks every turn.
  6. Keep the lock, fsync and containment out of the shared `atomic_io`: 34 modules import it, and `build/upgrade.py:21` uses `_replace_bytes`.
  7. A late or second nudge breaks plan decision 10 ("side effects fire once"). The user must decide.
- Still true from the reconcile: `domains/drift_acks.py` and `cli/drift_ack.py` are absent from `feature.json`.
- Code wins over these docs: the plan.md anchors are stale (`reconcile_gate.py:346-434` → `:307-388`, `atomic_io.py:38-68` → `:37-67`), and decision 4 overclaims for `RepeatedSignature.signature`. Anchors here come from the working tree over `0634bfd` (a comment-only pass is in flight).
