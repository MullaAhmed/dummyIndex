# Agent-facing instructions — spec

confidence: INFERRED

## Intent

Emit the three Claude-facing documents that make `.context/` self-navigable for an AI coding agent. They need no CLI run. The documents are `HOW_TO_USE.md`, a deterministic `architecture/overview.md`, and task `playbooks/*.md`. All generators are pure. No LLM, no I/O beyond returning strings. Output is reproducible and diff-stable (`dummyindex/context/output/instructions.py:1-8`).

## User-visible behavior

**`HOW_TO_USE.md`** is a static, hand-authored template returned verbatim (`instructions.py:23-144`). It tells the agent to read `.context/` before grepping:
- Two layers. The *deterministic backbone* (map, tree, naming, source-docs) refreshes via `rebuild --changed`. The *curated* layer (feature `spec.md`/`plan.md`/`concerns.md`, conventions) updates through read-only `reconcile`, then `/dummyindex --recouncil`, then `reconcile-stamp` (`instructions.py:26`, `:28`).
- A navigation table keyed on `feature_id`, not `id`. It separates `INDEX.json` `*_count` keys from raw `feature.json` lists (`instructions.py:36-50`, `:40`).
- A PageIndex-style "walk the tree, don't grep" procedure. `dummyindex context query` is an optional ranked first cut. Output caps at 16,000 bytes (`instructions.py:52-63`, `:56-57`).
- "The code wins" and the fix path that matches each staleness. The user's explicit instruction overrides a spec or plan (`instructions.py:75-81`).
- Commit policy: everything in `.context/` is committed except `cache/`, which is per-machine and never referenced. The committed-layout table adds `gc/evolution.jsonl`, `gc/evolve/<run>/` and `.context/fleet/run-<id>/` (`instructions.py:89`, `:97-105`).
- A secret-scanner note. `sha256` fields are content fingerprints. Scope the detect-secrets exclusion to `map/` and `source-docs/INDEX.json`, not all of `.context/` (`instructions.py:126-136`).

**`architecture/overview.md`** is derived deterministically from the file and symbol maps plus meta (`instructions.py:215-309`). It holds a Stack block (languages, file and symbol counts) and a top-level layout table. Each row has a heuristic role hint, file count, symbol count and languages (`instructions.py:255`). It lists root files. With a `DocCatalog`, it adds a "Documented architecture" section. That section is labelled **advisory only** and sorts high-confidence first (`instructions.py:281-300`). Role hints come from a fixed dir-name lookup. Unknown dirs render `_unknown_`, not a guessed role (`instructions.py:154-203`, `:332-334`).

**`playbooks/*.md`** are five static recipes selected by id from `_PLAYBOOK_BODIES` (`instructions.py:370-519`): `add-endpoint`, `add-feature`, `add-migration`, `fix-bug`, `refactor`. Each is a numbered procedure. It routes the agent through `map/symbols.json`, `tree.json` and `conventions/naming.md`. It ends by pairing `rebuild --changed` with reconcile when new files appear. `generate_playbook_md` raises `KeyError`, listing available ids, for an unknown id (`instructions.py:525-530`).

The doc-evidence pointers catalogued for this feature (`docs.md`) are MEDIUM/LOW confidence with broken refs. They are historical only and not quoted here.

## Contracts

Public functions and constants (`dummyindex/context/output/instructions.py`):
- `generate_how_to_use_md() -> str` (`:147-148`) returns the static `_HOW_TO_USE` template.
- `generate_architecture_overview_md(repo_root: Path, files_map: FilesMap, symbols_map: SymbolsMap, meta: Meta, *, doc_catalog: Optional[DocCatalog] = None) -> str` (`:215-309`).
- `generate_playbook_md(playbook_id: str) -> str` (`:525-530`) raises `KeyError` for an unknown id.
- `PLAYBOOK_IDS: tuple[str, ...]` is the sorted keys of `_PLAYBOOK_BODIES` (`:522`).
- `write_how_to_use_md(path: Path) -> None` (`:536-537`).
- `write_architecture_overview_md(path, repo_root, files_map, symbols_map, meta, *, doc_catalog=None) -> None` (`:540-555`).
- `write_playbook_md(path: Path, playbook_id: str) -> None` (`:557-558`).

Private helpers: `_atomic_write(path, content)` writes `path.suffix + ".tmp"`, then `replace()` (`:561-565`). It is atomic, so no partial file appears. `_group_files_by_top_level_dir` and `_group_symbols_by_top_level_dir` skip root files (`:312-331`). `_role_hint_for` is a case-insensitive `_DIR_ROLE_HINTS` lookup (`:332-334`). `_select_architecture_docs` matches filename signals or an "architecture" title. It drops externals and sorts by `DOC_CONFIDENCE_ORDER` (`:348-364`).

## Examples

- `generate_playbook_md("add-feature")` returns markdown starting `# Playbook — add a feature`. It cites `map/symbols.json` and `conventions/naming.md` (`test_instructions.py:211`).
- `generate_playbook_md("not-a-real-playbook")` raises `KeyError` (`test_instructions.py:225`).
- `generate_architecture_overview_md(...)` on `src/`, `tests/`, `README.md` includes `# Architecture overview`, `` `src/` ``, "source code", "test suite" and the root `README.md` (`test_instructions.py:114`). A flat repo yields "No subdirectories detected" (`:158`). An unknown dir renders `_unknown_` (`:177`).
- `write_how_to_use_md(path)` leaves no `.tmp` sibling (`test_instructions.py:103`).
- `build_all(...)` writes `HOW_TO_USE.md`, `architecture/overview.md` and one `playbooks/<id>.md` per `PLAYBOOK_IDS`. `INDEX.md` lists them all (`test_instructions.py:242`, `:267`).
- Doc-hygiene guards assert the binding `— via` gate, read-only reconcile wording and the `feature_id`/INDEX.json contract. They reject the known-bad `install --scope user` remedy and a bare `dummyindex --recouncil` verb (`test_skills_doc_hygiene.py:133-211`, `:568-600`). They pin the codebase-scan council doc's ranked-seed contract. It requires `symbolRef` and `evidence`, grounded in `graph-communities.json`, the 120-node/240-edge caps with the 40–80 aim, and `skill.md` wording (`:614-676`). They also check fleet red flags and hardcoded identifiers (`:699`, `:722`).
