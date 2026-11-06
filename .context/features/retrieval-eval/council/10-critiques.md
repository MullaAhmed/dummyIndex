## Data integrity

- `benchmarks/retrieval/run_eval.py:101-117` — gold matching also accepts basenames, so a same-named file in another directory can count as a correct answer. Benchmark hit/MRR results therefore do not establish exact-path correctness; the frozen gate separately checks expected citation paths.
- `tests/eval/test_retrieval_eval.py:133-146` — the frozen gate ranks post-budget `result.matches` using production defaults and does not inspect `truncated`. A changed token/byte budget can move this end-to-end gate even when raw scoring order is unchanged; distinguish output truncation when diagnosing a miss. The pinned benchmark's new truncation rejection avoids that ambiguity for its own runs (`benchmarks/retrieval/run_eval.py:163-175`).
- `tests/eval/test_retrieval_eval.py:127-155` — the corpus guard permits growth while hit/MRR floors remain fixed (`tests/eval/test_retrieval_eval.py:46-47`). Adding fixtures changes how many misses a passing percentage tolerates; reassess the documented twelve-positive calibration when changing the corpus.

## Security

- `tests/eval/test_retrieval_eval.py:60-67`, `benchmarks/retrieval/run_eval.py:27-88` — The frozen gate writes into a fresh pytest copy; the added benchmark has a different trust surface and starts Git/Python with networked pinned checkouts. Fixed repository URLs/SHAs and argument arrays avoid moving-branch selection and shell interpolation, but are not a sandbox for the checked-out workspace. The prior feature-wide no-network/no-subprocess verdict no longer applies.
- `benchmarks/retrieval/run_eval.py:51-88` — A reused or linked benchmark destination containing `.git` is checked out and its context force-rebuilt; a mistaken work directory can therefore alter an owner checkout. The runner does not prove that an existing destination is a disposable benchmark clone. Mitigation is a fresh owner-controlled disposable work directory; this is an operator boundary, not an enforced path/isolation guarantee.

## Product surface

- **A ranking change breaches an aggregate floor** — the gate reports hit@3/MRR
  and the threshold but does not report which missed question/rank caused the
  breach — localization still requires inspecting the fixture loop. Citation
  failures already name the question, expected path and actual citations, and
  the finalized plan now documents that separate contract
  (`tests/eval/test_retrieval_eval.py:133-172`).
- **Running the pinned benchmark for the first time** — the runner clones
  repository histories, checks out pinned commits and force-rebuilds each
  index; choosing a question split does not avoid repository/index setup — use
  a disposable work directory and account for network/build cost. The benchmark
  is separate from the small frozen pytest gate
  (`benchmarks/retrieval/run_eval.py:51-88`,
  `benchmarks/retrieval/run_eval.py:153-163`).
- **Reading a clean benchmark exit as a quality approval** — the runner prints
  hit@1/hit@3/MRR without enforcing a quality floor, and basename gold matching
  can accept the wrong same-named file — successful execution is not a general
  retrieval or agent-quality guarantee. The integrated runner correctly rejects
  truncated answers before scoring; silently shortened top-ten results are no
  longer treated as complete evidence
  (`benchmarks/retrieval/run_eval.py:110-118`,
  `benchmarks/retrieval/run_eval.py:163-184`).
- **Changing fixtures or comparing historical records** — the frozen floors
  remain 0.90/0.85 and permit corpus growth; historical baseline/result prose is
  not automatically rewritten — current test constants and actual runs remain
  authoritative, and historical scores are not fresh integration measurements
  (`tests/eval/test_retrieval_eval.py:40-47`,
  `tests/eval/test_retrieval_eval.py:125-127`).
