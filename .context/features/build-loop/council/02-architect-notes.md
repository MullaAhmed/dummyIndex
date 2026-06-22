# Architect notes — build-loop (stage 2)

## What I changed

- Replaced the loose "Where it lives" + "Architecture in three sentences" preamble with a single **Bounded context** section that states the one job (checklist → wave-grouped frontier) and the load-bearing domain/skill split (`__init__.py:18-22`): this feature decides *what/who*, the `dummyindex-build` skill decides *whether/how*.
- Promoted dependencies out of the "Open questions" footnote into a dedicated **Dependencies (upstream / downstream / cycles)** section — the index previously buried the deferred-import seam and the equipment/proposals consumption as throwaway questions.
- Collapsed the three-sentence architecture + data-model prose into **How it works (three invariants)** + a tighter **Parse model**, cutting repetition between the two.
- Promoted two implicit invariants from "Open questions" to first-class **Decisions** ("Independence is delegated, not enforced", "Opaque group id, not the heading label"), and reframed the deferred imports as an intentional cycle-avoidance seam rather than an open question.
- Folded the contract list (previously only in spec) into the plan's tail so the plan is self-contained for a reader who lands here first.
- Cut filler: removed the standalone "Open questions" section (its three items were either answered or promoted to decisions).

## Patterns named

- **Wave independence by construction** — monotonic group ids + plan-step disjoint-file grouping (`checklist.py:25-32`, `80-97`, `115-126`).
- **Warn-and-halt gate split** — code warns (`waves.py:57-61`, `271-272`, `313-314`); the skill halts. Boundary "not-equipped" (`equipped: false`) vs per-item silent `fallback` distinguished (`waves.py:54-56`, `248-250`).
- **Skip as honest non-tick** — `- [~] … — skipped: <reason>` advances the frontier without misreporting (`checklist.py:215-237`).
- **Atomic mtime-preserving flip** — n-th-line tmp-write + `replace`, no-op on done (`checklist.py:163-194`, `207-211`).
- **Pool hygiene** — only non-plugin `kind == "agent"` entries dispatchable (`waves.py:104-129`).
- **Implementer-default routing with specialist margin** — `_SPECIALIST_MIN_SCORE` (2) + strict outscore (`mapping.py:48-49`, `241-248`).
- **Deferred-import cycle-avoidance seam** — `waves.py:159`, `290`.

## Dependencies surfaced

- Upstream: consumes `.context/proposals/<slug>/checklist.md` (plan step, `dispatch.py:131-137`) and `.context/equipment.json` (equip step, `waves.py:81-101`). Sibling-but-not-imported `ProposalError` (`proposals/errors.py:5`).
- Downstream: feeds the `dummyindex-build` skill the dispatch frontier + `equipped` flag (`waves.py:232-276`, `279-337`).
- Internal cycle-avoidance: deferred imports of `map_task_to_equipment` and `next_wave` inside CLI handlers (`waves.py:159`, `290`).

## Decisions promoted

- **Independence is delegated, not enforced** — no code-level disjoint-file check; the plan step's grouping is the sole guarantee (`checklist.py:28-30`). Was an open question; now a stated contract boundary with rationale (domain intentionally does not read source).
- **Opaque group id, not the heading label** — 0-based `group` in JSON is deliberately not `## Wave N` (`waves.py:13-15`, `305`). Was an open question; now a decision.
- **Deferred imports are intentional** — reframed from "intentional or incidental?" to a stated cycle-avoidance seam (`waves.py:159`, `290`).

All `path:range` claims verified against `.context/map/symbols.json` (symbol-definition granularity; finer intra-function spans confirmed via the enclosing symbol). No source or spec edited.
