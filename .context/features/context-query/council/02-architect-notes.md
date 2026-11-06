# Architect notes — Context retrieval query

`confidence: INFERRED`

## What I changed

- Kept all scoring constants, IDF/size/top-five policies and output limits;
  reorganized them around the read-only boundary and three pipeline steps.
- Distinguished one-query reuse from persistent caching and made optional-read
  fallback narrower than arbitrary schema recovery. Kept canonical feature paths
  separate from display metadata (`dummyindex/context/domains/query.py:313-358`,
  `dummyindex/context/domains/query.py:576-720`).

## Patterns and decisions

Weighted ranking lives at `dummyindex/context/domains/query.py:428-573`; complete
record bounding at `dummyindex/context/domains/query.py:406-425`. Retaining
citations while shrinking excerpts and dropping whole matches protects complete
formats at the cost of result count. No model/embedding service or graph-storage
reader was invented on this path.

## Dependencies and evidence

Upstream: feature metadata and one parsed symbol map. Downstream: CLI, host
workflows and eval; production does not depend on its evaluator. Named symbols
were spot-checked in the map and source. Single-shot reasoning used because
Sequential Thinking MCP is unavailable. Specs/source and logs were unchanged;
historical benchmark scores were not promoted into fresh release evidence.
