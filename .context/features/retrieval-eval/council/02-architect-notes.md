# Architect notes — Retrieval evaluation

`confidence: INFERRED`

## What I changed

- Separated the frozen correctness gate from the pinned repository experiment;
  both consume production query but accept different gold-answer contracts.
- Retained gate floors, corpus guards, split policy and the 65,536-byte
  nontruncation guard. Made disposable checkout writes and basename false
  positives explicit (`benchmarks/retrieval/run_eval.py:51-118`,
  `benchmarks/retrieval/run_eval.py:163-175`).

## Patterns and decisions

A module-scoped fixture shares one built index
(`tests/eval/test_retrieval_eval.py:59-67`). Fixed regression gates protect a
small stable corpus; pinned rebuilds measure retrieval without council enrichment.
The runner reports metrics rather than enforcing research blinding or quality
thresholds. Historical records remain historical.

## Dependencies and evidence

Upstream: builder/query, local fixtures and Git/network/pinned repos for the
benchmark. Downstream: test failures and printed metrics. This is one-way
observation, not a production feedback import cycle or model-quality eval. Named
runner/gate symbols were checked in map/source. Single-shot reasoning used because
Sequential Thinking MCP is unavailable. No specs/source/logs or measured results
were changed, and no benchmark was run.
