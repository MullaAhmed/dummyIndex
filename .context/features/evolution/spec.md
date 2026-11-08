# Evidence-driven guidance evolution

`confidence: INFERRED` — source and isolated process tests reviewed; model gain unmeasured.

Evolution updates one convention, playbook or capability from cited outcomes. It stages one candidate, gates exact content with a content-bound receipt, then promotes with recoverable rollback.

Closeout enqueues one idempotent learning event. A verified narrow reflection (`cue`, `lesson`, `evidence`, `confidence`) has rule body `When <cue>: <lesson>`; `legacy_shape` passes. Only a passing gate applies. Missing checks stay `evaluated/blocked`. Unsupported reflection becomes `no_entry`. Closed statuses: `applied|evaluated|blocked|no_entry|pending|ignored|failed`. Only persisted `failed` exits non-zero; failures persist and retry. `evolve learning` returns 1 on `EvolveError`/`OSError`/`ValueError` (`dummyindex/cli/evolve.py:161-163`). Learning, evolution and experiment events never self-trigger. An empty test list selects no checks and blocks promotion. Unrelated tests cannot qualify a reflection; `evolve apply` without tests keeps target-based discovery (`dummyindex/context/domains/evolve_gate.py:187-219`, `dummyindex/context/domains/evolve_learning.py:178-303`).

## Chat learning and probation

- `chat:` runs stage under `.context/cache/evolution/runs/`, uncommitted. High-impact body or cue blocks at once.
- A passing gate calls `probation.actions.enter` (`dummyindex/context/domains/evolve_learning.py:363`). It writes no `evolution.jsonl` event.
- Qualification reads `project tests only; no model-quality claim`.
- Probation items live in `.context/cache/evolution/probation/`. Only the author's sessions load them, labelled provisional.
- Blast radius: `.context/features/**` routes to reconcile. `naming.md`, skills, equipment and playbooks need explicit `/dummyindex-evolve`.
- Human corrections seed `chat:` probation. Closeout, runtime and legacy `human:` learning auto-apply.
- Ignored rules get `needs_enforcement`, never rollback. Each `evolve probation report` states its output, even `ran, found nothing`.
- Thresholds are uncalibrated defaults. Reports give a detector-limited 95% upper bound; no improvement claim.
- Lifecycle, states and thresholds belong to the `probation` feature. Promotion: `evolve probation promote` (`dummyindex/cli/evolve_probation.py:144`).

## Evidence import

Evidence import belongs to `observe`. It runs locked, bounded to 20 s. Committed `.context/gc/evidence.json` holds exposure only, schema 2. Schema-1 data migrates into the local ledger on write (`dummyindex/context/domains/evidence.py:94`). Local source paths live in `.context/cache/evidence-sources.json`, never committed. Probation seeds write committed stubs with schema_version, id, host, day and detector only. Case exposure and ancestry survive raw-history cleanup, so development cases never become clean held-out cases.

## Experiments and native specs

Optional `evolve experiment` runs a trusted external command on isolated incumbent and candidate snapshots. Every case needs independent outcomes and actual loaded guidance IDs, versions and hashes. Required controls cannot be hidden by aggregate gains. Equal quality prefers lower cost, fewer tokens, then fewer guidance bytes. Winners need separate held-out execution; missing, failed or regressing measurements retain the incumbent. Fixture tests verify the controller only, not LLM benchmarks.

Native specifications (`execution: native`) return bounded author, execute and grade requests for the active host. Pinned inputs survive resumes; the changing tool-call ID is excluded. Unknown usage stays null; equal quality with unknown resources retains the incumbent. Only held-out qualification exposes `candidate_index`. Adoption preserves every incumbent held-out pass.

Per-version utility credits only confirmed loaded bodies. Two failed trials mark a version suspect; low usage alone never causes deletion. Experiments pin cases, rubric, executor, model, environment, baseline, candidate, seed and repetition. Infrastructure failures stay distinct from task failures. Terminal receipts reuse; a new repetition requests a fresh attempt explicitly.

## Managed rules

Managed convention blocks keep stable rule IDs, source fingerprints and durable evidence. Replacement requires the reviewed document hash. Supersession keeps owner-authored text outside managed blocks. Source edits, even line-count-preserving ones, mark rules stale when read or harvested.
