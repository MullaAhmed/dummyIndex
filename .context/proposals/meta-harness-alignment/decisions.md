# Decisions — Meta-Harness alignment

> **Ephemeral working record.** This dir is GC-swept when the proposal closes.
> The durable copy of this decision lives in `.context/features/equip/spec.md`
> (eval Contracts bullet) and in the `meta-harness-vs-dummyindex-verdict`
> memory note. Read this file for the rich detail; read those two for the
> decision that must survive.

## (a) Council verdict (2026-07-01, 5-advisor)

A 5-advisor llm-council (advisors → anonymized peer review → chairman)
analyzed the Stanford Meta-Harness paper (arXiv **2603.28052**; repo
`stanford-iris-lab/meta-harness`) against dummyindex. Meta-Harness is an
outer-loop **search** over harness code, driven by a proposer with full
filesystem access to prior candidates' source, scores, and raw execution
traces, under a Pareto frontier and a strict search/held-out split.

Verdict: the Meta-Harness lens applies to exactly **one** dummyindex surface —
`equip` — and NOT to `.context/`. `.context/` is a navigation map / compiler
output (one-shot, no reward channel), not the paper's "compressed-feedback
bottleneck" (the paper's own Table-3 ablation: raw traces 50.0 >> scores+
summary 34.9 >> scores-only 34.6). Applying search machinery to `.context/`
generation would be a category error. An equipped toolkit, by contrast, is a
policy re-executed every session, and `equip eval` is its nascent objective
function — that is the one place the lens legitimately bites.

Two objectives were flagged as conflated: (1) does the tool fire on the right
prompts — trigger precision/recall, gradeable now but a **proxy**; (2) does
the toolkit improve the agent's actual work — the real **prize** (the paper's
50.0 row), which needs a task benchmark dummyindex doesn't have. Adopted
cheaply: search/held-out separation, anti-overfit discipline, no self-grading,
honest proxy-vs-prize naming, keep `equip eval` a reporter. Rejected: an outer
search loop / Pareto frontier over `.context/`, and promoting the reporter to
a closed-loop gate before its reward is validated.

## (b) The two falsification experiments (2026-07-05)

Before building any evolve-loop, the council's own discipline demanded a
falsification check: does the `equip eval` scalar even correlate with a tool
being useful, and is there headroom for a search loop to climb?

**Experiment 1 — `dummyindex-db-specialist`.** 14 hand-authored synthetic
cases split search(7)/held-out(7); held-out positives reworded, held-out
decoys near-misses (pg pool config, ad-hoc SQL, React memo). Independent blind
router subagents produced observations; a tuner rewrote the description on
the search set only; scored via the real `score_run`. Result: **all four
cells (baseline/tuned × search/held-out) = accuracy 1.00**, zero misfires.
The already-well-scoped description routes perfectly, so the trigger-accuracy
proxy has no headroom. The tuner visibly **overfit** — it enumerated the exact
search-decoy categories — but couldn't help (already 1.0) and didn't regress.

**Experiment 2 — `dummyindex-security-specialist` (headroom hunt).** Repeated
on a domain deliberately chosen to overlap `reviewer`/`implementer`, suite
engineered to induce errors: subtle data-exposure positives (false-negative
bait) plus security-flavored decoys — CVE dep bump, input-validation,
hashlib swap, dependency audit (false-positive bait) — with **two independent
blind routers per baseline cell**. Result again: **all four cells = 1.00**,
zero misfires, both routers identical (no boundary instability).

Combined: trigger-accuracy has **no headroom** for reasonably-described tools
even at engineered boundaries, so a search loop has nothing to optimize.
Root cause: a capable router plus a decent one-shot description saturates
routing; headroom would need a genuinely bad description, whose fix is
regenerate/patch-once (which `equip` already does), not search. **Decision:
the trigger-accuracy `equip evolve-loop` is contraindicated (CONTRAINDICATED)**
— do not build it; keep `equip eval` a reporter.

## (c) What stays true

`equip eval` remains a pure **reporter** of a routing **proxy** (does the
description fire on the right prompts) — no LLM-in-code, no search loop, no
Pareto frontier, no persisted "best" candidate. The real **prize** — does the
equipped tool make the agent's work better, gradeable against the repo's own
test suite (the SWE-bench-style reward most repos already have, and which
`build-loop` already runs) — is the only future direction worth revisiting,
and it is explicitly not built by this proposal.

## (d) Upstream corroboration (R3, 2026-08-07)

The paper's own repo now agrees with the contraindication. Upstream PR #12
(2026-07-11) added `experimental/harbor_meta_harness/` — an outer-loop pilot
whose reward is **task-outcome** via Harbor verifier suites (aggregate
mean/min/fraction_solved); trigger accuracy appears nowhere in it. Its README
mandates "Probe each collection before using it" — a measured headroom check
before any loop, the same discipline experiments (b) applied before
concluding CONTRAINDICATED. Its `forbidden_references` denylist guards
exactly the leakage/tuner-overfit failure mode observed in both experiments.
Cite: `meta-harness@44b9942:experimental/harbor_meta_harness/README.md` and
`controller.py` (`forbidden_references` ~127-149, `validate_source` ~272+).

## (e) Second corroborating exhibit (prime-agent, 2026-08-07)

`PrimeIntellect-ai/prime-agent` (Continual Harness, arXiv 2605.09998; pinned
`87e7a7f`) ships a self-optimization loop in production that dropped its own
paper's outcome channel. Its `/refine` loop is **self-judged**: the
"evidence" field is the proposing LLM's own rationale, not an independent
check. `expectedOutcome` is recorded but never validated. Auto-refine
defaults ON (every 25 turns / at compaction, LLM-gated). The kernel CRUD path
bypasses even those gates entirely. This is a shipping instance of exactly
the self-optimization shape this proposal contraindicates. Cite:
`prime-agent@87e7a7f:packages/coding-agent/src/core/refinement/refinement.ts`
and `prompts/rlm.ts:29`.
