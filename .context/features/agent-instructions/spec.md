# Agent-facing instructions — spec

confidence: INFERRED

## Intent

Emit the three Claude-facing documents that make a `.context/` index self-navigable for an AI coding agent without running the CLI: a `HOW_TO_USE.md` navigation guide, a deterministic `architecture/overview.md`, and a fixed set of task `playbooks/*.md`. All generators are pure — no LLM, no I/O beyond returning strings — so the output is reproducible and diff-stable (`dummyindex/context/output/instructions.py:1-8`).

## User-visible behavior

**`HOW_TO_USE.md`** — a static, hand-authored template returned verbatim (`instructions.py:24-113`). It tells the agent to read `.context/` before grepping, via:
- A two-layer model: the *deterministic backbone* (map/tree/naming/source-docs) refreshed by `rebuild --changed`, vs. the *curated* layer (feature `spec.md`/`plan.md`/`concerns.md`, conventions) updated through the read-only `reconcile` → place/enrich → `reconcile-stamp` procedure (`instructions.py:27`, `:80`, `:106`).
- A navigation table mapping questions → index files, keyed on `feature_id` (not `id`), distinguishing `INDEX.json` `*_count` summary keys from raw `feature.json` lists (`instructions.py:33-46`).
- A PageIndex-style "walk the tree, don't grep" retrieval procedure, with `dummyindex context query` as an optional ranked first cut (`instructions.py:48-59`).
- "When the index is wrong, the code wins" + which fix path matches which staleness; "your explicit instruction overrides a spec/plan" (`instructions.py:75-81`).
- Commit policy (everything but `cache/` committed; heavy artefacts marked `linguist-generated` in `.gitattributes`) and a secret-scanner note (the `sha256` fields are content fingerprints, scope the detect-secrets exclusion to `map/` + `source-docs/INDEX.json`, not all of `.context/`) (`instructions.py:87-102`).

**`architecture/overview.md`** — derived deterministically from the file/symbol maps + meta (`instructions.py:180-277`): a Stack block (languages/file/symbol counts), a Top-level layout table (one row per top-level dir with a heuristic role hint, file count, symbol count, languages), a Repo-root files list, and — when a `DocCatalog` is supplied — a "Documented architecture" pointer section listing checked-in arch docs sorted high-confidence-first and labelled **advisory only**. Role hints come from a fixed dir-name lookup; unknown dirs render `_unknown_` (`instructions.py:119-168`, `:300-301`).

**`playbooks/*.md`** — five static recipes selected by id from `_PLAYBOOK_BODIES`: `add-endpoint`, `add-feature`, `add-migration`, `fix-bug`, `refactor` (`instructions.py:338-490`). Each is a numbered procedure that routes the agent through `map/symbols.json`/`tree.json`/`conventions/naming.md` and ends by pairing `rebuild --changed` with the reconcile procedure when new files are added. `generate_playbook_md` raises `KeyError` (listing available ids) for an unknown id (`instructions.py:493-499`).

The doc-evidence pointers catalogued for this feature (`docs.md`) are MEDIUM/LOW confidence with broken refs — historical only, not quoted here.

## Contracts

Public functions / constants (`dummyindex/context/output/instructions.py`):
- `generate_how_to_use_md() -> str` (`:112-113`) — returns the static `_HOW_TO_USE` template (`:24-109`).
- `generate_architecture_overview_md(repo_root: Path, files_map: FilesMap, symbols_map: SymbolsMap, meta: Meta, *, doc_catalog: Optional[DocCatalog] = None) -> str` (`:180-277`).
- `generate_playbook_md(playbook_id: str) -> str` (`:493-499`) — raises `KeyError` for unknown id.
- `PLAYBOOK_IDS: tuple[str, ...]` = sorted keys of `_PLAYBOOK_BODIES` (`:490`).
- `write_how_to_use_md(path: Path) -> None` (`:505-506`).
- `write_architecture_overview_md(path, repo_root, files_map, symbols_map, meta, *, doc_catalog=None) -> None` (`:509-523`).
- `write_playbook_md(path: Path, playbook_id: str) -> None` (`:526-527`).

Private helpers: `_atomic_write(path, content)` writes to `path.suffix + ".tmp"` then `replace()`s (atomic, no partial file) (`:530-534`); `_group_files_by_top_level_dir` / `_group_symbols_by_top_level_dir` skip root files (`:280-297`); `_role_hint_for` is a case-insensitive `_DIR_ROLE_HINTS` lookup (`:300-301`); `_select_architecture_docs` matches arch filename signals or an "architecture" title, drops externals, sorts by `DOC_CONFIDENCE_ORDER` (`:316-332`).

## Examples

- `generate_playbook_md("add-feature")` → markdown beginning `# Playbook — add a feature`, citing `map/symbols.json` and `conventions/naming.md` (`test_instructions.py:191-196`).
- `generate_playbook_md("not-a-real-playbook")` → `KeyError` (`test_instructions.py:198-201`).
- `generate_architecture_overview_md(...)` on a repo with `src/`, `tests/`, `README.md` → includes `# Architecture overview`, ``` `src/` ```, role "source code", "test suite", and the root `README.md` (`test_instructions.py:107-138`); a flat repo yields "No subdirectories detected" (`:140-155`); an unrecognized dir renders `_unknown_` (`:157-171`).
- `write_how_to_use_md(path)` leaves no `.tmp` sibling (`test_instructions.py:97-101`).
- `build_all(...)` writes `HOW_TO_USE.md`, `architecture/overview.md`, and one `playbooks/<id>.md` per `PLAYBOOK_IDS`, all listed in `INDEX.md` (`test_instructions.py:215-237`).
- Doc-hygiene guards assert the generated prose carries the binding `— via` gate, read-only reconcile wording, the `feature_id`/INDEX.json field contract, and never the known-bad `install --scope user` remedy or phantom `dummyindex --recouncil` CLI verb (`test_skills_doc_hygiene.py:42-80`).
