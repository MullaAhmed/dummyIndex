# Retrieval correctness gate — spec

`confidence: INFERRED`

## Intent

Keep deterministic retrieval correct on a frozen sample index. The pytest gate
protects known navigation answers. It does not measure model task quality and
does not change production retrieval.

## User-visible behavior

`python -m pytest tests/eval/test_retrieval_eval.py -q -s` builds one temporary
copy of `SAMPLE_REPO` per module and runs three integration checks. The main
gate evaluates positive fixtures with `query(..., top_k=3)`, prints MRR,
hit-rate@3 and mean estimated tokens, and requires hit-rate@3 >= 0.90 and MRR >=
0.85. Mean estimated tokens is recorded rather than gated. The other checks
require the off-topic negative control to return no matches and every positive
question to overlap its expected feature vocabulary
(`tests/eval/test_retrieval_eval.py:46-47`,
`tests/eval/test_retrieval_eval.py:118-179`,
`tests/eval/test_retrieval_eval.py:182-214`,
`tests/eval/test_retrieval_eval.py:216-265`).

## Contracts

- The frozen fixture corpus is a JSON array of `question`,
  `expected_feature_id`, `expected_path`, with one `negative_control` entry.
  The gate requires at least twelve positives and exactly one negative
  (`tests/eval/test_retrieval_eval.py:70-81`, `:127`). Hits require the expected
  feature rank plus its expected path in citations; path matching accepts an
  exact or trailing path segment (`tests/eval/test_retrieval_eval.py:89-109`,
  `:133-150`). Stable expectations concern this frozen index, not live cluster
  IDs after a rebuild.

## Examples

The committed positive fixture `how does make_app build an App instance` targets
`community-0` and `app.py`; the gate checks its rank and cited path. The
off-topic Kubernetes fixture must return no matches. `tests/eval/BASELINE.md` is
historical rationale for the gate floors, not a new run. These metrics do not
establish agent-quality improvement. The model-dependent behavior gate has a
separate scope and evidence.
