# Checklist — Ponytail-derived improvements

> Items within a `## Wave` are mutually independent (disjoint files) — build dispatches them concurrently. Waves run strictly in order. Tick `- [x]` only after verifying. Derived from the post-critique plan; each impl item is TDD.

## Wave 1 — foundations (disjoint files)
- [x] Factor `DEBT_PREFIXES` + add `# DEBT:` to `_RATIONALE_PREFIXES` (`pipeline/extract/python_rationale.py`)
- [x] Add `EquipmentItem.invariants` field, omitted from `to_dict` when empty (`context/domains/equip/models.py`)
- [x] Author over-engineering persona card (`skills/audit/agents/over-engineering.md`)
- [x] Author ≥12 retrieval-eval fixtures against the `SAMPLE_REPO` index (`tests/eval/retrieval_fixtures.json`)
- [x] Add pure `compute_badge(report) -> str` helper (`context/drift.py`)

## Wave 2 — build on the foundations (disjoint files)
- [x] Debt harvester: Python-only, repo-relative paths, raw-comment + structured `# DEBT:` parse, `no-trigger` tagging, deterministic order (`context/domains/debt/harvest.py` + `models.py`)
- [x] Canary classifier + `is_user_owned()` guard across `apply`/`refresh`/`uninstall` + `RefreshReport.alarm_invariant_broken` (`equip/enums.py`, `equip/lifecycle/status.py`, `cli/equip/dispatch.py`)
- [x] Badge write at the CLI boundary: atomic, mkdir, isolated try/except (`cli/plan_update.py`)
- [x] Register `"over-engineering": ("review",)` capability pref + resolution tests (`context/domains/audit/catalog.py`)
- [x] Retrieval eval harness + gate + committed `BASELINE.md` + negative control (`tests/eval/test_retrieval_eval.py`, `tests/eval/BASELINE.md`)

## Wave 3 — command bodies + surfacing (disjoint files)
- [x] Debt CLI body: stdout default, `--write`, `--json` (`cli/debt.py`)
- [x] Statusline CLI body + scripts that read the cache directly; Python fallback catches all → exit 0 (`cli/statusline.py`, `statusline.sh`, `statusline.ps1`)
- [x] Renderer populates `invariants` as manifest metadata (not rendered bytes); delete-one→`INVARIANT_BROKEN` round-trip (`equip/generate/specialists.py`)
- [x] Emit-only statusline nudge checking both local + global `statusLine`; writes nothing to settings (`context/hooks.py`)

## Wave 4 — wire the new subcommands (single atomic edit of the shared files)
- [x] Register `ContextSubcommand.DEBT` + `STATUSLINE` and their `_HANDLERS` entries (`context/enums.py`, `cli/__init__.py`)

## Wave 5 — reconcile, review, acceptance
- [x] **GATE** Reconcile new modules into `.context/` (rebuild --changed + reconcile procedure + reconcile-stamp); `compute_drift` shows no unassigned/awaiting for them
- [x] Review the full diff; resolve CRITICAL/HIGH — via /code-review
- [x] Acceptance: debt ledger is repo-relative, Python-only, deterministic; `no-trigger` rule + tally exact; clean repo message (spec Acceptance §1)
- [x] Acceptance: empty-invariants byte-identical (new states unreachable, `to_dict` omits key); `CUSTOMIZED`/`INVARIANT_BROKEN` survive apply/refresh/uninstall + no re-baseline; rendered specialist has real load-bearing invariants (spec Acceptance §2)
- [x] Acceptance: `over-engineering` PersonaCard body carries 5 tags + footer + carve-out; resolves on all three roster paths (spec Acceptance §3)
- [x] Acceptance: eval passes hit-rate@3 ≥ T_hit AND MRR ≥ T_mrr with negative control + per-fixture token check (spec Acceptance §4)
- [x] Acceptance: statusline prints `[ctx ✓]`/`[ctx: N drift]`; existing `statusLine` untouched (both scopes); badge write never fails the hook (spec Acceptance §5)
- [x] Acceptance: full suite green at ≥80% coverage on each new module
