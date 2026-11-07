# Spec — Evolution probation lifecycle: eight reversible states, local overlay, asymmetric promote/demote rules, followed-check, enforcement route, expiry/suspension/caps, yield report, blast-radius tiers

## Intent

Today a passing human-origin reflection auto-applies into a committed convention.
Silence after an edit is read as success. A correct but ignored rule cannot be told from a wrong one.
Nothing expires, nothing reports yield, and every target gets the same bar.

This proposal adds the decision layer over the evidence plane (`evolution-evidence-plane`).
Chat-derived rules live on local probation first. Harm demotes fast; promotion is slow, bounded and human-committed.
Ignored rules route to enforcement, never to rollback. Every `evolve` pass reports its yield, including zero.
Users: maintainers who chat in Claude Code. Teammates see only promoted rules a human committed.

Out of scope: evidence import, exposure capture, hashing, hooks (evidence plane); config schema; Codex loading.

## Interface consumed (from `dummyindex.context.domains.observe`)
`open_corrections`, `corrections`, `attributions`, `exposures`, `session_tool_calls`, `resolution_packet`, `record_attribution`, `record_exposure`, `commit_evidence_stub`, `scan_text`, `keyed_id`, `retention_days`, `evolution_enabled`.
Fields follow that proposal's C6, C8 and C9. `session` values are keyed IDs. This package never reads ledger files directly.

## Contracts

### L1. States
| State | Where | Loaded | Committed |
|---|---|---|---|
| OBSERVED | evidence-plane correction, `status: open` | no | no |
| PROPOSED | `.context/gc/learning/<hash>.json`, event ID `chat:<correction>` | no | event file (templated cue, no chat text) |
| PROBATION | `.context/cache/evolution/probation/<id>.json` | author's sessions, marked provisional | no |
| PROMOTED | managed rule block in `.context/conventions/*.md`; item file keeps the record | everyone | yes, by the user's commit |
| SUSPENDED | item file; a bound source hash changed | no | unchanged |
| DEMOTED | item file history; block removed if it was promoted | no | removal via the user's commit |
| EXPIRED | item file history | no | no |
| QUARANTINED | evidence-plane correction with `quarantine`, or an item failing a content scan | no | no |
- Item file: `{schema_version: 1, id, target, body, applies_when, prediction, probe, sources, tests, evidence, origin_session, learning_event, created, state, harm, ignored, contested, needs_enforcement, demote_pending, history}`.
- `id` must match `living_rules` rule-ID syntax before any path is built. `origin_session` and `harm` sessions are keyed IDs.
- `history` is append-only `{ts, from, to, reason}`. Records are never deleted.
- Bookkeeping: `.context/cache/evolution/probation/_state.json` `{consumed, digested (last 50 sessions), last_block_bytes, last_report}`.
- Thresholds live in `probation/constants.py`, each marked `# uncalibrated default`.
- Every function that reads time takes `now: datetime | None`.

### L2. Target tiers (blast radius)
`route(item, items) -> Route` is pure:
| Attributed item | Route | Effect |
|---|---|---|
| `probation:<id>`, or `<convention path>#<id>` of an evolution item | `count` | update that item's counters |
| `.context/conventions/*.md` except `naming.md`, optional `#rule` | `convention` | seed one learning event |
| `.context/features/**` | `reconcile` | digest says run `dummyindex context reconcile` |
| anything else (skills, equipment, playbooks, `naming.md`) | `explicit` | digest says use `/dummyindex-evolve` with a human promote |
- `probation:<id>` comes from injection; `#<id>` comes from a file read of a promoted rule.
- Non-durable, `unrelated` and `unknown` attributions do nothing. Session memory is never a target.
- A session that loaded a live probation item for target T seeds nothing for T.

### L3. Sync
`sync(context_dir, *, now=None, probes=False) -> SyncResult`. No gate, no curated write.
1. Each unconsumed attribution is routed. `convention` calls `enqueue_learning(origin="human", event_id="chat:" + correction, evidence=[commit_evidence_stub(...)], target=path, cue=<fixed template naming the path>)`. `lesson` and `replacement` stay empty.
2. `count`: `retracts` makes PROBATION → DEMOTED at once; PROMOTED gets `demote_pending`. Otherwise L4 gives `followed`:
   - `yes`: append `[session, day]` to `harm`.
   - `no`: `ignored += 1`; at `IGNORED_ROUTE` (2) set `needs_enforcement`. Never demote.
   - `unknown`: `contested += 1`.
   - An item with a probe and `probes=False` leaves the attribution unconsumed for the next CLI sync.
3. Harm: ≥ `HARM_MIN` (2) entries with distinct sessions and distinct days, origin session excluded. PROBATION → DEMOTED; PROMOTED gets `demote_pending`.
4. Drift: a changed `sources` hash gives SUSPENDED; matching hashes again restore PROBATION.
5. Expiry: PROBATION/SUSPENDED with no `probation:<id>` exposure for `retention_days()` since `max(created, last exposure)` → EXPIRED.
6. Writes only `.context/cache/evolution/`, `.context/gc/learning/` and `.context/gc/evidence/`.
- CLI entry points call `sync(probes=True)`. The session-start path calls `sync(probes=False)`, so no learner regex runs at session start.

### L4. Followed-check
- `probe`: `null`, `{"require": <regex>}` or `{"forbid": <regex>}`, regex ≤200 chars, compiled at entry.
- Window: tool calls with first-exposure turn ≤ turn < correction turn, from `session_tool_calls`.
- `require`: followed iff a signature matches. `forbid`: followed iff none matches.
- `probe: null` or a gone transcript gives `unknown`. No LLM judge in v1.

### L5. Entering probation (`evolve_learning`)
- Branch key: `event_id.startswith("chat:")`. Legacy `human:` and closeout/runtime events keep today's path and auto-apply.
- `chat:` runs stage under `.context/cache/evolution/runs/<name>/` through one `_run_dir(event)` helper used by prepare and finish. Gate input capture already skips `.context/cache/`.
- `chat:` prepare rejects (state `evaluated`, verdict `blocked`) a body with `scan_text` reasons, a URL, a code fence or a `$ ` command line. Reason: `high-impact content: use explicit /dummyindex-evolve`.
- `chat:` gate pass calls `probation.enter(...)`; no `promote_files`, no committed `record_event`. The event records `verdict: pass` and `probation: <id>`.
- `enter` refuses (verdict `blocked`, reason `probation cap`) past `MAX_LIVE_PER_TARGET` (1) or `MAX_LIVE_TOTAL` (10) live items. Live = PROBATION or SUSPENDED.
- Reflection JSON gains optional `applies_when` (default: lesson `cue`) and `probe`. A bad or long regex is rejected.

### L6. Session-start block
`session_block(context_dir, session_id, *, now=None) -> str`, printed by `memory session-start` after the memory block. Any error prints nothing.
- Runs `sync(probes=False)`; a sync error still renders from stored items.
- Fixed header: local, provisional, unverified, "exposure is not applicability".
- One line per PROBATION item: `- [probation:<id>] when <applies_when>: <first body line, ≤200 chars>`.
- `needs_enforcement` items add a templated compliance reminder. No transcript text.
- Total ≤ `INDEX_MAX_CHARS` (1,600). Items that do not fit are skipped and not logged as exposed.
- With a `session_id`: `record_exposure(turn=0, items=[("probation:<id>", sha256(body))])` per shown item, plus at most one `Next:` line per session.
- `Next:` priority: `demote_pending`, `evolve attribute --next`, `evolve learning --next`, routed reconcile/explicit, eligible items.
- Without a `session_id` (empty stdin): items only; no exposure, no `Next:`.

### L7. Promotion and demotion (human-run only)
- Eligible: PROBATION; ≥ `PROMOTE_MIN_SESSIONS` (10) distinct exposed sessions over ≥ `PROMOTE_MIN_DAYS` (3) distinct days, origin excluded; `harm` empty; `contested == 0`; drift-free; with a probe, ≥1 exposed session followed and none not followed.
- `promote(context_dir, ids=None, *, now=None, runner=None)`: per eligible item, re-scan content, re-plan with `living_rules.plan_rule` on current target bytes, stage `.context/gc/evolve/probation-<id>/`, `run_gate` with `item.tests`, then `check_receipt`, `promote_files`, and `record_event` `gate` + `promote`.
- `promote` event `outcome`: `{"qualification": "no harm detected", "exposed_sessions": n, "upper_bound_95": 1 - 0.05 ** (1 / n)}`.
- Output: `no harm detected in N exposed sessions; observed-correction bound (detector-limited, 95%): X%`. Never "improved" or "improvement".
- Gate fail or block keeps PROBATION with a history note. A content-scan hit gives QUARANTINED.
- Nothing commits. Output ends with `review and commit .context/conventions/ yourself`.
- `demote(context_dir, id, *, now=None, runner=None)`: local states → DEMOTED. PROMOTED stages the target without its block, gates, applies and records `rollback`. A block already gone just records DEMOTED.
- Pinning is structural: chat-derived writes touch only `plan_rule` managed blocks under a whole-document hash.

### L8. Yield report
`report(context_dir, *, now=None) -> dict` over the last `retention_days()`:
- Counts: observed, quarantined, attributed, proposed, gate passes, promotions, demotions, expiries, suspensions.
- `exposure_rate`: live items with ≥1 exposure in the window ÷ live items; `null` without live items.
- `ignored_rate`: ignored ÷ (ignored + harm entries + contested); `null` when the denominator is 0.
- `resident_bytes`: `last_block_bytes` plus bytes of PROMOTED evolution rule bodies.
- `nothing_new: true` and the line `ran, found nothing` when the counts dict equals `last_report`.
- Lists: routed reconcile/explicit items, `needs_enforcement` items, contested items, eligible items.

### L9. CLI (wire-only `dummyindex/cli/evolve_probation.py`, registered in `cli/evolve.py`)
- `evolve attribute --next [--json]`: `resolution_packet` plus a pointer to `probation-protocol.md`; `nothing to attribute`, exit 0, when empty.
- `evolve attribute --event ID --verdict attributed|unrelated|unknown [--item ITEM] [--durable] [--retracts]`: `record_attribution`, then `sync(probes=True)`. Bad verdict or bare `--retracts` exits 2.
- `evolve probation report [--json]`, `evolve probation promote [--item ID]...`, `evolve probation demote --item ID`. Each runs `sync(probes=True)` first.
- Disabled: prints `evolution disabled (DUMMYINDEX_EVOLUTION)`, exit 0.
- `cli/help.py` evolve block gains the two verbs.

### L10. Skill text
- New `dummyindex/skills/evolve/probation-protocol.md`:
  - Rubric: judge only the human text; name one candidate or answer `unknown`; durable only for standing instructions; `retracts` only for an explicit retraction; author unknown to you.
  - Order: `evolve evidence` until `complete`, `evolve attribute --next` loop, `evolve learning --next`, `evolve probation report`, review eligible items, `evolve probation promote`, the user commits.
- `SKILL.md` gains one pointer line and two CLI reference lines, trimmed to stay within its `tests/data/skill-budget.txt` entry.

## Decisions
1. All new CLI lives under `evolve`; no new `ContextSubcommand`. This proposal owns `cli/evolve.py`, `cli/help.py` and `cli/memory.py`.
2. The overlay rides `memory session-start`. Claude runs SessionStart hooks in parallel, so sync and inject share one process.
3. Closeout, runtime and legacy `human:` learning keep auto-apply. Only `chat:` events go through probation.
4. High-impact targets get no approval queue. Skills, equipment, URLs, commands and scripts stay on explicit `/dummyindex-evolve`, where a human runs `promote`.
5. Feature-doc corrections route to reconcile; no feature-doc probation.
6. No `revalidate` verb. SUSPENDED returns when hashes match again, else expires. The next attributed correction can re-propose.
7. No parent/child lineage: seeding is blocked for targets with a live probation item, so no descendants exist.
8. Promoted-rule demotion is human-run. Hooks never write curated files; `demote_pending` points to `evolve probation demote`.
9. Probes are deterministic `require`/`forbid` regexes, evaluated only in CLI syncs. Lint probes and an LLM judge are cut.
10. No model/CLI version grouping in v1. Stamps stay in the evidence plane for later use.
11. Injection counts as exposure. The report labels it "exposure, not applicability".
12. The learner picks gate tests from existing tests, as today. It cannot edit tests, hooks, detectors or this package.
13. Thresholds are uncalibrated defaults in one constants module. Output states bounds, never improvement.
14. Kill switch is the evidence plane's env check; every entry point honors it.
15. Code carries no long comments: one-line docstrings at most.

## Related proposals
- `evolution-evidence-plane`: prerequisite. Land it first. `member_files` are disjoint, so fleet path-ordering will not serialize the pair; the operator must. `depends_on` in `proposal.json` is documentation only.
- `self-improvement-loop`: shipped (16/16 ticked). Gate, receipts and rollback are reused, not superseded.
- `meta-harness-alignment`: orthogonal; "no improvement claim from proxies" is kept in L7 and L8.

## Acceptance
- [ ] `tests/context/domains/test_evolve_learning.py`: a `chat:` event built via `enqueue_learning(origin="human")`, prepared and finished against a tiny fixture test file (this file's existing gate pattern), leaves `evolution.jsonl` and `.context/conventions/` byte-identical, creates no `.context/gc/evolve/` dir, and writes a PROBATION item.
- [ ] `tests/context/domains/test_evolve_learning.py`: closeout and legacy `human:` events still auto-apply.
- [ ] `tests/context/domains/test_evolve_learning.py`: a `chat:` body with a URL, a code fence or U+200B ends `blocked` with the high-impact reason; a bad `probe` regex is rejected; `applies_when` defaults to the cue.
- [ ] `tests/context/domains/test_evolve_learning.py`: a second live item for one target, or an eleventh repo-wide, ends `blocked` with `probation cap`.
- [ ] `tests/context/domains/test_evolve_learning.py`: no committed file contains the correction text or the rule body after a `chat:` event reaches PROBATION.
- [ ] `tests/context/domains/test_probation.py`: a retraction demotes a PROBATION item in the same sync.
- [ ] `tests/context/domains/test_probation.py`: two followed corrections in one session, or on one day, do not demote; two in distinct sessions on distinct days do.
- [ ] `tests/context/domains/test_probation.py`: a matched `forbid` probe counts `ignored`; the second sets `needs_enforcement`; the item stays PROBATION.
- [ ] `tests/context/domains/test_probation.py`: `probe: null` counts `contested`; one contested blocks eligibility; `sync(probes=False)` leaves probe attributions unconsumed.
- [ ] `tests/context/domains/test_probation.py`: a changed source suspends and hides the item; restoring it returns PROBATION.
- [ ] `tests/context/domains/test_probation.py`: with an injected `now`, no exposure for the retention window expires the item; file and history remain.
- [ ] `tests/context/domains/test_probation.py`: 9 sessions are not eligible; 10 over 2 days are not; 10 over 3 days with zero harm are; the origin session never counts.
- [ ] `tests/context/domains/test_probation.py`: `route` maps every L2 row, including `naming.md` to `explicit` and `#<id>` of an evolution item to `count`; feature-doc, non-durable and `unknown` attributions enqueue nothing.
- [ ] `tests/context/domains/test_probation.py`: a session with a live probation item for T seeds nothing for T.
- [ ] `tests/context/domains/test_probation.py`: sync leaves a tree hash of `.context/` unchanged outside `cache/evolution`, `gc/learning` and `gc/evidence`; `probation/` source holds no `ledger.json` string.
- [ ] `tests/context/domains/test_probation.py`: the block is ≤1,600 chars; a skipped item has no exposure row; one `Next:` per session follows the L6 priority table; empty `session_id` logs nothing.
- [ ] `tests/context/domains/test_probation.py`: `report` returns `nothing_new` on a second call with equal counts; empty denominators give `null` rates; `resident_bytes` equals block plus promoted body bytes.
- [ ] `tests/context/domains/test_probation_actions.py`: with a fake gate runner, `promote` edits only the managed block on current target bytes, records `gate` and `promote` with `upper_bound_95` ≈ 0.2589 at n=10, and prints no "improv".
- [ ] `tests/context/domains/test_probation_actions.py`: a failing gate keeps PROBATION; a content-scan hit gives QUARANTINED.
- [ ] `tests/context/domains/test_probation_actions.py`: `demote` of a PROMOTED item removes only its block and records `rollback`; a missing block just records DEMOTED.
- [ ] `tests/context/domains/memory/test_memory_cli.py`: `memory session-start` prints the memory block then the probation block; a raising `session_block` leaves output unchanged, exit 0.
- [ ] `tests/cli/test_evolve_probation_cli.py`: empty `attribute --next` prints `nothing to attribute`, exit 0; a recorded retraction demotes at once; bad `--verdict` and bare `--retracts` exit 2; disabled verbs print the disabled line, exit 0.
- [ ] `tests/cli/test_check_budget.py` passes with the edited `SKILL.md`.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `equip`
- `build-loop`
- `evolution`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
