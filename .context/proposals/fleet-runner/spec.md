# Spec — Fleet runner: checkpointed multi-proposal overnight execution with budget circuit-breaker and commit policy

## Intent

The user hand-built `overnight-todo-run` in BOS-Mono/backend (.claude/skills/, 69 lines)
after one 22-hour session: sweep Linear todo, group tickets into plans by file-
disjointness, plan in parallel forks, execute each plan in an isolated worktree via
orchestrators that spawn workers, babysit, then merge PRs in order. It worked (7 plans,
7 PRs, 29 commits) but its scar tissue is structural and now proven live:

- run state was an **uncommitted** EXECUTION-ORDER.md that no longer exists on disk;
- a monthly spend cap killed five agents at once mid-wave (02:05) and recovery cost
  half a night;
- one unanswered interview question stalled the entire follow-up run (19:24);
- ticket-count mismatches needed human noticing twice.

The durable IP — ordering, isolation, checkpointing, budget, commit policy — belongs in
the deterministic CLI. The inherently runtime-bound parts (babysitter loop, subagent
spawning, Linear MCP access, the one-interview round) stay in a thin packaged skill.

## Contracts

- New verb family `dummyindex context fleet` over new domain
  `dummyindex/context/domains/fleetrun.py` (distinct from proposal B's
  `domains/fleet.py`; both share the `.context/fleet/` directory namespace with
  disjoint run-id prefixes `maintain-*` vs `run-*`):
  - `fleet init --plans <slug[,slug…]> | --intake intake.json --budget-usd N
    --max-parallel N --branch-template "<tpl>" [--ruling k=v]…` — writes **committed**
    artifacts under `.context/fleet/run-<id>/`: `RUN-MANIFEST.md` (human-readable:
    units, priority order, merge order, rulings, commit-policy block: magic-word map,
    stage-only-owned-files rule, trailer blocklist) and `state.json` (machine:
    `{units:[{id,slug,branch,status: pending|planning|building|merging|done|blocked|
    gated, paths[], revision, gate_question?}], budget:{cap_usd, spent_est_usd},
    max_parallel, created}`), atomic writes, `gc/state.json` precedent for committing.
    Intake JSON is produced host-side (Linear MCP); the CLI stays tracker-agnostic —
    `{ticket, title, paths[]}` entries (`repo_hint`/`size` optional host-only metadata,
    not consumed by the CLI).
  - `fleet next [--run DIR] [--json]` — returns up to `max_parallel` dispatchable
    units: earliest-priority first, never two units whose member-path sets intersect,
    skipping blocked/gated ones. Disjointness data comes from the unit's `paths[]`
    (intake entries carry them; `--plans` mode reads optional `member_files` from each
    `proposal.json`, falling back to conservative intersection = serial when absent).
    Default run discovery is prefix-scoped: newest `run-*` dir only. When `spent_est_usd >= cap_usd` every response is a
    `BUDGET-HALT` envelope with exact resume instructions.
  - `fleet checkpoint --unit <id> --status <st> [--wave N] [--gate "question"]
    [--note …]` — advance state; a unit carrying an unanswered `--gate` becomes status
    `gated` and is skipped by `next` forever until answered via a later checkpoint —
    **the anti-stall rule**: no run ever waits on a question.
  - `fleet spend --unit <id> --est-usd X` — accumulates the meter that feeds the
    breaker.
  - `fleet merge-order [--run DIR]` — prints landing order with dependency rationale.
- Branch naming from `--branch-template` (default neutral `{run}/{id}-{slug}`; pass e.g. `ahmed/{id}-{slug}` explicitly).
- Host-side skill (packaged): `dummyindex/skills/fleet/SKILL.md` — the babysitter
  procedure driving the verbs: intake production, grouping rules (small+disjoint batch,
  big/solo, subset-dedupe), parallel planning forks, worktree-isolated orchestrators,
  dormant-agent probes, foreground verification, resume-from-state (never transcripts),
  PR/merge phase opt-in. All state reads/writes go through the CLI verbs.
- Invariants: deterministic CLI; committed run artifacts; corrupt state.json fails loud
  (unlike append-only logs) because it is the single source of truth; no LLM in-process.

## Acceptance

- [ ] pytest `tests/context/domains/test_fleetrun.py`: init writes both artifacts;
      next respects priority, max_parallel, and file-disjointness; gated units are
      permanently skipped; budget halt trips at cap and clears only via checkpointed
      spend reduction (resume path explicit).
- [ ] pytest `tests/cli/test_fleet_cli.py`: full lifecycle on temp repo — init from
      two fixture proposals, next/checkpoint/spend loop to done, merge-order stable.
- [ ] Anti-stall test: a run where every unit gets gated still terminates `next` with
      an empty-but-valid envelope (exit 0).
- [ ] Doc grep: packaged SKILL contains resume-from-state and foreground-verification
      red-flag rules; contains no hardcoded repo names or project refs.
- [ ] Full suite green: `python -m pytest tests/ -q --tb=short`.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `gc`
- `equip`
- `proposals`
- `install-surface`
- `codex-guidance`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
