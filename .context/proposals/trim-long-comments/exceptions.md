# Exceptions — trim-long-comments

Items still over threshold (comment block 5+ lines, docstring 9+ lines) after
the trim, keyed exactly as `comment_scan.py --doc-min 9 --all` prints them. Each
was reported by its unit; the orchestrator compiled the list.

One item has dropped off the list. The `tests/eval/test_retrieval_eval.py`
"Do not lower these" floor block is now 4 lines: the banner pass (`banners.py`)
removed its two decorative `# ----` frame lines. Its four text lines are
byte-identical to base.

| Kind | Path:line | Lines | Reason |
|---|---|---|---|
| doc | dummyindex/context/domains/gc/delete.py:1 | 17 | six-guard delete ladder; safety content (rule 4) |
| doc | dummyindex/context/domains/memory/miner/__init__.py:1 | 16 | keep-list: Apache-2.0 attribution, verbatim |
| doc | dummyindex/context/domains/memory/miner/signatures.py:1 | 11 | keep-list: attribution, verbatim |
| doc | dummyindex/context/domains/reality_check/__init__.py:1 | 37 | keep-list: pipeline contract; every rule kept, false claims corrected |
| doc | dummyindex/installer/link/__init__.py:1 | 13 | package import law + `allowed_symlinks` security invariant |
| doc | dummyindex/installer/link/create.py:402 | 13 | safe-replacement sequence + per-family error isolation |
| doc | dummyindex/installer/link/orchestrate.py:33 | 15 | probe safety (victim tree, dotfiles resolution) + hint choice |
| doc | dummyindex/installer/link/orchestrate.py:92 | 14 | call ordering + three-mode contract |
| doc | dummyindex/pipeline/build/structure.py:1 | 14 | return-shape contract (schema 2.0 node/edge keys) |
| block | tests/cli/test_cli_doc_sync_policy_canary.py:21 | 28 | keep-list: MIT line verbatim + SCOPE + COUPLING HOLE |
| doc | tests/eval/test_retrieval_eval.py:1 | 25 | keep-list: brittleness rationale (cited by conventions/testing.md) |
