# Checklist — build-dispatch-fanout-fix

> Waves strictly ordered; within-wave items file-disjoint (proof: `plan.md`
> § Wave disjointness). T2→T4 share `waves.py` and are split across waves.

## Wave 1 — domain layer

- [x] T1 `dispatch_mode` agent-classification (`agent:` prefix + bare-name pool
      match, default-pure) — `dummyindex/context/domains/buildloop/models.py`
- [x] T3 routing module: `parse_route_flags/resolve_routing`, `ModelChoice`
      validation, propose-template `routing` note —
      `dummyindex/context/domains/buildloop/routing.py` (NEW),
      `dummyindex/cli/propose.py`

## Wave 2

- [x] T2 mapper passes agent-name pool; typed-entry-only pinning; unknown `agent:`
      fails safe; adds `routing` + `upgrade_note` keys to do_next/do_next_wave
      payloads — `dummyindex/cli/build_loop/waves.py` (after T1)
- [x] T5 skill docs + USAGE: two-class rule + corrected step-8 assertion in
      `plan/SKILL.md`; `--route` + models-disclosure + carve-out in `build/SKILL.md`;
      `--route` lines in `cli/help.py` USAGE (+ guide copy)
- [x] T5 skill docs: two-class tag rule + corrected step-8 assertion in
      `plan/SKILL.md`; `--route` + models-disclosure + carve-out in `build/SKILL.md`

## Wave 3

- [x] T4 `_do_status` renders routing; next/next-wave payloads gain `routing` +
      `upgrade_note` keys — `dummyindex/cli/build_loop/dispatch.py`

## Wave 4 — tests (disjoint files)

- [x] T6a classifier matrix (agent:/bare-match/GATE/skill-kind) — extend
      `tests/context/domains/test_build_loop_routing.py`
- [x] T6b pool-upgrade path + pinning — `tests/cli/test_waves_upgrade.py` (NEW)
- [x] T6c precedence invocation > proposal > unset; invalid alias rejected —
      `tests/context/domains/test_model_routing.py` (NEW)
- [x] T6d doc grep test: disclosure step present; step-8 two-class wording

## Wave 5 — acceptance

- [x] A1 classifier matrix green — via dummyindex-verify
- [x] A2 fixture: `— via python-implementer` maps pinned-subagent; `/dummyindex-verify` skill tag stays main-session — via dummyindex-verify
- [x] A3 routing precedence + validation green — via dummyindex-verify
- [x] A4 `--status` shows routing; next-wave payloads expose `routing`/`upgrade_note`; unknown-agent tag degrades safely — via dummyindex-verify
- [x] A5 full suite `python -m pytest tests/ -q --tb=short` green — via dummyindex-verify
- [x] A6 landing commit uses `fix:` type (behaviour defect) for the dispatch change;
      body documents the new tag class. No hand-edit of `CHANGELOG.md`.
