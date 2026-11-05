# Index lifecycle — limits

Source-stale labels request semantic review; deterministic refresh cannot write
new semantic summaries. `coverage.json` distinguishes file navigation from
extracted symbols and records exclusions with reasons. It does not prove that
every parser understood every construct.

Graph files are bounded; graph consumers currently reconstruct the graph in RAM.
Distinct emitted definitions survive source-ID collisions. Affected IDs receive
suffixes when another collision enters the scan; unique legacy IDs stay compatible.
Unknown call targets remain explicit candidate sets. The existing undirected graph
still aggregates repeated edge observations, and parser coverage is not a proof
that every possible AST construct was extracted.
Missing or corrupt curated tree data is preserved through a failed refresh,
rather than silently replaced with an empty tree.
