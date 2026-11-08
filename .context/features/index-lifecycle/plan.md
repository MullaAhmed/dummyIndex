# Index lifecycle — implementation

`dummyindex/context/build/runner.py` builds maps, tree, summaries, coverage and
graph artifacts. `scope.py` keeps scanning inside the chosen output root and
remembers the source subtree for later refreshes.

`enriched_refresh.py` refreshes curated indexes without replacing their feature
taxonomy or authored specifications. `navigation_refresh.py` carries matching
annotations, updates topology and flags summaries whose source hashes changed.
Mechanical summary sections update while other sections, including repeated
headings, survive.

`reconcile.py` reports ownership gaps and missing source. An unavailable commit
anchor requires full scoped inventory and explicit re-baselining after review.
`tests/context/build/test_index_repair.py` covers these repair boundaries.
