# Spec — Move all context code into dummyindex/context/

## Intent

The earlier split proposal made `dummyindex/evolve/` and `dummyindex/shared/`.
It also decided "context modules do not move" (its spec, Layers section).
So `dummyindex/` still has 9 context packages next to `context/`.

This proposal finishes the job. All context code goes under `dummyindex/context/`.
The user fixed the layout. It is not open for discussion.
Readers: the agents that run the move waves, and the Manager that orders them.

## Target tree

```
dummyindex/
  __init__.py  __main__.py
  skills/                      (no move)
  evolve/                      (no move)
  context/
    build/ domains/ output/ schemas/      (no move)
    cli/ shared/ pipeline/ analysis/ export/ usage/ installer/   (moved in)
    versioning.py  codex_guidance.py                                (moved in)
tests/
  evolve/  test_*.py  conftest.py  paths.py                         (no move)
  context/
    cli/ shared/ pipeline/ analysis/ export/ usage/                 (moved in)
```

`tests/installer/` does not exist. Installer tests stay at the root (`tests/test_install*.py`).

## Contracts

### C1 — Move rules (reuse of the earlier proposal, C3)

1. Move only. No behavior change. No reformat. Only the import-sort that `ruff check .` demands.
2. No shim, no re-export at an old path. Update every importer.
3. Keep file names. `git mv` keeps history.
4. `pyproject.toml` stays the same. `include = ["dummyindex*"]` finds all packages. `package-data` has only `skills/*` and `context/schemas/*.json`.
5. Hook and installer strings name CLI commands and skills, not module paths. They stay.
6. `.context/` is not edited by hand. The close-out (`rebuild --changed`, reconcile, re-anchor) refreshes it. `rebuild` without `--changed`, and `--full`, are forbidden: they destroy the curated index.
7. Evolve code digests change (`gate_code_sha256`, `promotion_code_sha256`, snapshot `controller`). No test pins them. The last `gc/evolution.jsonl` record is a finished harvest. No evolve run is open.

### C2 — Rewrite table

Prefix rewrite with a word boundary. 9 old prefixes, one new prefix each:

| Old | New |
|---|---|
| `dummyindex.cli` | `dummyindex.context.cli` |
| `dummyindex.shared` | `dummyindex.context.shared` |
| `dummyindex.pipeline` | `dummyindex.context.pipeline` |
| `dummyindex.analysis` | `dummyindex.context.analysis` |
| `dummyindex.export` | `dummyindex.context.export` |
| `dummyindex.usage` | `dummyindex.context.usage` |
| `dummyindex.installer` | `dummyindex.context.installer` |
| `dummyindex.versioning` | `dummyindex.context.versioning` |
| `dummyindex.codex_guidance` | `dummyindex.context.codex_guidance` |

The boundary `\b` after the name stops `dummyindex.cli` from matching `dummyindex.context.cli`.
It covers source, tests and string targets (`monkeypatch.setattr("dummyindex...")`, `mock.patch`).
Path style (`dummyindex/cli/…`) in comments, docstrings and docs gets the same prefix.
Opaque data strings in tests stay (audit `scope`, docguard text, `feature_files`, `tests/fixtures/`).
`CHANGELOG.md` history stays.

### C3 — Points the prefix rewrite does not catch

1. **Cross-package relative imports.** These resolve wrong after the move. Make them absolute BEFORE the move.
   Today there are 5: `context/domains/requirements/seed.py:9`, `.../toml_io.py:16` (`....versioning`), `context/git.py:15` (`..pipeline.io`), `installer/common.py:11,12` (`..skills`, `..versioning`).
   A scan script (`D:\temp\scan_rel.py`) re-checks the whole tree after the move.
2. **Depth-based resource paths.** Depth grows by 1. Anchor on the `dummyindex.skills` package instead (example: `context/domains/equip/generate/render.py:24`).
   - `installer/common.py:22` `parents[1] / "skills"`.
   - `cli/statusline.py:20` `parent.parent / "skills" / "statusline"`.
   - `installer/ownership.py:21` `parents[1]` is the package root. `package_source_hash` hashes every file under it. Anchor on `dummyindex.__file__` so the hash scope stays the whole package. `parents[1]` would shrink it to `context/`.
3. **`dummyindex/__init__.py`** lazy `_map` holds 5 module-name strings. The prefix rewrite covers them. Check by hand.
4. **Tests that locate files by depth** (`Path(__file__).resolve().parents[N]`, `.parent.parent / "fixtures"`) in the moved test folders. Depth grows by 1. Use `tests/paths.py` (`TESTS_DIR`) where it fits.
5. **`from dummyindex import <name>`** forms: none today. The scan confirms.
6. **`evolve/evolve_native_snapshot.py`** digest key `"export/storage.py"` stays. The path comes from `graph_storage.__file__`, so it follows the move.
7. **Docs and generated text.** Update `docs/reference/01-conventions.md` (3-layer rule), `docs/guide/03-architecture.md`, `docs/guide/04-data-model.md:196`, `docs/guide/08-skill.md:215`. Check `dummyindex/skills/**/*.md` and `context/output/instructions.py` for module paths.

### C4 — Layers and boundary test

`tests/test_import_boundaries.py` takes the new layout:

- Layers by path: `dummyindex/evolve/**` = evolve. `dummyindex/context/shared/**` = shared. Everything else, with the root `__init__.py` and `__main__.py`, = context.
- Rules stay: shared imports shared and stdlib only. Context never imports evolve. Evolve imports shared and the public names of context.
- R1/R2 exception: the composition root becomes `dummyindex/context/cli/__init__.py`. Same 3 lazy evolve pairs.
- R5 old paths: add the 9 old prefixes. An old file must not come back.
- R7 allowlist: `dummyindex/context/pipeline/extract/generic.py` (line as found). `dummyindex/__init__.py` line 30 stays.
- New rule R8: the top level of `dummyindex/` has exactly the dirs `{context, evolve, skills}` and the files `{__init__.py, __main__.py}`. `__pycache__` is ignored. A `tmp_path` self-check proves it.
- Fresh-interpreter import list uses the new module paths.

## Risks (record, do not fix here)

- `dummyindex/context/__init__.py` imports `build.conventions` and more at module level. After the move, any import of a moved module runs it first.
  Two effects: an import cycle is possible, and `dummyindex install` loads more at start.
  The fresh-interpreter test must import each of the 9 moved packages alone. A cycle is a Wave 2 blocker. A start-time cost is only reported.
- The `shared` layer now sits inside `dummyindex.context`. The test must treat `dummyindex.context.shared` as shared, and the bare package `dummyindex.context` as context.

## Acceptance

- [ ] `ruff check .` passes.
- [ ] `python -m pytest tests/ -q --tb=short` passes with 0 failed.
- [ ] `python -m dummyindex --help` exits 0.
- [ ] The top level of `dummyindex/` is exactly `{__init__.py, __main__.py, skills, context, evolve}` (`__pycache__` ignored). R8 in `tests/test_import_boundaries.py` checks it.
- [ ] `git grep -nE "dummyindex\.(cli|shared|pipeline|analysis|export|usage|installer|versioning|codex_guidance)\b" -- dummyindex tests docs scripts pyproject.toml` has 0 hits.
- [ ] Each moved package imports alone in a fresh interpreter (`python -c "import dummyindex.context.<pkg>"`, 9 packages).
- [ ] `package_source_hash()` still hashes every file under `dummyindex/` (same file set as before the move).
- [ ] `git diff <base> HEAD -- pyproject.toml dummyindex/skills` is empty, except the `skills/**/*.md` path edits C3.7 names.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `equip`
- `session-memory`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
