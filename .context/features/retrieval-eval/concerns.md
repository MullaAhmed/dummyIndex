# Correctness-gated retrieval eval — concerns

`confidence: INFERRED`

## Data integrity

- `tests/eval/test_retrieval_eval.py:133-146` — the frozen gate ranks post-budget `result.matches` using production defaults and does not inspect `truncated`. A changed token/byte budget can move this end-to-end gate even when raw scoring order is unchanged. Distinguish output truncation when diagnosing a miss.
- `tests/eval/test_retrieval_eval.py:127-155` — the corpus guard permits growth while hit/MRR floors remain fixed (`tests/eval/test_retrieval_eval.py:46-47`). Adding fixtures changes how many misses a passing percentage tolerates; reassess the documented twelve-positive calibration when changing the corpus.

## Security

- `tests/eval/test_retrieval_eval.py:60-67` — the gate writes only into a fresh pytest copy of `SAMPLE_REPO`. That copy is not a sandbox for other workspaces; no isolation guarantee is claimed.

## Product surface

- **A ranking change breaches an aggregate floor** — the gate reports hit@3/MRR and the threshold. It does not report which missed question/rank caused the breach. Localization still requires inspecting the fixture loop. Citation failures already name the question, expected path and actual citations (`tests/eval/test_retrieval_eval.py:146-150`).
- **Changing fixtures or comparing historical records** — the frozen floors remain 0.90/0.85 and permit corpus growth. Historical baseline prose is not automatically rewritten. Current test constants and actual runs remain authoritative. Historical scores are not fresh measurements (`tests/eval/test_retrieval_eval.py:46-47`, `tests/eval/test_retrieval_eval.py:127`).
