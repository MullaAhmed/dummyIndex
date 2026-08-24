# dummyindex benchmark harness

Head-to-head comparison of two agent configurations on identical tasks:

| Arm | Setup | Question |
|---|---|---|
| `baseline` ("C") | opencode + raw repo checkout, neutral `AGENTS.md` | How does an agent do with its own glob/grep? |
| `context` ("A") | same checkout + **full enriched** `.context/` + `.context/` navigation section appended to the same `AGENTS.md` | Does walking a prebuilt, council-curated index beat blind search — at equal or better accuracy, fewer tokens and tool calls? |

Same model (`opencode/x-preview-f-free`), byte-identical prompts, byte-identical
flags; the only delta is the index plus its navigation instructions.

## Phase 0 — enrichment BEFORE benchmarking (required)

The context arm is only meaningful against a **fully curated** index. An
un-enriched backbone (`community-N` names, null summaries) gives agents an
empty map — measured earlier as strictly worse than grep. Therefore:

1. **Enrich once per `(repo, commit)` in the shared cache clone** — never per
   cell. The driver (`benchmarks/enrich.py`) runs the real council protocol:
   `council-batch --next` → one opencode run per unit (persona procedure
   shipped into `.context/council/procedures/`) → `section-write` /
   `council-log` → `reality-check` + `mark-enriched` per feature.
2. **Separate accounting by design.** Every enrichment call is logged to
   `results/benchmarks/enrichment/runs.jsonl` — a cost ledger that REPORT.md
   renders as *"Amortized index-build cost"* and gates NEVER see.
3. **Resumable:** a completed repo carries a `.bi_bench_enriched` marker;
   re-running skips it. Interrupted enrichment continues from the council
   frontier.
4. **Arm isolation:** context workspaces inherit the enriched index verbatim
   (re-ingest is skipped — never overwrite curated work); baseline workspaces
   have `.context/` stripped after copy so they can't see it.

```bash
# free plan: lists unique (repo, commit) targets and their state
python -m benchmarks enrich --suite both

# paid: full council build (~72 repos across both suites)
DUMMYINDEX_BENCH_ALLOW_PAY=1 python -m benchmarks enrich --suite both --execute \
    [--mode standard] [--cap 4] [--limit 3]
```

Rows recorded during sweeps carry `index_state`
(`backbone` / `enriched`) so mixed-era data stays interpretable, and
`reset-cells` can drop stale-condition rows:

```bash
python -m benchmarks reset-cells --suite repoqa --arm context --index-state backbone
```

## Suites

### 1. RepoQA SNF (`suites/repoqa.py`)

Searching-Needle-Function tasks from the **official RepoQA release**
(`evalplus/repoqa_release`, version `2024-06-23`: 600 needles, 6 languages ×
10 repos × 10 needles). Adaptation: instead of the paper's stuffed 16K-token
context, the agent gets the pinned repo checkout and navigates — that is the
capability under test.

Two protocols (`--protocol`), both graded identically across arms:

| Protocol | Agent output | Grader | Extra deps |
|---|---|---|---|
| `name` (default) | ONLY the function name | case-insensitive substring match (`scoring/snf.py`) — the widely cited simplified rule | none |
| `function` | complete function code | **faithful port of the official evaluator** (`scoring/snf_official.py`): fence sanitization → tree-sitter function extraction → NLTK smoothed-BLEU best-match over every needle in the repo → threshold 0.8 | `nltk` |

Publish which protocol a number came from. The dataset JSON auto-downloads
and caches under `results/benchmarks/cache/repoqa/`; override with
`REPOQA_BENCH_DATA_VERSION` (release tag) or
`REPOQA_BENCH_DATA_OVERRIDE_PATH` (local extracted JSON). No HF `datasets`
needed for this suite.

### 2. SWE-bench Lite subset (`suites/swebench.py`)

Stratified subset of HF `princeton-nlp/SWE-bench_Lite`. Agent edits the repo;
we extract a unified diff vs `base_commit` (`scoring/swebench_patch.py`) and
grade with the **official dockerized harness** via `scoring/swegrade.sh`
(requires `pip install swebench` + docker). We never reimplement grading.
Needs the optional `datasets` package: `uv pip install datasets`.

Install benchmark extras at once: `uv pip install datasets nltk` (or
`pip install -e '.[benchmark]'`).

## Safety gates

Nothing spends money by accident. A paid run requires **both**:

```bash
DUMMYINDEX_BENCH_ALLOW_PAY=1   # environment opt-in (behavior_arms idiom)
--execute                      # explicit CLI flag on run-* commands
```

Without them every command is a dry-run planner. `plan`, `report`, and all
unit tests are always free.

## Contamination controls

- Per-run sandboxed `XDG_CONFIG_HOME`/`XDG_DATA_HOME`: your personal opencode
  config, skills, plugins, MCP servers, and session history cannot reach the
  agent. Only `opencode/auth.json` is copied across for provider auth.
- `--pure` disables external plugins as belt-and-suspenders.
- Repos are cloned once per `(repo, commit)` into a shared cache, then copied
  per arm so both arms see byte-identical trees.
- `AGENTS.md` is written **last**, overwriting anything ingest wrote, so the
  instruction delta is exactly one section (shared-base/single-delta contract,
  `arms.py`). The baseline arm's file is a strict prefix of the context arm's.

## Usage

```bash
python -m benchmarks plan                       # free: print the matrix
python -m benchmarks run-repoqa                 # free: dry-run, prints argv per cell

# real sweep (costs money):
DUMMYINDEX_BENCH_ALLOW_PAY=1 python -m benchmarks run-repoqa --execute \
    --per-cell 2 --repeats 3                    # 120 tasks x 2 arms x 3 reps (name protocol)
DUMMYINDEX_BENCH_ALLOW_PAY=1 python -m benchmarks run-repoqa --execute \
    --protocol function                         # official-BLEU grading variant
DUMMYINDEX_BENCH_ALLOW_PAY=1 python -m benchmarks run-swebench --execute \
    --size 50                                   # 50 instances x 2 arms

bash benchmarks/scoring/swegrade.sh \
    results/benchmarks/swebench/preds-swe-20260823.jsonl swe-20260823

python -m benchmarks report --suite all --out results/benchmarks/REPORT.md \
    [--resolved results/benchmarks/swebench/swe-20260823/resolved.json]
```

Artifacts land in gitignored `results/benchmarks/<suite>/runs.jsonl`
(one row per cell) plus session telemetry inside each row.

## Metrics & gates

Per cell: accuracy / resolve rate, input+output+cache tokens, cost when
reported, tool-call counts (total + per-tool breakdown), wall time. The
report derives mean ± σ, tokens-per-correct-answer, and evaluates the
**pre-registered gates** in `gates.py`:

- Accuracy non-inferiority: context arm ≥ baseline − 0.02 (SNF) / − 0.05 (SWE).
- Tool-call ratio floor: baseline/context mean calls ≥ 1.15× (a hard
  regression fails loudly; the full ≥50% claim stays recorded, not gated,
  on a first measurement).

These thresholds are fixed **before** any paid sweep, per the repo baseline
idiom (`tests/eval/BASELINE.md`): revise only by deliberate re-observation,
never to paper over a regression.

## Layout

```
benchmarks/
├── __main__.py        CLI (enrich / plan / run-* / reset-cells / grade / report)
├── arms.py            Arm enum, AGENTS.md rendering, pinned-clone + workspace prep,
│                      enriched-cache inheritance + baseline .context stripping
├── enrich.py          phase-0 council driver (council-batch loop → opencode units)
├── runner.py          headless opencode driver, pay-gates, per-run sandboxes, JSONL
├── telemetry.py       tolerant parser for `opencode run --format json` streams and exports
├── gates.py           pre-registered acceptance gates
├── report.py          aggregation, dedupe, amortized index-cost section, REPORT.md
├── suites/repoqa.py   official-release loading, protocols, stratified subsets, prompts
├── suites/swebench.py SWE-bench Lite adapter + predictions writer
├── scoring/snf.py     simplified name-substring grader
├── scoring/snf_official.py  faithful port of the official RepoQA evaluator (BLEU)
├── scoring/swebench_patch.py  model-patch extraction (git add -A + diff --cached)
└── scoring/swegrade.sh        official dockerized grading wrapper
tests/benchmarks/      unit tests — offline, deterministic, no LLM calls
```

## Smoke stage (first paid step)

Before the full sweep, validate the telemetry assumptions against reality:

```bash
DUMMYINDEX_BENCH_ALLOW_PAY=1 python -m benchmarks run-repoqa --execute \
    --per-cell 1 --repeats 1    # then trim runs.jsonl to ~5 cells
```

Confirm that `input_tokens`/`output_tokens`/tool-call counts look sane against
`opencode stats` for the same sessions. If opencode changed its event schema,
fix `telemetry.py` against the new capture before running anything larger.
