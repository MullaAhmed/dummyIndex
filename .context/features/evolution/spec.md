# Evidence-driven guidance evolution

`confidence: INFERRED` — source and isolated process tests reviewed; model gain unmeasured.

Evolution updates one authoritative convention, playbook or capability from
cited outcomes, through the staged candidate, exact-content test gate,
content-bound receipt, recoverable promotion and rollback.

Closeout enqueues one idempotent learning event. A verified narrow reflection
(`cue`, `lesson`, `evidence`, `confidence`) has rule body `When <cue>: <lesson>`;
`legacy_shape` passes. Only a passing gate applies. Missing checks stay
`evaluated/blocked`; unsupported reflection becomes `no_entry`. Closed statuses:
`applied|evaluated|blocked|no_entry|pending|ignored|failed`. Only persisted `failed`
exits non-zero; failures persist and retry. `evolve learning` also returns 1 on
`EvolveError`/`OSError`/`ValueError` (`dummyindex/cli/evolve.py:158-160`).
Learning, evolution and experiment events cannot trigger themselves. An empty test
list selects no checks and blocks promotion; `evolve apply` without one keeps
target-based discovery. Unrelated tests cannot qualify a
reflection (`dummyindex/context/domains/evolve_gate.py:187-212,432-455`,
`dummyindex/context/domains/evolve_learning.py:191-271`, `dummyindex/cli/evolve.py:112-166,638`).

## Chat probation

- `chat:` learning enters local probation first (`.context/cache/evolution/probation/`, uncommitted). Only the author's sessions load it, labelled provisional. Legacy `human:`, closeout and runtime events still auto-apply.
- States: OBSERVED, PROPOSED, PROBATION, PROMOTED, SUSPENDED, DEMOTED, EXPIRED, QUARANTINED.
- Asymmetric: harm in two sessions on two days demotes fast. Promotion is slow: 10 exposed sessions over 3 days, zero harm or contested, then `evolve probation promote` gates it and the user commits. Ignored rules get `needs_enforcement`, never rollback.
- Blast radius: convention → learning event; `.context/features/**` → reconcile; skills, equipment, playbooks, `naming.md` → explicit `/dummyindex-evolve`.
- Source drift → SUSPENDED; no exposure past retention → EXPIRED.
- Each `evolve probation report` states its output, even `ran, found nothing`. Thresholds are uncalibrated defaults. Output gives only a detector-limited 95% upper bound; no improvement claim.

Managed convention blocks have stable rule IDs, source fingerprints and durable
evidence. Replacement requires the reviewed document hash. Supersession removes
old active wording, preserving owner-authored material outside managed blocks.
Source changes, including edits that preserve line counts, mark rules stale when
read or harvested.

Evidence import reads project-scoped Claude/Codex JSONL and read-only Codex SQLite.
Cursors and origin IDs deduplicate rescans and forks; injected instructions are
excluded. Committed records hold hashes, categories and locators, not transcript
prose or absolute host paths. Local source paths live in `cache/evidence-sources.json`.
Case exposure and ancestry survive raw-history cleanup, so development cases never
become clean held-out cases.

Optional `evolve experiment` runs a trusted external command against isolated
incumbent/candidate snapshots. Every case needs independent outcomes and actual
loaded guidance IDs, versions and hashes. Required controls cannot be hidden by
aggregate gains. Equal quality prefers lower cost, fewer tokens, then fewer guidance
bytes. Winners need separate held-out execution; missing, failed or regressing
measurements retain the incumbent. Fixture tests verify this controller; they are not LLM benchmarks.

Native specifications (`execution: native`) return bounded author, execute and
grade requests for the active host. Pinned inputs survive resumes; the changing
tool-call ID is excluded from identity. Unknown usage stays null; equal quality
with unknown resources retains the incumbent. Only held-out qualification exposes
a `candidate_index` for the ordinary gate and promotion. Adoption preserves every
incumbent held-out pass.

Per-version utility credits only confirmed loaded bodies. Two failed trials mark
a version suspect; low usage alone never causes deletion. Experiments pin cases,
rubric, executor, model, environment, baseline, candidate, seed and repetition.
Infrastructure failures stay distinct from task failures. Terminal receipts are
reused; a new repetition explicitly requests a fresh attempt.
