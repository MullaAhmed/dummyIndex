# dummyIndex v2 — v0 Scope

**Status:** Buildable slice. The rest of `BRIEF.md` is the north-star; this doc is what we ship first.
**Date:** 2026-05-24
**Predecessor doc:** `BRIEF.md` (locked design)

---

## 1. v0 goal

A `dummyindex` CLI that drops a `.context/` folder into any repo and writes a managed CLAUDE.md block telling Claude to read it. **No MCP, no LLM-powered routing, no templates yet.** The agent uses `.context/` via direct file reads / `@import`, and we measure whether that alone moves the needle.

If v0 doesn't move the needle, the whole brief is wrong and we save ourselves from building Phases 3–6. If it does, we proceed with confidence.

---

## 2. What's in v0

| Capability | In v0? |
|---|---|
| Detect & classify files (reuse `pipeline.detect`) | ✅ |
| AST extraction (reuse `pipeline.extract`) | ✅ |
| Hierarchical `.context/tree.json` (deterministic, no LLM) | ✅ |
| `.context/map/files.json` + `symbols.json` | ✅ |
| `.context/conventions/naming.md` (statistical inference, no LLM) | ✅ |
| `.context/INDEX.md` (hand-readable TOC) | ✅ |
| CLAUDE.md managed-block writer (idempotent) | ✅ |
| `dummyindex init`, `dummyindex rebuild`, `dummyindex rebuild --changed`, `dummyindex bootstrap` | ✅ |
| Incremental rebuild via SHA-256 cache | ✅ |
| `meta.json` schema + version | ✅ |
| Schema validation for all JSON outputs | ✅ |
| Eval harness (with vs without `.context/`) | ✅ |

## 3. What's NOT in v0 (deferred)

| Capability | Lands in |
|---|---|
| LLM-generated node summaries (L0 abstracts beyond docstrings) | v0.1 |
| Interactive model + budget chooser | v0.1 |
| MCP server (`walk`, `expand`, `open`, etc.) | v0.1 |
| Personalized PageRank ranking | v0.1 |
| `route()` and decision-point tools | v0.2 |
| Capabilities inventory (`.context/capabilities/`) | v0.2 |
| Operation templates (`.context/templates/`) | v0.3 |
| Flow + feature hypergraphs (`.context/flows/`, `features/`) | v0.4 |
| Audit subsystem (`.context/audit/`) | v0.4 |
| `--watch` file watching | v0.5 |
| Session-learning hook | v0.5 |
| API contract / DB schema / flag inventory / boundary linter | v0.6+ |

In v0, the agent reads `.context/` via direct file reads or `@import` lines in CLAUDE.md. That's deliberately the simplest possible integration so we can measure whether the *content* of `.context/` helps, before adding MCP infrastructure.

---

## 4. End state — what v0 produces

Running `dummyindex init` on this repo (dummyindex) produces:

```
.context/
├── INDEX.md                    # Hand-readable TOC of this folder
├── PROJECT.md                  # 1-page project summary (deterministic: pulled from README + pyproject)
├── tree.json                   # Hierarchical reasoning tree (deterministic, no LLM summaries yet)
├── tree.schema.json
├── conventions/
│   ├── naming.md               # Statistically-derived naming rules
│   └── naming.json
├── map/
│   ├── files.json              # Path → role, size, language, summary (docstring if any)
│   ├── files.schema.json
│   ├── symbols.json            # All classes/fns/components/consts with path:line, kind, docstring
│   └── symbols.schema.json
├── cache/                      # gitignored
└── meta.json                   # Version, last run, file fingerprints, config
```

And appends to `CLAUDE.md`:

```markdown
<!-- dummyindex:begin (managed — do not hand-edit; regenerate with `dummyindex bootstrap`) -->
# dummyIndex — Context Engine (v0)

Before grepping or reading files for non-trivial requests, consult:

1. `.context/INDEX.md` — folder map and how to navigate
2. `.context/tree.json` — hierarchical structure of the codebase (don't load wholesale; lookup by node_id)
3. `.context/map/symbols.json` — every class / function / component / constant with path:line
4. `.context/conventions/naming.md` — derived naming rules; honor them in new code

If the index disagrees with the code, the code wins — note discrepancies and re-run `dummyindex rebuild --changed`.

This is dummyIndex v0. Future versions add MCP-driven routing — see BRIEF.md.
<!-- dummyindex:end -->
```

---

## 5. Acceptance criteria (when is v0 done?)

Done means **all** of:

1. `dummyindex init` runs clean on this repo (dummyindex) and produces every file listed in §4.
2. `dummyindex init` runs clean on a separately-tested fixture: a small mixed Python + TypeScript repo we maintain in `tests/fixtures/sample_repo/`.
3. `dummyindex rebuild --changed` only re-processes files whose SHA-256 changed since last run, verified with timing.
4. Every JSON output validates against its `.schema.json`.
5. CLAUDE.md managed-block writer is idempotent: running `dummyindex bootstrap` twice produces a single block; running it after the user added other content to CLAUDE.md leaves their content intact.
6. CLAUDE.md managed-block writer correctly handles: no existing CLAUDE.md, existing CLAUDE.md without our block, existing CLAUDE.md with our block (regenerate in place), existing CLAUDE.md with conflicting content (don't overwrite, surface error).
7. Conventions inference produces sensible output on dummyindex (manual spot-check: are the rules accurate?) and on the sample fixture (assertion-driven).
8. Eval harness (see §7) runs to completion and produces a comparison report.

---

## 6. PR-by-PR plan

Roughly six PRs, each shippable and reviewable independently. Each PR ends green: build passes, tests pass, no new lint errors.

### PR 1 — Package skeleton + CLI + schemas

**New files:**
- `dummyindex/context/__init__.py`
- `dummyindex/context/cli.py` (subcommand handlers)
- `dummyindex/context/meta.py` (read/write `meta.json` with schema versioning)
- `dummyindex/context/schemas/meta.schema.json`
- `dummyindex/context/schemas/tree.schema.json`
- `dummyindex/context/schemas/files.schema.json`
- `dummyindex/context/schemas/symbols.schema.json`
- `tests/context/test_cli.py`
- `tests/context/test_meta.py`

**Wired to existing CLI:** new subcommands `dummyindex init`, `dummyindex rebuild`, `dummyindex bootstrap` (stubs that error "not implemented yet" if the dependent PRs aren't merged).

**Acceptance:** `dummyindex init --help` works; `meta.py` round-trips a `meta.json` file against its schema.

### PR 2 — Files & symbols map

**New files:**
- `dummyindex/context/maps.py` (assembles `files.json` and `symbols.json` from pipeline.detect + pipeline.extract outputs)
- `tests/context/test_maps.py`
- `tests/fixtures/sample_repo/` (small mixed Python + TS repo, ~10 files)

**Reused:** `pipeline.detect.detect()` and `pipeline.extract.extract()` — no changes to those modules. Wire their outputs into our writers.

**Acceptance:** Running on the sample fixture produces `files.json` with every source file listed, and `symbols.json` with every top-level class/function. JSON validates against schemas. Sub-second runtime on the fixture.

### PR 3 — Hierarchical tree

**New files:**
- `dummyindex/context/tree.py` (builds `tree.json` PageIndex-style from pipeline.structure output, applying the AST-driven chunking heuristic from BRIEF §5)
- `tests/context/test_tree.py`
- `tests/context/golden/tree.json` (golden file for the sample fixture)

**Reused:** `pipeline.structure.build_structure_graph()` — its output is already a folder→file→class→function hierarchy. We reshape it into PageIndex node objects with `node_id`, `kind`, `title`, `abstract` (deterministic from name + docstring), `overview_ref` (file:lines), `children`. **No LLM summaries in v0** — `abstract` is the docstring's first sentence if present, else a name-based stub ("class PaymentRepo").

**Acceptance:** Golden-file match on the sample fixture. On dummyindex itself, the tree has every top-level module as L1, every file as L2, every class/top-level function as L3, methods as L4.

### PR 4 — Convention learner v1 (naming)

**New files:**
- `dummyindex/context/conventions.py` (derives naming rules from `symbols.json` + `files.json` using statistical inference: per directory, per symbol kind, dominant casing + extension + path prefix; threshold ≥80% of population)
- `tests/context/test_conventions.py`

**No LLM in v0.** Pure Python + regex + frequency analysis. Output:

```markdown
# Naming conventions (derived 2026-05-24)

## Python source files
- 100% of files under `dummyindex/` use `snake_case.py` (evidence: 38/38 files)
- 97% of classes use `PascalCase` (evidence: 124/127 classes; exceptions: ...)
- 99% of functions use `snake_case` (evidence: 412/417 functions; exceptions: ...)

## TypeScript source files
- ...
```

**Acceptance:** Running on dummyindex produces a markdown file whose rules can be manually verified against the code. Test on the sample fixture asserts specific expected rules.

### PR 5 — CLAUDE.md managed block + INDEX.md + PROJECT.md

**New files:**
- `dummyindex/context/bootstrap.py` (managed-block writer with the idempotent semantics from §5.5-§5.6 above)
- `dummyindex/context/docs.py` (INDEX.md + PROJECT.md generators)
- `tests/context/test_bootstrap.py` (every case from §5.6)

**Acceptance:** Every case in §5.6 has a passing test. INDEX.md lists every file dummyIndex wrote with a one-line description. PROJECT.md extracts mission/description/scripts from `pyproject.toml` + `README.md` deterministically (no LLM).

### PR 6 — Incremental rebuild + eval harness

**New files:**
- `dummyindex/context/incremental.py` (uses pipeline.cache.py to skip unchanged files; updates the affected nodes in `tree.json` without re-reading the whole repo)
- `evals/v0/run_eval.py` (eval harness — see §7)
- `evals/v0/tasks.yaml` (5–10 representative task descriptions)
- `evals/v0/README.md` (how to run and interpret)
- `tests/context/test_incremental.py`

**Acceptance:** On a 2nd `dummyindex rebuild` with no file changes, ≥95% of files are skipped (verified via timing log). On a 2nd rebuild with one file edited, only that file (+ any files referencing its symbols) is reprocessed. Eval harness runs and produces a report.

---

## 7. Eval methodology

This is what proves or disproves v0's value. The eval is the gate to v0.1.

### 7.1 Task corpus

`evals/v0/tasks.yaml` — 5–10 representative coding tasks on the dummyindex repo and the sample fixture. Examples:

- "Add a new flow detector for scheduled jobs to `analysis/flows.py`"
- "Find and fix the bug where SVG export skips hyperedges"
- "Refactor `pipeline/extract.py` to extract Rust support into its own module"
- "Add a `--max-depth` flag to the tree builder"
- "Write a test for the cache invalidation behavior"

Each task has: a description, an expected reference outcome (files touched), and difficulty tier.

### 7.2 Runs

For each task:
- **Baseline run:** Claude Code on the repo *without* `.context/` and without the CLAUDE.md managed block.
- **Treatment run:** Claude Code on the repo *with* `.context/` and the managed block.

Same prompt, same model, same temperature. Run each task 3× per condition to control for variance.

### 7.3 Metrics

| Metric | How measured |
|---|---|
| Tool calls per task | Count `Read` / `Bash grep` / `Glob` / Edit / Write calls from the transcript. |
| Tokens consumed | Sum of input + output tokens per run (from the API response). |
| Task success | Did the run produce a result that passes the task's acceptance criteria? Binary, human-judged. |
| Quality | Code-review pass / fail on the produced diff (human-judged from a rubric). |
| Wall-clock time | Start of run → final response. |

### 7.4 Pass criteria for v0

v0 is a success if, on the task corpus:

- **Tool calls: ≥30% reduction** (lower bar than the brief's ≥50% — v0 has no MCP, only passive context)
- **Quality: no regression** (treatment fail rate ≤ baseline fail rate, within statistical noise on n=15–30 runs)
- **Tokens: ≥15% reduction** (loose bar; the real win is tool calls)

If we don't hit these, we revisit either the `.context/` content or the CLAUDE.md directive language before scaling up. We don't build v0.1 on a v0 that didn't move the needle.

### 7.5 Anti-cheating notes

- Eval runs are non-interactive (no human steering).
- Treatment and baseline runs alternate by task to avoid ordering effects.
- The dummyindex maintainer (whoever reviews PR 6) is the human judge for quality and task success — not the author of v0.

---

## 8. Risks for v0

| Risk | Mitigation |
|---|---|
| Claude ignores CLAUDE.md directive on small tasks | Acknowledged in brief §8.2; eval will show the floor. If compliance is ~30% on small tasks, the directive language needs work, not the index. |
| Deterministic-only summaries (no LLM in v0) are too thin to help | Possible. If eval fails, fast-track v0.1's LLM summaries before declaring the design wrong. |
| Sample fixture is too small to detect noise | Mitigate by also running on dummyindex itself + at least one external fixture (we'll pick something open-source, ~5k LOC). |
| `pipeline.structure` output shape doesn't quite fit PageIndex tree | Reshape in `tree.py`; if structural changes to dummyindex's pipeline are needed, they go in their own PR before PR 3. |
| Incremental rebuild has cache-invalidation bugs | Already a problem domain in pipeline.cache.py; we'd inherit any existing bugs. PR 6 includes stress tests against a fixture of churn-heavy edits. |

---

## 9. Timeline (rough)

Not committed; depends on review cycles and how much pipeline.structure needs adapting.

- PR 1: 1 day
- PR 2: 1–2 days
- PR 3: 2–3 days (the chunking heuristic edge cases are where time goes)
- PR 4: 2 days
- PR 5: 1 day
- PR 6: 3–4 days (eval harness setup + initial run)

**Total v0:** ~2 working weeks if reviews land same-day, longer with normal review latency. Eval results come at the end of PR 6 — that's the v0 verdict.

---

## 10. Decisions still needed before PR 1

These were deferred from BRIEF §16:

1. **Languages, v0.** I'd start with Python + TypeScript only — covers ~80% of agent-coded projects and limits the surface area of the chunking heuristic. dummyindex's full 25-language support stays available; v0 just doesn't *test* against the others. Confirm or override.
2. **Sample fixture choice.** Pick (or build) the 5k-LOC external open-source repo for the eval. Suggest a small framework or CLI tool; needs to span Python + TS to exercise both. Want to suggest one or have me pick?
3. **Eval task corpus.** I sketched 5 task templates in §7.1; the corpus needs 5–10 concrete tasks tied to actual files. Worth a 30-minute pairing session or want me to draft and send for review?

These don't block locking the v0 scope — they block PR 1.
