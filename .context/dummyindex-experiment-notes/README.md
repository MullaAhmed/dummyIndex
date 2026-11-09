# dummyindex autoresearch experiments (not merged), saved 2026-11-07

Source branches were based on the v0.37.0 release; deleted after saving.
Apply with: git apply <file>.patch   (against v0.37.0 / origin/main at 4f3cf0d)

## query-perf.patch  (dummyindex/context/domains/query.py, 17 commits)
Micro-optimizations: drop exists() pre-checks (rely on OSError), index only symbol
names per feature, estimate_tokens `n or 1`, sum/heapq.nsmallest for top symbols,
_build_match no longer Optional.
RISK: shrink target `max(40, budget // 2)` -> `budget // 2` changes output for small budgets. Review before merging.

## storage-perf.patch  (dummyindex/export/storage.py, 2 commits)
- _plain_path: only build Windows path parser when ":" in relative name
- _shards: prefix built as '"' + family + '"' instead of json.dumps(family)
RISK: only equivalent for family names needing no JSON escaping.

## graph-perf.patch  (graph_query/models.py, verbs.py)
Almost all already in main. Only leftover: GraphRow.to_payload uses a tuple loop
instead of five _put() calls (cosmetic, same behavior).

Commit lists: query-commits.txt, storage-commits.txt
