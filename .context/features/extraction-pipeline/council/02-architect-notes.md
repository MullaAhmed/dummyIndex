# Architect notes — extraction-pipeline

## What I changed
- Replaced the "Where it lives" prose blob lead with a **Bounded context** section first — names what this feature owns (extract → cluster → export, with `pipeline/io/` as an infra adapter) and explicitly excludes the downstream build-feature consumers (`references.py`, networkx assembly) that the draft had buried inside "Key decisions". The draft conflated boundary and consumer.
- Promoted a standalone **Pattern catalogue** — the draft named patterns implicitly inside prose; now each is named, located, and given its load-bearing rationale.
- Added a **Dependencies** section (upstream / downstream / cycles) — wholly absent from the draft. Made the one-way pipeline and "no cycles" explicit, and recorded that pass-2 is internal (doesn't call back into cluster/export).
- Rewrote "Key decisions" → **Decisions** in "decided X because Y" form; split the cache decision to surface the `root`-no-op compat shim as its own promoted decision, and promoted the `generic.py` "extremis" file-size exception (was only a docstring concession) so reviewers don't re-litigate it.
- **Moved `references.py` out of the decisions** into Downstream dependencies (with a note it's correct-against-source but lives in another feature). Cut it as a "key decision" of this context — it isn't one.
- Trimmed line-range citations to declaration lines matching `symbols.json` where they diverged from the draft's body-span numbers; left body spans only where they carry meaning.

## Patterns named
- Two-pass extraction at `pipeline/extract/generic.py:23` + `resolve.py` / `__init__.py:216-242` — pure per-file pass 1 (emits `raw_calls`) feeds global pass 2; the split is what makes pass 1 cacheable.
- Port/adapter over a parametric driver at `pipeline/extract/config.py:13` (port) + `language_configs.py`/`languages/` (adapters) + `generic.py:23` (host) — language variation is data + two injected callables; irregular grammars escape via custom walks.
- Content-addressed cache at `pipeline/io/cache.py:20-40` — `sha256(file-bytes)` key, path-independent.
- Seeded-determinism seams at `analysis/cluster.py:11,42,52,109` + `export/graph.py:40-43` + `__init__.py:276,293` — determinism enforced at named seams, not assumed.
- Error isolation / graceful degradation at `pipeline/extract/__init__.py:202-214` + `pipeline/io/git.py:11-14`.

## Dependencies surfaced
- Upstream: `tree_sitter` (Language API v2, gated by `_check_tree_sitter_version:61`); `pipeline/io/` cache+git; `graspologic` (optional, gates Leiden), `networkx`, `python-louvain`; `pipeline/enums.ConfidenceLevel`.
- Downstream: build feature's networkx assembly + `pipeline/build/references.py:16` (`_derive_textual_references`, helper `_build_matcher:106`); `symbol-graph.json` consumers.
- Cycles: none — extract → cluster → export is one-way; pass-2 of extract is internal.

## Decisions promoted
- decided `file_hash`'s `root` arg is a retained no-op because the cache must survive cwd/mv/path-form differences (was buried in the cache bullet; rationale in docstring at `pipeline/io/cache.py:32-35`).
- decided `_extract_generic` is a sanctioned file-size exception because conventions §4 "extremis" covers it (was only a docstring concession at `pipeline/extract/generic.py:1-13`).
- decided the three determinism seams are deliberate, not emergent (was stated but not framed as a decision; `analysis/cluster.py:11,42,52,109`, `export/graph.py:40-43`).

## Symbol verification
- All cited symbols verified against `.context/map/symbols.json` by name + range: `extract`, `collect_files`, `_extract_generic`, `LanguageConfig`, `_make_id`/`_read_text`/`_find_body`, `_resolve_cross_file_imports`/`_resolve_cross_file_java_imports`, `cluster`/`_partition`/`_split_community`/`_suppress_output`, `to_json`/`_node_community_map`/`_strip_diacritics`, `file_hash`/`cache_dir`/`load_cached`/`save_cached`, `is_git_repo`/`resolve_git_dir`/`submodule_paths`, `_check_tree_sitter_version`.
- `_derive_textual_references` + `_build_matcher` are ABSENT from `symbols.json` but PRESENT in source at the cited lines (`pipeline/build/references.py:16,106` — confirmed by grep). Code wins; they belong to the downstream build feature, so I moved them to Dependencies rather than dropping them. Flagged in the plan.
- Stale doc flagged: `cluster()` docstrings (`analysis/cluster.py:30,64`) still claim Leiden-only / "best quality" while code falls back to Louvain. Left as an Open question; code wins.
