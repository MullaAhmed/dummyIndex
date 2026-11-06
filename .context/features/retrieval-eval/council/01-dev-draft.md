# Retrieval evaluation — plan

`confidence: INFERRED`

## Where it lives

The existing correctness gate stays under `tests/eval/`: `test_retrieval_eval.py`
contains the module-scoped index fixture, metrics gate, negative control and
vocabulary check; `retrieval_fixtures.json` supplies answers; `BASELINE.md`
preserves historical threshold rationale
(`tests/eval/test_retrieval_eval.py:46-81`, `:117-265`).

The feature also owns `benchmarks/retrieval/run_eval.py`, its three question JSON
files and `RESULTS.md`. The runner consumes the production `query` API; it does
not introduce a second scorer. Production query behavior remains owned by
`context-query` (`benchmarks/retrieval/run_eval.py:134-175`).

## Architecture in three sentences

The pytest lane builds a frozen sample index once, evaluates authored expected
feature IDs and citation paths, and applies fixed hit-rate/MRR floors plus
non-vacuity guards. The benchmark lane checks out pinned repositories into a
separate work directory, rebuilds only deterministic indexes, and scores a gold
file's first matching feature among the top ten. Both lanes observe the same
public retrieval API, while the benchmark explicitly rejects truncated answers
before aggregating metrics.

## Data and decisions

The frozen corpus contains twelve positives and one negative; the code asserts
at least twelve positives and exactly one negative. Correctness uses rank and
expected citation paths, while estimated token cost remains a recorded signal.
The existing floors stay `T_HIT=0.90` and `T_MRR=0.85`; changing corpus/build
behavior requires deliberate re-observation rather than lowering thresholds to
hide a regression (`tests/eval/test_retrieval_eval.py:40-81`, `:125-172`).

Benchmark question files map repository names to ordered `[question, golds]`
rows. The default file has eighteen questions each for requests, Flask and
dummyindex; the later files have seven each across three and four repos.
Development/holdout is determined by even/odd position within each repo;
`--split all` bypasses that alternating assignment
(`benchmarks/retrieval/run_eval.py:138-163`). Full path, basename and directory
gold matching remain explicit benchmark policy, not the frozen gate's citation
check (`benchmarks/retrieval/run_eval.py:91-118`).

Pinned commits and `context init --force --depth standard` keep the benchmark
about deterministic retrieval, not council enrichment. Index rebuilding occurs
inside the benchmark checkout and can replace its existing context, so it needs
a disposable work directory (`benchmarks/retrieval/run_eval.py:27-88`).

The integration supplies `max_bytes=65_536` alongside `top_k=10` and
`budget_tokens=100000`, then fails if the result is truncated. Increasing the
token estimate alone cannot bypass production's byte ceiling. This preserves
complete top-ten evaluation rather than silently treating byte-dropped matches
as misses (`benchmarks/retrieval/run_eval.py:163-175`).

## Verification and open questions

The pytest gate remains the default correctness check; the networked benchmark
is an explicitly invoked experiment and has no success threshold beyond correct
execution. Historical `RESULTS.md` documents selection reuse and small validation
sets; these records are not regenerated or promoted into new release claims by
integration. `BASELINE.md` remains historical rationale, with authoritative
current floors read from the test constants.

Basename matching can accept identically named files in different directories,
and small authored corpora do not establish generalization or model task gains.
The benchmark reports such retrieval metrics separately from the sibling
model-dependent behavior gate. No new measurements or broader quality guarantee
is added here.
