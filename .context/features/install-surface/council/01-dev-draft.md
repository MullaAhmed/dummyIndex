# Install surface — plan

`confidence: INFERRED`

## Where it lives

- `dummyindex/installer/`: `args.py` (flags, usage); `common.py` (host paths,
  `LinkMode`, platform tokens, `render_skill`, slash commands, stamp reads,
  comparator aliases); `ownership.py` (manifest, sync, source status, removal);
  `legacy_fingerprints.py` (0.36.0 hashes only); `repair.py`; `uninstall.py`.
- `dummyindex/installer/install/`: `orchestrate.py` (`install()`),
  `family_write.py` (file sets, canonical sync, thin references, symlink
  preflight), `link_dispatch.py` (LINK gate, report lines), `project_init.py`
  (auto-init, hooks, default plugins, config, equipment).
- `dummyindex/installer/link/`: classification, capability probe, link creation
  with rename-aside recovery, dangling sweep.
- `dummyindex/versioning.py`: neutral comparator imported by
  `dummyindex/installer/common.py:11` and
  `dummyindex/context/build/enriched_refresh.py:88`.
- Wired seams owned elsewhere: `dummyindex/context/hooks.py`,
  `dummyindex/context/default_plugins.py`,
  `dummyindex/context/domains/equip/lifecycle/status.py`.
- Tests: `tests/test_install*.py`, `tests/test_versioning.py`,
  `tests/context/test_hooks.py`, `tests/context/test_default_plugins.py`, all
  with isolated HOME/USERPROFILE.

## Architecture in three sentences

`install()` validates arguments and symlink chains, runs repair, syncs the
canonical `.agents` family, then links or references Claude via
`run_link_install` + `_install_skill_references` or writes a full copy
(`dummyindex/installer/install/orchestrate.py:127-285`). Every family and
command file write goes through `sync_family`, so install, repair, references,
and slash commands share one hash-gated ownership rule (`family_write.py:75-81`, `145-153`;
`dummyindex/installer/common.py:262-264`). Project init is a best-effort tail
that lazily imports `context/`, refreshes or full-builds, and prints each step
as a `label -> outcome` line instead of raising (`project_init.py:55-180`).

## Data model

No database. Per family: `.dummyindex-files.json` (schema 1: per-file hashes,
layout, skill and package source digests, `complete`) plus `.dummyindex_version`,
written only when complete (`dummyindex/installer/ownership.py:219-238`).
Downstream, through other features' APIs: `.context/meta.json`
`dummyindex_version`, advanced only after every required artefact writes and
lowered only with `allow_downgrade`
(`dummyindex/context/build/enriched_refresh.py:227-230`, `362-401`);
`.context/config.json`; `.claude/settings*.json`; `~/.claude/CLAUDE.md`.

## Key decisions

- **Hashes authorize writes; stamps do not.** `source_status` checks completeness,
  package and skill source digests, and bytes separately, since a matching
  version can coexist with edited guidance (`ownership.py:244-260`).
- **`versioning.py` is top-level** because `context/` may not import
  `installer/`. `VersionOrder` mixes in `str` and pins `__str__`, so existing
  `== "older"`, `in ("newer", "unknown")`, and f-string callers are unchanged;
  unparseable is `UNKNOWN`, so garbage never triggers an upgrade
  (`dummyindex/versioning.py:14-32`, `common.py:384-398`).
- **One `force_downgrade`** covers family stamps and the curated `.context` stamp
  (`orchestrate.py:326-332`, `project_init.py:86-91`). The full build needs no
  flag: `build_all` writes fresh meta at the running version
  (`dummyindex/context/build/runner.py:167`).
- **Degrade, don't fail.** `context/` imports are function-local inside `try`,
  and a held-back stamp still returns True, because the skill install already
  succeeded (`project_init.py:47-68`, `95-100`).
- **Package-attribute seam.** `run_link_install` and `_install_project_hooks`
  are called through the package object so tests can monkeypatch them
  (`orchestrate.py:5-21`, `project_init.py:6-22`).
- **Cycle break.** `repair.py:65` imports `.install` at module level, so
  `install()` imports `repair` inside the function (`orchestrate.py:187`, `288`).
- **One-version legacy catalog.** Unmanifested content stamped anything but
  0.36.0 gets no baseline and is preserved for review (`ownership.py:108-116`).

## Open questions

- `--force-downgrade` help still says only "allow repair to rewrite a copy
  stamped newer" (`args.py:47-48`), though the flag now also lowers a newer
  `meta.dummyindex_version`. No install-level test passes `force_downgrade=True`
  through auto-init; `allow_downgrade` is tested only at
  `tests/context/build/test_index_repair.py:85-110`.
- `_agents_family_stamp_state` is annotated `-> str` but returns a `VersionOrder`
  for stamped families (`link_dispatch.py:125-142`). The `str` mixin makes this
  harmless.
