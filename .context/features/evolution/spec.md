# Evidence-driven guidance evolution

`confidence: INFERRED` — source and isolated process tests reviewed; model gain unmeasured.

Evolution updates a small authoritative convention, playbook or capability from
cited outcomes. It reuses the staged candidate, exact-content project test gate,
content-bound receipt, recoverable promotion and rollback.

Closeout can enqueue one idempotent learning event. A verified narrow reflection
is a lesson record (`cue`, `lesson`, `evidence`, `confidence`). Its rule body is
`When <cue>: <lesson>`. Pre-change reflections pass as `legacy_shape`. The gate
then runs, and only a passing candidate is applied automatically. Missing checks
remain `evaluated/blocked`; unsupported reflection becomes `no_entry`. Events store
a closed `status`: `applied|evaluated|blocked|no_entry|pending|ignored|failed`.
For a persisted event, only `failed` exits non-zero; closeout failures persist and retry. `evolve learning` also returns 1 on `EvolveError`/`OSError`/`ValueError` (`dummyindex/cli/evolve.py:158-160`).
Learning/evolution/experiment events cannot trigger themselves. For learning closeout,
an explicitly empty test list selects no checks and blocks promotion; omitting test
selection in `evolve apply` retains target-based discovery. Unrelated tests cannot
qualify that reflection (`dummyindex/context/domains/evolve_gate.py:187-212,432-455`,
`dummyindex/context/domains/evolve_learning.py:191-271`, `dummyindex/cli/evolve.py:112-166,638`).

Managed convention blocks have stable rule IDs, source fingerprints and durable
evidence. Replacement requires the reviewed document hash. Supersession removes
old active wording, preserving owner-authored material outside managed blocks.
Source changes, including edits that preserve line counts, mark rules stale when
read or harvested.

Evidence import reads project-scoped Claude/Codex JSONL and supported read-only
Codex SQLite tables. Cursors and origin IDs deduplicate
rescans and copied/forked rows; injected instructions are excluded. Committed
records contain hashes/categories and source locators, not transcript prose or
absolute host paths. Local source paths live only in `cache/evidence-sources.json`.
Case exposure and derived ancestry survive raw-history cleanup and prevent
development cases from becoming clean held-out cases later.

Optional `evolve experiment` executes a trusted external agent/evaluator command
against isolated incumbent/candidate snapshots. It requires independent outcomes
for every case and actual loaded guidance IDs, versions and content hashes.
Required controls cannot be hidden by aggregate gains. Equal-quality strategies
prefer lower cost, then fewer measured tokens, then fewer captured guidance
bytes. Every winner needs separate held-out incumbent/candidate execution. Missing,
failed or regressing measurements retain the incumbent. General, domain and
supported composition probes execute separately. Deterministic fixture tests
verify this controller; they are not LLM benchmarks.

Native specifications (`execution: native`) instead return bounded author,
execute and independent-grade requests for the active host. Actual incumbent
feedback precedes general/domain proposals; composition sees their tested changes
and outcomes. Root inputs, accepted candidates, feedback, checked artifacts and
runtime identity remain pinned across resumes; the changing host tool-call ID
is excluded from environment identity. Unknown usage stays null; equal
quality with unknown resources retains the incumbent. The fixed deadline and
action count survive continuation. Only held-out qualification exposes a
`candidate_index` for the ordinary project gate and promotion.
A distinct development tie that preserves incumbent passes can receive one
held-out probe. Native adoption also preserves every incumbent held-out pass;
an aggregate gain cannot hide a regression on another case.
Native snapshots keep the verified active context-graph generation; historical
shards stay in the owner checkout.

Per-version utility credits only confirmed loaded bodies. Two failed trials mark
a version suspect; low usage alone never causes deletion. Experiments pin cases,
rubric, executor, model, environment, baseline, candidate, seed and repetition.
Resource bounds cover scheduled stages and retries; infrastructure failures stay
distinct from task failures. Terminal receipts, including failures, are reused;
a new repetition explicitly requests a fresh attempt.
