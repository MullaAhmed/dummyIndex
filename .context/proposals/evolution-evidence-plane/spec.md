# Spec — Evolution evidence plane: bounded Stop-hook observation, two-stage correction detection, load-time exposure log, keyed local ledger, hostile-transcript filters

## Intent

Ordinary chats evolve nothing today. The Stop hook only nudges a handoff.
A seven-word regex hit enqueues learning directly (`evidence.scan_hosts`).
No log records which session loaded which artifact version.
The committed ledger stores bare SHA-256 of session IDs and correction text.

This proposal builds the evidence plane: facts only, local, keyed, hostile-input aware.
It decides nothing. `evolution-probation-lifecycle` consumes its data and owns every decision.
Users: maintainers running dummyindex in Claude Code; Codex evidence arrives through `evolve evidence`.

Out of scope: lifecycle states, thresholds, CLI verbs, skill text, config schema, Codex exposure.

## Contracts

### C1. Stop hook observes only
- `dummyindex/context/hooks.py` `_STOP_HOOK` gains one entry: `{"type": "command", "async": true, "command": _MANAGED_COMMENT + _SILENT_GATE + 'dummyindex context evolve evidence --root "$CLAUDE_PROJECT_DIR" >/dev/null 2>&1 || true\nexit 0\n'}`.
- `async: true` runs it in the background; it cannot block the turn. Stop stdout stays muted; it is protocol for the reconcile gate.
- Claude ignores `timeout` on async hooks. No `timeout` key. The hard bound is `budget_s` (C2).
- The run writes only `.context/cache/evolution/**` and `.context/cache/evidence-sources.json`. It never writes a curated file.
- The hook never prompts, never reflects, never enqueues learning.

### C2. Bounded incremental import
- `scan_hosts(context_dir, ..., budget_s=20.0, clock=time.monotonic, now=None)`.
- It takes the non-blocking `observe.lock` before any parse. Contention returns `{"skipped": "locked"}` with no write.
- `evolve_promotion.project_lock` allowlist gains `observe.lock`. Curated and learning writes keep `evolve.lock`.
- Once `clock()` passes the budget, it stops before the next file. It saves cursors for every finished file. Result gains `complete: bool`.
- Fast path: skip a file when `st_size` and `st_mtime_ns` equal its cursor. No open.
- Kill switch: env `DUMMYINDEX_EVOLUTION` in `{"0","off","false"}`, or an unusable key (C4), returns `{"disabled": true}` and writes nothing.

### C3. Storage split
| Data | Path | Committed |
|---|---|---|
| cursors, corrections, attributions, session→source map | `.context/cache/evolution/ledger.json` | no |
| exposure rows (append-only) | `.context/cache/evolution/exposure.jsonl` | no |
| held-out lineage (`expose_case`) | `.context/gc/evidence.json`, `schema_version: 2`, key `exposure` only | yes |
| per-correction stub (only on request) | `.context/gc/evidence/<keyed-id>.json` | yes |
| HMAC key | `~/.dummyindex/evidence.key` | never |
- `.context/cache/` is already gitignored. No new gitignore pattern, no new committed path.
- Every ledger and exposure write runs under `observe.lock`. On contention the writer skips; the next Stop retries.
- Migration: a schema-1 `gc/evidence.json` moves `events` and `cursors` into the local ledger first. Then the committed file is rewritten as schema 2. A crash between the two steps repeats safely: event IDs dedupe.
- `read_ledger()` keeps its shape `{schema_version, events, cursors, exposure}`. `events` and `cursors` come from the local ledger; `events[*]` keeps `id, host, kind, origin, timestamp`. `evolve.harvest` needs no edit.
- Legacy `gc/evidence/<id>.json` files and git history are not rewritten. They back existing learning events.
- Save prunes local rows whose `day` < `now.date() - retention_days()`.

### C4. Keyed identifiers
- `keyed_id(*parts, key=None) -> str`: hex HMAC-SHA256 over canonical JSON of `parts`. Default key: `evidence_key()`.
- `evidence_key(home=None)`: 32 random bytes at `~/.dummyindex/evidence.key`, exclusive create, re-read on `FileExistsError`. `chmod 0o600` on POSIX; Windows relies on home-directory ACLs.
- An unreadable or uncreatable key disables evolution for that call (C2).
- New writes never hold a bare SHA-256 of a session ID or human text, committed or local.
- Stub schema: `{"schema_version": 2, "id", "host", "kind": "human_correction", "day", "detector"}`. No text hash, session or turn.

### C5. Human-text provenance (stage 1 capture)
- Claude rows count as human text only via `memory/miner/scan._human_prompt_text`, imported by its private name. It requires `userType == "external"` and text blocks only.
- `_INJECTED` prefixes gain `<system-reminder>`, `<command-`, `<local-command-`. Rows with `<!-- dummyindex:learning -->` stay excluded.
- Code fences and `>` lines are stripped before matching (existing).
- `_CORRECTION` stays a liberal prefilter. A hit creates one OBSERVED correction and decides nothing.
- `scan_hosts` no longer calls `enqueue_learning` or writes `gc/evidence/<id>.json`. Result key `learning` stays, always `null`.
- Import direction: `evidence` imports `observe`; `observe` never imports `evidence`. Codex rows stay in `evidence._event`/`_jsonl`/`_database`.

### C6. Exposure log (Claude only)
- Derived at import from assistant `tool_use` blocks:
  - `Read` of a file under `.context/conventions/`, `.context/features/`, `.context/playbooks/`, `.context/equipment/`, or any `**/skills/**/SKILL.md` in the repo gives `item` = repo-relative POSIX path.
  - `Skill` with `input.skill` gives `item` = `skill:<name>`.
  - Other paths are ignored.
- Paths are resolved, and on Windows case-folded, before `relative_to(root)`. Backslash and drive-letter variants match.
- Row: `{item, version, rules, session, turn, day, via, call, model, cli, detector}`.
  - `version`: sha256 of the file bytes at import; `null` when unreadable.
  - `rules`: managed rule IDs via `living_rules.rules_in`; `[]` on error.
  - `turn`: human-typed turns seen in that transcript before the call.
  - `via`: `read` | `skill` | `inject`. `call`: keyed tool-use ID; duplicates (forks, rescans) are dropped.
  - `model`: assistant `message.model`; `cli`: `config.current_dummyindex_version()`; `detector`: `DETECTOR_VERSION` (1).
- `record_exposure(context_dir, *, session_id, turn, items: list[tuple[str, str | None]], via="inject")` logs loader injections. `session_id` is raw and keyed inside. Injected rows carry `model: null`, `rules: []`.

### C7. Hostile-transcript filter
- `scan_text(text) -> tuple[str, ...]` returns reasons:
  - `invisible-unicode`: U+200B–U+200F, U+202A–U+202E, U+2060–U+2064, U+2066–U+2069, U+FEFF, U+E0000–U+E007F.
  - `injection-marker`: case-insensitive `ignore (all |any )?(previous|prior|above) instructions`, `</?(system|instructions?)>`, `<\|im_(start|end)\|>`, `<!-- dummyindex:`.
- Applied to the human turn and to tool-result text since the previous human turn. The buffer is capped at 64 KB and resets at each human turn.
- Any reason sets `quarantine`. Quarantined corrections never appear in a resolution packet.

### C8. Correction record
`{id, host, session, turn, day, source_id, byte_offset, model, cli, detector, candidates, quarantine, status}`
- `id`: `keyed_id(host, native row uuid)`; fallback `keyed_id(host, timestamp, text)`. Forked copies collapse.
- `candidates`: distinct exposure `item`s in the same session with `turn` < correction `turn`. Injected rows use turn 0.
- `status`: `open` | `resolved` | `expired` (local transcript gone).
- Codex corrections have `candidates: []`. They are captured, never attributable.

### C9. Stage-2 interface (the resolver is the host LLM; lifecycle owns its CLI)
- `resolution_packet(context_dir) -> dict | None`: oldest `open`, unquarantined correction with ≥1 candidate.
  - Shape: `{correction, human_text, assistant_text, candidates: [{item, version, rules}], verdicts: ["attributed","unrelated","unknown"]}`.
  - `human_text` and the preceding `assistant_text` come from the local raw transcript, each truncated to 1,000 chars. They are never written to disk.
  - A missing transcript marks the correction `expired` and moves to the next one.
- `record_attribution(context_dir, correction_id, *, verdict, item=None, durable=False, retracts=False, now=None) -> dict`:
  - `attributed` requires `item` equal to a candidate path, or `<candidate path>#<rule id in that row's rules>`.
  - `retracts` requires `attributed`. Other verdicts reject `item`.
  - Appends `{correction, verdict, item, durable, retracts, session, turn, day}`; sets the correction `resolved`. A second record raises.
- Reads: `open_corrections`, `corrections`, `attributions`, `exposures(context_dir, item=None)`, `session_tool_calls(context_dir, session) -> list[tuple[int, str]] | None`. `session` values are keyed IDs.
  - `session_tool_calls` re-reads the local transcript and returns `(turn, canonical_signature)` via `memory/miner/signatures.canonical_signature`. `None` when the transcript is gone.
- `commit_evidence_stub(context_dir, correction_id) -> str` writes the C4 stub and returns its repo-relative path. `living_rules.durable_evidence` accepts it.
- `retention_days(home=None) -> int`: `min(30, cleanupPeriodDays)` from `~/.claude/settings.json` when it holds a positive int; else 30. Plain file read; no `cli/` import.
- `evolution_enabled() -> bool`: the C2 checks.
- All names export from `dummyindex.context.domains.observe`.

## Decisions
1. The hook reuses `evolve evidence`. No new CLI verb here; lifecycle owns every CLI surface.
2. Background = Claude `async: true` plus in-process `budget_s` (20 s) plus a non-blocking lock taken first. No `timeout` key, no detached shell.
3. Each Stop sweeps this project's transcript directory with a stat-only fast path. Accepted; no debounce.
4. No once-per-session flag here. Lifecycle's digest is once per session.
5. Kill switch is env only. Teams set it in Claude `settings.json` `env`. No config schema v6.
6. Exposure comes from transcript tool calls only. No logging hook, no cite-the-ID protocol. Version is read at import; a one-turn lag is accepted.
7. Codex exposure, Codex instruction pointers and an LLM followed-judge are cut.
8. One HMAC key, no rotation. A lost key re-keys future rows; old local rows age out.
9. Held-out lineage keys stay as-is. They are case IDs and fixture hashes, not chat text.
10. Legacy committed per-event files and git history are not scrubbed. The keyed guarantee covers new writes.
11. Experiment and native snapshots already exclude `gc/evidence.json` but not `gc/evidence/`. That gap predates this work and stays out of scope.
12. Between this landing and lifecycle, human-correction learning pauses. Closeout learning is unaffected.
13. Code carries no long comments: one-line docstrings at most.

## Related proposals
- `self-improvement-loop`: shipped (16/16 ticked) as the `evolution` feature. Reused, not superseded. Its `planned` status is stale.
- `meta-harness-alignment`: orthogonal (equip-eval stays a reporter). Not superseded; "proxy, not prize" is honored.
- `evolution-probation-lifecycle`: depends on C6–C9.

## Acceptance
- [ ] `tests/context/test_hooks.py`: the managed Stop entry has one `evolve evidence` hook with `async: true`, no `timeout`, streams sent to `/dev/null`; `async` survives the settings JSON round trip.
- [ ] `tests/context/test_hooks.py`: a second install reports `claude/Stop` skipped; an old managed Stop is refreshed with the new hook; a user hook in the managed entry survives; uninstall removes the new hook.
- [ ] `tests/context/domains/test_evidence.py`: fixture rows carry `userType: "external"`; a human correction is counted in the local ledger; `.context/gc/evidence/` and `.context/gc/learning/` stay empty on a fresh fixture.
- [ ] `tests/context/domains/test_evidence.py`: no file under `.context/gc/` contains the sha256 of the raw session ID or of the correction text.
- [ ] `tests/context/domains/test_evidence.py`: a schema-1 fixture migrates; committed file is schema 2 with `exposure` kept; `read_ledger()` still lists events and cursors; a second import adds no duplicates.
- [ ] `tests/context/domains/test_evidence.py`: a fake clock expiring after 1 of 3 files returns `complete: false` with 1 cursor saved; a rerun completes.
- [ ] `tests/context/domains/test_evidence.py`: an unchanged size and mtime opens nothing (counted via monkeypatched open); an mtime-only touch re-reads.
- [ ] `tests/context/domains/test_evidence.py`: a held `observe.lock` returns `skipped: locked` with no write; `DUMMYINDEX_EVOLUTION=off` writes nothing.
- [ ] `tests/context/domains/test_evidence.py`: existing lineage tests pass unchanged.
- [ ] `tests/context/domains/test_observe_units.py`: `keyed_id` differs for two keys; the key file is created once and re-read on `FileExistsError`; mode 0600 on POSIX (skipped on win32).
- [ ] `tests/context/domains/test_observe_units.py`: every C7 range endpoint and pattern quarantines; clean text does not; `retention_days` uses `cleanupPeriodDays` when valid, else 30.
- [ ] `tests/context/domains/test_observe_import.py`: `<system-reminder>`, `isMeta`, `userType: "internal"` and tool-result-only rows never become corrections.
- [ ] `tests/context/domains/test_observe_import.py`: a tool result with U+200B before a correction quarantines it; the buffer resets at the next human turn.
- [ ] `tests/context/domains/test_observe_import.py`: `Read` of `.context/conventions/x.md` at turn 1 then a correction at turn 2 gives that candidate; the row carries version, rules, model, cli and detector.
- [ ] `tests/context/domains/test_observe_import.py`: `Skill` gives `skill:<name>`; a `Read` of `.context/cache/x` or a non-skill file is ignored; a backslash, mixed-case drive path matches on win32.
- [ ] `tests/context/domains/test_observe_import.py`: turn counts continue across two incremental imports; a forked copy adds no duplicate correction or exposure.
- [ ] `tests/context/domains/test_observe_attribution.py`: packets come oldest first, skip quarantined and zero-candidate rows, truncate text to 1,000 chars, and expire a correction whose transcript is gone.
- [ ] `tests/context/domains/test_observe_attribution.py`: `record_attribution` rejects off-candidate items, bare `retracts` and a second record; accepts `path#rule` only for a rule in that row.
- [ ] `tests/context/domains/test_observe_attribution.py`: `record_exposure` writes no raw session ID to disk; `session_tool_calls` returns `None` after the transcript is deleted.
- [ ] `tests/context/domains/test_observe_attribution.py`: `commit_evidence_stub` output passes `durable_evidence` and holds only the C4 keys.
- [ ] `tests/context/domains/test_evolve.py`, `test_evolve_learning.py` and `tests/cli/test_evolve_cli.py` pass unchanged.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `equip`
- `evolution`
- `session-memory`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
