# Spec — Fold skill-creator eval/benchmark loop into equip: measure + benchmark generated skills/specialists

`status: planned` · `created: 2026-07-01`

Give **equip** the one lifecycle stage it lacks: a way to **measure** whether a
generated/vendored tool actually works — starting with *trigger-description
accuracy* (does the tool's `description`/"Use when" fire on the prompts it
should, and stay silent on the ones it shouldn't) and *benchmark stability*
(variance across repeated runs). Ported in spirit from Anthropic's
`skill-creator` (`anthropics/skills`), whose **Create / Eval / Improve /
Benchmark** loop is exactly the discipline equip's generator side is missing.

## Intent

**Problem.** equip *generates* tuned skills/agents (`generate/render.py`,
`generate/catalog.py`) and *governs* them well — trust gating, blast-radius
disclosure, atomic never-clobber install, a hash-baselined lifecycle
(`lifecycle/status.py`), provenance pinning. But it never checks whether a
generated or vendored tool is *effective*: whether its `description` triggers on
the right prompts, or whether it behaves consistently. This is the exact standing
gap the sibling proposal flagged and left out of scope:

> *"No success metric for 'trustworthy context' — every adoption hardens artifact
> correctness; none proves `.context/` improves retrieval."*
> — `.context/proposals/external-repo-adoptions/spec.md` (Blind spots)

`skill-creator` closes this for *hand-authored* skills (Eval + Benchmark modes —
test cases, precision/recall on triggering, variance across runs). equip is the
*generator*; it should own the same measurement stage for the tools it emits.

**Who.** Anyone running `/dummyindex-equip` who wants evidence — not a hope —
that a generated specialist or vendored skill fires when it should. Feeds the
existing `equip patch` improvement seam (`lifecycle/evolve.py:apply_patch`) so a
low-scoring description can be rewritten and re-measured.

**The call: ADAPT, not ADOPT (technique port, not vendor).** This mirrors the
sibling proposal's anchor decision on the tdd-guard *reporter* vs the tdd-guard
*LLM-judge*: we keep the **deterministic artifact** (score + benchmark) in code
and push the **LLM judgment** (does this prompt trigger this description?) into
the `dummyindex-equip` skill markdown — never a subprocess LLM call from the
domain. `skill-creator` is Anthropic-authored; we port the *loop shape*, vendor
no code. (`mcp-builder`, the sibling skill for MCP-server scaffolding, is noted
only as adjacent prior art for a future generator-side effort — **out of scope
here**.)

## Contracts

> **Numeric & edge-case conventions are pinned here on purpose** — the critique
> panel flagged them as the highest-risk holes. `score_run`/`aggregate_benchmark`
> are the correctness core; every convention below is a testable invariant.

**New pure domain — `dummyindex/context/domains/equip/eval/`** (no I/O, no
network, no LLM; the "never an LLM judge in code" spine holds. This is a
deliberate sub-package — 6 modules `enums/models/errors/score/cases/__init__`
grow their own canonical trio, so the eval alphabet lives in `eval/enums.py`, not
the sibling `equip/enums.py`):

- `enums.py` — `EvalOutcome(str, Enum)`:
  `TRUE_POSITIVE | FALSE_POSITIVE | TRUE_NEGATIVE | FALSE_NEGATIVE`.
- `models.py` — frozen dataclasses, each with a hand-written `to_dict()` per
  `conventions/coding-practices.md`:
  - `EvalCase(case_id: str, prompt: str, expects_trigger: bool)` — one labelled
    triggering test. Prompts are **committed** under `.context/` (see path
    below) → suites MUST use synthetic prompts, never real/secret-bearing text.
  - `TriggerObservation(case_id: str, fired: bool)` — one *observed* firing
    decision (produced by the skill's LLM judgment, fed in as data).
  - `EvalResult(tool_name, cases: tuple[...], counts per EvalOutcome, precision,
    recall, accuracy, misfires: tuple[EvalCase, ...])`.
  - `BenchmarkReport(tool_name, runs: tuple[EvalResult, ...], mean_accuracy,
    accuracy_variance, flaky_case_ids: tuple[str, ...])`.
- `errors.py` — `EvalError(EquipError)` base (bases on `EquipError` so the
  existing CLI `except EquipError` path catches it) +
  `EvalSuiteError` (malformed **suite** content), `ObservationsError` (malformed
  **observations** content), `EvalSuiteNotFoundError`,
  `ObservationMismatchError` (observation `case_id` not in the suite),
  `MissingObservationError` (a suite case has no observation).
- `score.py` — pure. **Pinned numeric conventions:**
  - `score_run(cases, observations) -> EvalResult` — confusion matrix →
    precision / recall / accuracy. **Zero-denominator ⇒ `0.0`** (sklearn
    `zero_division=0` convention): no positive predictions ⇒ precision `0.0`; no
    actual positives ⇒ recall `0.0`; accuracy is always defined (empty suite ⇒
    `0.0`). **Coverage is bidirectional**: every observation must match a case
    (`ObservationMismatchError`) **and** every case must have an observation
    (`MissingObservationError`, listing the unobserved `case_id`s) — a dropped
    parallel-subagent judgment fails loud, never scores a partial suite.
  - `aggregate_benchmark(results) -> BenchmarkReport` — **population** variance
    of accuracy (÷N). All runs MUST cover the **same `case_id` set**; a mismatch
    ⇒ `EvalError` (a suite was edited mid-benchmark). A case is **flaky** iff its
    outcome is not identical across every run. `<2` runs ⇒ `accuracy_variance =
    0.0`, empty `flaky_case_ids` (a single run is trivially non-flaky).
- `cases.py` — pure parse/serialize:
  `parse_eval_suite(data) -> tuple[EvalCase,...]` (raises `EvalSuiteError` on a
  **duplicate `case_id`** — it is the join + flaky key),
  `parse_observations(data) -> tuple[TriggerObservation,...]` (raises
  `ObservationsError`), `suite_to_dict` / `result_to_dict` /
  `benchmark_to_dict`. Fail-fast on malformed input.
- `__init__.py` — public re-exports (the test surface).

**Artifact location — a NEW named constant, not `EQUIPMENT_REL`.**
`EQUIPMENT_REL = "equipment.json"` is a *filename*, not a dir root. Add
`EVALS_REL = "equipment-evals"` beside it in `lifecycle/manifest.py` (a sibling
dir, deliberately **not** `.context/equipment/` which would shadow the
`equipment.json` file). Suites/results/benchmarks live at
`.context/equipment-evals/<tool>.{suite,result,benchmark}.json`.

**New CLI verbs — `dummyindex/cli/equip/eval.py`** (all subprocess/file I/O at
this boundary, per `conventions/coding-practices.md`):

- **Tool-name safety (BLOCK):** `<tool>` is a manifest item name — **vendored**
  skill names come from an external `SKILL.md` and are attacker-controllable
  (`../../.claude/settings`). A shared `_safe_tool_name(tool) -> str` validates
  against `^[A-Za-z0-9._-]+$` (reject `/`, `..`, leading `.`) at the CLI boundary
  and exits **2** before any path is built — no `write_text_atomic` traversal.
- `equip eval <tool> --observations FILE [--suite FILE] [--run-label L] [--force] [--root DIR] [--json]`
  — read the suite (default `.context/equipment-evals/<tool>.suite.json`) + the
  observations file, call the pure `score_run`, write
  `<tool>.result.json` (or `<tool>.run-<L>.result.json`) via
  `atomic_io.write_text_atomic`, print accuracy + each misfire's **`case_id` +
  `EvalOutcome`**. **Exit codes** (matching the equip family): `2` = bad flags /
  unsafe tool name / **missing suite file** (`EvalSuiteNotFoundError`); `1` =
  **malformed** suite or observations content (`EvalSuiteError`/`ObservationsError`,
  both `json.JSONDecodeError`/`OSError` caught here); `0` = scored. A
  `--run-label` whose result file already exists is rejected unless `--force`
  (silent overwrite would deflate benchmark variance).
- `equip benchmark <tool> [--root DIR] [--json]`
  — guard `evals_dir.is_dir()` (missing dir ⇒ treated as no runs), glob
  `<tool>.run-*.result.json` **excluding `*.tmp`**, call `aggregate_benchmark`,
  write `<tool>.benchmark.json`, print mean accuracy + variance + flaky cases.
  **Fail-open**: zero run files ⇒ stderr warning + **exit 0**, and writes **no**
  benchmark file. When a labelless `<tool>.result.json` exists but no `run-*`
  files do, the warning says "unlabelled results — re-run `equip eval
  --run-label`" (not a silent no-op). This is a **reporter, not a gate**.
- `EquipVerb` gains `EVAL` + `BENCHMARK`; `cli/equip/dispatch.py` routes them.

**Skill-side loop — `dummyindex-equip` skill markdown** (the LLM half, kept out
of code):

A new "evaluate a generated tool" procedure: read the tool's `description`;
gather/author an eval suite; **dispatch parallel subagents** (Task tool) to judge
each case *blind to its expected label* — "would a tool described as `<desc>`
fire on `<prompt>`?"; assemble the `TriggerObservation` list; call `equip eval`.
For **benchmark**, repeat K runs with fresh judgments (`--run-label`), then
`equip benchmark`. **Improve loop**: if accuracy is low, propose a `description`
rewrite through the existing `equip patch --item <tool> --from-file …`
(`lifecycle/evolve.py:apply_patch`) and re-measure. This is the same
"deterministic plumbing in code, orchestration in the skill" split that
build-loop and council already use.

**Suite authoring (NON-optional — the loop is dead without it).** The eval verb
requires a `<tool>.suite.json` to exist. Documenting the **suite JSON schema and
how a user hand-authors one** therefore lives in the skill markdown (Wave 7,
task 14) as a *required* deliverable — only the *automated seeding* below is
stretch.

**Optional wiring (stretch — Wave 7, additive & never-clobber):**
- `equip apply` seeds a starter `<tool>.suite.json` per generated tool (a couple
  of capability-derived positive cases + one decoy negative). Seeding happens in
  the **CLI apply write path** (`dispatch.py` `_apply_write`), **never** in the
  pure `generate/catalog.py` — catalog decides specs, the boundary writes files.
  Written under the same atomic never-clobber guard so a hand-edited suite is
  never stomped.
- `equip status` surfaces tools with no recorded `.result.json` as
  **"unevaluated"** via a **new `StatusReport.unevaluated: tuple[str, ...]`
  channel** (mirroring the existing `missing_playbook` channel), populated at the
  **CLI layer** (the status handler globs the evals dir) — `lifecycle/status.py`
  stays pure and `ItemState` is **not** touched (evaluation-state is orthogonal
  to the origin-hash lifecycle).

**Layering & reuse (honour `conventions/*`):**
- New domain modules are **pure**; every subprocess/file touch stays in
  `cli/equip/eval.py`. Reuse `atomic_io.write_text_atomic`, `EQUIPMENT_REL`,
  `Capability`, `EquipVerb`, `content_hash`, the `EquipmentManifest` loader (for
  `status`), and `apply_patch` (for the improve loop). No new dependency.
- Files stay small (`conventions/folder-organization.md`): one concern per
  module, `<600` lines, CLI handler thin.

## Acceptance

- [ ] `score_run` computes the correct confusion matrix + precision / recall /
      accuracy on all-positive, all-negative, and mixed fixtures; pure (a test
      monkeypatches `open`/`Path.read_text` to raise and `score_run` still
      succeeds). Pinned edges asserted with exact numbers: **all-negative**
      fixture (tool correctly silent) ⇒ `precision == recall == 0.0`,
      `accuracy == 1.0`; **empty suite** ⇒ `accuracy == 0.0`.
- [ ] `score_run` raises `ObservationMismatchError` for an observation whose
      `case_id` is absent from the suite, and `MissingObservationError` (listing
      the unobserved ids) when a suite case has no observation.
- [ ] `aggregate_benchmark` returns mean accuracy + **population** variance
      (÷N): a fixture of runs `[acc=1.0, acc=0.5]` asserts the exact expected
      mean `0.75` and variance `0.015625`. A case is flaky **iff** its outcome
      differs across runs (identical runs ⇒ empty `flaky_case_ids`, `0.0`
      variance); a single-run input ⇒ `0.0` variance, empty flaky list; runs with
      mismatched `case_id` sets ⇒ `EvalError`.
- [ ] `parse_eval_suite` raises `EvalSuiteError` on malformed input **and on a
      duplicate `case_id`**; `parse_observations` raises `ObservationsError` on
      malformed input (both cover `json.JSONDecodeError`); `dict → parse →
      to_dict` round-trips for suite/result/benchmark.
- [ ] `equip eval <tool>` end-to-end: reads suite + observations, writes
      `.context/equipment-evals/<tool>.result.json` in the pinned shape, and
      stdout contains each misfire's **`case_id` + `EvalOutcome`** (a capsys test
      with 1 FP + 1 FN asserts both ids appear, neither TP/TN id does). A
      **schema contract test** pins the result/benchmark JSON shape.
- [ ] `equip eval` **exit codes** are asserted via rc/capsys: `2` for a missing
      suite file (`EvalSuiteNotFoundError`) and for an **unsafe tool name**
      (`../` / absolute), `1` for a **malformed observations** file, `0` on a
      clean score. A `--run-label` collision without `--force` exits non-zero.
- [ ] `equip benchmark <tool>` aggregates ≥2 `run-*.result.json` files (excluding
      `*.tmp`) into a report with variance + flaky list; **a missing evals dir or
      zero run files ⇒ stderr warning + exit 0 and writes no benchmark file**;
      a labelless `<tool>.result.json` with no `run-*` files warns "re-run with
      `--run-label`".
- [ ] Guard tests prove the LLM judgment stays out of code: an **AST import-scan**
      of `eval/*.py` finds no `subprocess`/network import, **and** `score_run`
      runs with filesystem access monkeypatched off (trigger decisions arrive
      only as in-memory data).
- [ ] The `dummyindex-equip` skill markdown documents the suite JSON schema, how
      to hand-author a suite, and the dispatch → observe → `equip eval` →
      `equip benchmark` → `equip patch` loop; a grep-able test asserts the section
      names all three CLI touchpoints + the blind-judgment step, and warns to use
      synthetic (non-secret) prompts. `tests/test_skills_doc_hygiene.py` stays green.
- [ ] Full suite green (`conventions/testing.md` — the enforced bar is green on
      the 3.10/3.12 matrix, not a `--cov` gate); `.context/features/equip/*`
      reconciled to describe the new eval stage.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `equip`
- `feature-taxonomy`
- `tree-enrich`
- `bootstrap`
- `build-loop`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
