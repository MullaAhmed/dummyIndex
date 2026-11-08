# Install surface — plan

`confidence: INFERRED`

## Where it lives

- Boundary: writes skill families (files, links, manifests), `.claude/commands/` and
  `~/.claude/CLAUDE.md` (`dummyindex/installer/install/orchestrate.py:367-379`). It calls
  but does not own `context/{hooks,default_plugins,domains/equip/lifecycle/status}.py`
  (also `equip`) and `context/build/enriched_refresh.py` (`index-lifecycle`).
- `dummyindex/installer/`: `args.py`, `common.py` (paths, `LinkMode`, family registry
  `:80-90`, `render_skill`, stamps), `ownership.py`, `legacy_fingerprints.py`,
  `repair.py`, `uninstall.py`; `install/` (`orchestrate`, `family_write`, `link_dispatch`,
  `project_init`); `link/` (classify, probe, create, sweep); `dummyindex/versioning.py`.
- Downstream: `dummyindex/__main__.py:15-23`; `dummyindex/cli/check.py:181`, `233`, `325` (`--versions`);
  `normalize_platform_arg` in `cli/{bootstrap,init,onboard,equip/dispatch}.py`.
- Upstream: lazy `context.{build,hooks,default_plugins,output,domains.equip}`,
  `cli.migrate`, `cli.equip.common` (`dummyindex/installer/install/project_init.py:40-50`, `173-175`); eager
  `versioning`, `codex_guidance`, `context.domains.{config,atomic_io}` (`dummyindex/installer/common.py:11`,
  `dummyindex/installer/repair.py:16`, `dummyindex/installer/install/orchestrate.py:14`, `dummyindex/installer/ownership.py:12`).
- Cycles, broken by function-local imports: `install` ↔ `repair` (`dummyindex/installer/repair.py:31`
  eager; `dummyindex/installer/install/orchestrate.py:173`, `274` lazy); `common` ↔ `ownership` (`dummyindex/installer/common.py:243`,
  `dummyindex/installer/ownership.py:169`); `installer` ↔ `cli` (`dummyindex/installer/install/project_init.py:41`, `174`).

## Architecture in three sentences

`install()` is a linear orchestrator: a symlink preflight refuses unsafe managed paths,
repair runs plan → execute → describe (`dummyindex/installer/install/orchestrate.py:173-190`), the canonical
`.agents` family syncs, then Claude dispatches on `LinkMode` — COPY full copies,
LINK/AUTO `run_link_install` (`dummyindex/installer/link/orchestrate.py:92-147`), AUTO plus thin references
(`dummyindex/installer/install/orchestrate.py:113-271`). `sync_family` (`dummyindex/installer/ownership.py:157-241`) is the single write
gate (`dummyindex/installer/install/family_write.py:75-81`, `146-153`; `dummyindex/installer/common.py:250-252`) and `remove_family`
(`dummyindex/installer/ownership.py:263-299`) the single remover (`dummyindex/installer/common.py:270`; `dummyindex/installer/uninstall.py:144`, `173`),
so install, repair, uninstall and dedupe share one hash rule. Project init is a
best-effort step chain (refresh or build, guidance, hooks, plugins, equipment), each step
printing `label -> outcome` instead of raising (`dummyindex/installer/install/project_init.py:40-161`).

## Data model

No database. Per family: `.dummyindex-files.json` (schema 1: `family`, `version`, `layout`
full|reference, `source_sha256`, `package_source_sha256`, `complete`, per-file `files`)
plus `.dummyindex_version`, written only when complete (`dummyindex/installer/ownership.py:219-238`). Via
other features: `.context/meta.json` `dummyindex_version`, advanced only when every
required artefact writes and lowered only with `allow_downgrade`
(`dummyindex/context/build/enriched_refresh.py:176-179`, `305-339`); `.context/config.json`;
`.claude/settings*.json`.

## Key decisions

- **Hashes authorize writes; stamps are hints**, because stock guidance can change within
  a development version (`dummyindex/installer/install/orchestrate.py:191-192`). A newer/unparseable stamp blocks
  unless `--force-downgrade`, which never bypasses hashes (`dummyindex/installer/ownership.py:171-178`); a bad
  manifest raises (`179-183`); `source_status` checks digests and bytes apart (`244-260`).
- **One canonical body**: non-COPY Claude also syncs `.agents` (`dummyindex/installer/install/orchestrate.py:87-89`),
  because links must never target a stale or partial tree (`dummyindex/installer/link/orchestrate.py:101-102`).
- **One Claude allowlist per run** (`dummyindex/installer/install/orchestrate.py:105-112`, reused `289`), so preflight,
  links and commands never disagree on a tolerated dotfiles `.claude`.
- **`versioning.py` is top-level** because `context/` may not import `installer/`
  (`dummyindex/versioning.py:3-4`; `dummyindex/context/build/upgrade.py:7`); `VersionOrder(str, Enum)` pins
  `__str__` because callers compare and format it as a string (`dummyindex/versioning.py:13-29`).
- **Refresh, never re-cluster, a curated index**, because the `/dummyindex-update` flow
  runs bare `install` (`dummyindex/installer/install/project_init.py:59-62`); the full build needs no downgrade flag
  since `build_all` writes fresh meta (`dummyindex/context/build/runner.py:152`).
- **Degrade, don't fail**, because the skill install already succeeded
  (`dummyindex/installer/install/project_init.py:34-35`): a held-back stamp warns, init returns True (`67-81`, `111`);
  an incomplete family exits 1 only after every later step (`dummyindex/installer/install/orchestrate.py:340-345`).
- **Package-object test seam**: `run_link_install` and `_install_project_hooks` resolve
  through the package for monkeypatching (`dummyindex/installer/install/orchestrate.py:3-5`; `dummyindex/installer/install/project_init.py:4-6`).
- **`link/` is a leaf** (rule: only `..common`) because install, repair and uninstall
  import it (`dummyindex/installer/link/__init__.py:3-5`).
- **One-version legacy catalog**: unmanifested content not stamped 0.36.0 gets no
  baseline and is preserved (`dummyindex/installer/ownership.py:108-116`).

## Open questions

- `--force-downgrade` also lowers `meta.dummyindex_version` (`dummyindex/installer/install/project_init.py:67-72`);
  its help omits that (`dummyindex/installer/args.py:47-48`), and every install test passing it sets
  `skill_only=True`, leaving only `tests/context/build/test_index_repair.py:85-110`.
- `dummyindex/installer/link/orchestrate.py:104-107` says an AUTO probe failure falls back to copies; the code
  writes thin references (`:135`; `dummyindex/installer/install/orchestrate.py:265-271`). Code wins.
- No production caller: `_all_claude_families_missing` (`dummyindex/installer/install/link_dispatch.py:27-36`),
  `_backfill_sibling_stamps` (`39-78`), and `_claude_narrowing_link_gate`'s AUTO branch
  (`157`), since `install()` gates only LINK (`dummyindex/installer/install/orchestrate.py:242-245`).
