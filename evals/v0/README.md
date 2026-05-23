# dummyIndex v0 Eval Harness

The point of v0 is to **prove that the content of `.context/` reduces tool calls and tokens without quality regression**. This directory is the scaffold for that measurement.

## Methodology

Per `V0_SCOPE.md §7`:

For each task in `tasks.yaml`:
- **Baseline run:** Claude Code on the repo *without* `.context/` and without the CLAUDE.md managed block.
- **Treatment run:** Claude Code on the repo *with* `.context/` and the managed block (i.e. after `dummyindex context init`).

Same prompt, same model, same temperature. Run each task 3× per condition.

## Pass criteria

The v0 design is validated if, on the task corpus:

| Metric | Bar |
|---|---|
| Tool calls (Read / Glob / Grep / Edit) | ≥30% reduction in treatment vs baseline |
| Quality | No regression (treatment fail rate ≤ baseline) |
| Tokens (input + output) | ≥15% reduction |

If these don't hold, **don't build v0.1** until the v0 content is fixed.

## Files in this directory

| File | Purpose |
|---|---|
| `tasks.yaml` | The task corpus — 5–10 representative coding tasks. |
| `run_eval.py` | The harness scaffold. Currently runs in **smoke mode** (mock LLM) so the harness itself is exercisable in CI. Real model invocation is wired in by replacing `run_one(...)` — see comments in the file. |
| `results/` | Created at runtime; one JSON per (task, condition, repetition). Gitignored. |
| `report.md` | The aggregated comparison report (generated). Gitignored. |

## Running the smoke mode

```bash
uv run python evals/v0/run_eval.py --smoke
```

This validates the harness's plumbing — task parsing, repetition, result collation — without spending money on real model calls.

## Wiring a real model

Replace `run_one()` in `run_eval.py` with a function that:

1. Spawns a Claude Code session in the target repo (subprocess against `claude` CLI, or via the Anthropic SDK).
2. Sends the task description as the first user message.
3. Waits for the session to complete (configurable timeout).
4. Returns a `RunRecord` with: tool call list, token totals, the final diff or response, and a `passed: bool` set by the human judge (or a programmatic check).

The harness will run baseline and treatment alternately to avoid ordering effects.

## Adding new tasks

Each task in `tasks.yaml` needs:

```yaml
- id: descriptive-slug
  prompt: |
    Free-form task description (what a real user would say).
  difficulty: easy | medium | hard
  acceptance:
    - "Files changed include app/x.py"
    - "Tests in tests/x_test.py pass"
```

`acceptance` is consulted by the human judge; v0 doesn't auto-check.

## Anti-cheating notes

- Eval runs are non-interactive (no human steering).
- Treatment and baseline alternate by task to avoid ordering effects.
- The dummyindex maintainer (whoever reviews PR 6) is the human judge — not the author of v0.
