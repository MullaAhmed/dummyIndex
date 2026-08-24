# Spec — One-command context maintain loop with enrichment estimates, scoping, resume, and default auto-recouncil

> Scaffolded by `dummyindex context propose`. Flesh out the intent
> and contracts below, then keep the **Acceptance** checklist honest.

## Intent

Maintenance of a curated index today is a hand-scripted pipeline. The user's own run
book (BOS-Mono frontend, 2026-08-22) is: `rebuild --changed` → `reconcile` → per drifted
feature `/dummyindex --recouncil <id>` → `reconcile-stamp` each → verify zero drift →
commit `chore(context): re-anchor`. Every step exists as a separate CLI verb or skill
procedure, so every session re-assembles the loop from prose — and the expensive middle
(enrichment recouncil) runs blind: "the reconcile has been going for hours why?"
(99.5/127.7-minute batches), killed at a spend cap with no way to resume except
transcript archaeology.

Goals:

1. One deterministic verb that assembles the loop and emits exactly the LLM work
   remaining, checkpointed so any kill resumes.
2. Cost honesty before the spend happens: an estimate of features × stages × units
   before anything launches, with a hard scope flag.
3. Builds end clean: after the final wave, recouncil runs by default (user ruling:
   "recouncil should run automatically always at the end unless stated otherwise") with
   an explicit opt-out instead of a confirm-gate.

## Contracts

- **New verb family** under `context maintain`:
  - `maintain plan [--max-features N] [--json]` — read-only assembly: run
    `compute_reconcile_report`, list drifted features + unassigned files, print the
    ordered work list with **estimates** (features × council stages from
    `active_stages()` × units per stage; unit counts come from the existing
    council-batch frontier computation). Exit 0.
  - `maintain begin [--max-features N]` — write the run manifest
    `.context/fleet/maintain-<ts>/RUN.md` + state file
    `.context/fleet/maintain-<ts>/state.json` (**committed** artifacts, mirroring the
    `gc/state.json` precedent) containing: anchor sha, feature work list in execution
    order, per-feature stage checklists, estimates, status per unit (`pending|done|skipped`),
    created/updated timestamps.
  - `maintain next [--run <dir>]` — print the earliest incomplete unit across the run
    (same frontier semantics as `council_batch.next_batch`) so the host skill can launch
    one subagent per unit without re-deriving order. `--json` available.
  - `maintain done --feature <id> [--stage <stage>] [--run <dir>]` — mark units complete;
    `maintain stamp` wraps `reconcile-stamp` for the finished feature and ticks it in
    state.json.
  - `maintain status [--run <dir>] [--json]` — counts done/pending/skipped, elapsed,
    estimated remaining.
- **Estimate honesty.** Estimates are computed from deterministic counters only (nodes
  per feature from `enrich.build_plan`, stages from `active_stages(mode)`); they are
  labelled `estimate:` in output. No invented wall-clock promises beyond a clearly
  labelled heuristic (`units × 90s` reference point, printed as heuristic).
- **Scope guard.** `--max-features N` truncates the work list to N features (priority:
  drifted_features → awaiting_enrichment → unassigned placement). Without the flag all
  features are listed; `begin` requires either the flag or an explicit `--all`.
- **Resume.** All verbs accept `--run <dir>` (default: newest `maintain-*` dir under
  `.context/fleet/` — prefix-scoped so fleet-runner's `run-*` dirs are never picked up). State mutations are atomic writes; a killed run resumes from
  `state.json`, never from transcripts.
- **Auto-recouncil default for builds.** `config.json` gains schema v5 key
  `"build": {"auto_recouncil": true}` (default true; read-migrate v4 configs like the
  v3→v4 precedent in `domains/config.py`). `/dummyindex-build` procedure appends a
  mandatory closing phase: after the last accepted wave, run the maintain loop
  (`maintain begin/next…`) until the run reports zero pending, then commit the
  re-anchor as `chore(context): re-anchor`. `--no-recouncil` on the build invocation
  (and `auto_recouncil: false` in config) skips it, printing the pending count left
  behind. The build-loop CLI surfaces the flag through `build --check/--status` payloads
  (`models.py` untouched where possible).
- **Invariants.** No LLM calls from the CLI itself; the host skill consumes `next`
  units. Everything written under `.context/fleet/` is committed (it is the durable
  cross-session memory of a maintenance run); nothing under `cache/`.

## Acceptance

> All verified on build/maintain-guardrails (2026-08-23); see checklist.md.

- [x] `uv run pytest tests/cli/test_maintain.py` green: `plan` prints estimate lines +
      ordered features; `begin` writes RUN.md + state.json; `next` returns earliest
      incomplete unit; `done`+`stamp` advance state; `status` counts match.
- [x] Resume test: kill simulation (hand-corrupt one unit to `pending` after others
      `done`) → `next` resumes at correct unit, never repeats done units.
- [x] Scope test: `--max-features 1` truncates work list and `begin --max-features 1`
      refuses without `--all`.
- [x] Config v5 read-migration test: v4 config opens cleanly; `auto_recouncil` defaults
      True; explicit false honoured.
- [x] Build-skill doc test (grep-level): `/dummyindex-build` SKILL contains the
      closing-phase contract and the `--no-recouncil` escape hatch.
- [x] Full suite green: `python -m pytest tests/ -q --tb=short`.

## Open questions — RESOLVED at build time (orchestrator ruling)

- Q1: SETTLED as opt-in heal. `reconcile-stamp --heal-orphaned` re-baselines an
  orphaned anchor at HEAD with a loud warning; the default refusal is unchanged.
  (`not_ancestor` was never the orphan case — `missing_from_repo` is.)
- Q2: SETTLED as new top-level `.context/fleet/`, committed. The directory is owned
  by the fleet-runner proposal; this proposal's runs use the `maintain-*` prefix so
  neither picks up the other's dirs. HOW_TO_USE's committed-layout table is left to
  fleet-runner to extend.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `install-surface`
- `tree-enrich`
- `cli-dispatch`
- `equip`
- `session-memory`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
