# Architect notes — Install surface

## What I changed

- `plan.md` 84 → 83 lines. Kept `confidence: INFERRED`, the dev's five sections, and exactly
  three sentences under "Architecture in three sentences".
- Boundary comes first now: the installer writes skill families, `.claude/commands/` and
  `~/.claude/CLAUDE.md` itself (`dummyindex/installer/install/orchestrate.py:384-396`).
  `context/hooks.py`, `context/default_plugins.py` and
  `context/domains/equip/lifecycle/status.py` are also listed in `equip/feature.json`, and
  `context/build/enriched_refresh.py` belongs to `index-lifecycle`, so they are marked
  "called, not owned".
- Added Downstream, Upstream and Cycles bullets. Dropped the tests bullet because
  `feature.json` `files` already lists those tests and they don't define the boundary.
- Fixed an overclaim in the draft. It said "`context/` imports are function-local", but
  `context.domains.config` (`orchestrate.py:22`, `project_init.py:23`) and
  `context.domains.atomic_io` (`ownership.py:12`) are imported at module level.
- Fixed ranges:
  - `_advance_version_stamp`: `362-401` → `362-409` (the write is at `405-408`).
  - "held-back stamp still returns True" now also cites `project_init.py:130`, where the
    `return True` is.
  - Dropped `common.py:384-398` (the comment block starts at `383`; the alias pair at
    `397-398` is already pinned in `spec.md` Contracts).
- Data model now lists the manifest keys (`ownership.py:219-228`). Moved
  `~/.claude/CLAUDE.md` out of "via other features", because `_register_claude_user_skill`
  writes it directly.
- Moved the "one `--force-downgrade`" decision into Open questions. The code gives no
  reason for using one flag for both stamps, so it can't be written as "decided because".
- Dropped the `_agents_family_stamp_state -> str` open question: it is cosmetic, and the
  draft already called it harmless.
- Flagged conflict (code wins): the `run_link_install` docstring says an AUTO probe failure
  falls through to a copy path (`link/orchestrate.py:161-167`). The warning text (`:208`)
  and `install()` (`orchestrate.py:279-285`) write thin references instead. This is in the
  plan as an Open question.
- Flagged conflict (code wins): `link/__init__.py:18-21` says link modules import only
  `..common`, but `link/create.py:253` and `355` lazily import `..ownership`. No cycle
  results, because `ownership` never imports `link`, so I kept this out of the plan.
- Flagged conflict (code wins): the `_all_claude_families_missing` docstring says "8
  enumerated" families (`link_dispatch.py:28`). The registry at `common.py:89-99` holds
  main plus 9 siblings, which is 10. The function has no caller.
- Flagged conflict (code wins): the `_claude_narrowing_link_gate` docstring
  (`link_dispatch.py:154-157`) describes an AUTO fallback. `install()` never reaches it,
  because it calls the gate only under LINK (`orchestrate.py:256-259`).
- Doc evidence: no `high` or `medium` prose doc covers this feature. The only catalogued
  hits are `low`: `CHANGELOG.md`, `docs/guide/07-cli.md`, `docs/guide/09-lifecycle.md` and
  `docs/sources/installable-sources.md`. I quoted none of them.
- Every named symbol was checked in `map/symbols.json`. `LEGACY_FILES` and the
  `_SIBLING_SKILLS` tuple are constants that the index doesn't record, so the plan cites
  them by `path:line` only.

## Patterns named

- Linear orchestrator: `install()` (`dummyindex/installer/install/orchestrate.py:55-381`).
- Plan → execute → describe: `plan_repairs` (`repair.py:331`), `execute_repairs` (`:447`),
  `describe_plan` (`:609`), wired at `orchestrate.py:187-204`.
- Enum-switched tri-state dispatcher: `LinkMode` (`common.py:49`) and `run_link_install`
  (`link/orchestrate.py:130-220`), with the caller's branch at `orchestrate.py:228-285`.
- Single write gate: `sync_family` (`ownership.py:157-241`). Callers are
  `family_write.py:75-81`, `146-153` and `common.py:262-264`.
- Single remover: `remove_family` (`ownership.py:263-299`). Callers are `common.py:282` and
  `uninstall.py:156`, `185`.
- Static family registry: `common.py:89-99`, read at `family_write.py:38`, `:178`,
  `link_dispatch.py:43` and `link/families.py:12`. It is enumerated, not globbed
  (`link_dispatch.py:28-29`). This is named in "Where it lives" only.
- Best-effort step chain: `_auto_init_project` (`project_init.py:55-180`). Each step
  catches its error and prints `label -> outcome`.
- Late-bound package attribute (test seam): `orchestrate.py:21`, `261`;
  `project_init.py:22`, `123`, `173`; `install/__init__.py:18-26`. The same shape is at
  `link/sweep.py:10`.
- Leaf subpackage by import law: `link/__init__.py:18-25`.
- Evidenced but left out of the plan as not boundary-defining:
  - Callable seam `symlink_fn=os.symlink` (`link/orchestrate.py:134`), which matches
    `.context/conventions/coding-practices.md:64-71`.
  - Closed `(str, Enum)` alphabets: `LinkMode` (`common.py:49`) and `FamilyLinkState`
    (`link/models.py:17`).

## Dependencies surfaced

- Downstream:
  - `__main__.py:29-37`: `install`, `uninstall`, `parse_*_args`.
  - `cli/check.py:199-200`, `251-256`, `346`: `context check --versions`, which uses
    `scan_installed_copies`, `read_manifest`, `source_status`, `expected_families`,
    `reference_skill` and `package_source_hash`.
  - `normalize_platform_arg` users: `cli/bootstrap.py:16`, `cli/init.py:128`,
    `cli/onboard.py:54`, `cli/equip/dispatch.py:69`.
- Upstream, lazy imports:
  - `project_init.py:55-65`: `context.build`, `build_all`, `format_migration_report`,
    `context.hooks.install`, `context.output.{agents_md,claude_md}`, `cli.migrate`.
  - `project_init.py:195-197`: `cli.equip.common`, `context.domains.equip`.
  - `project_init.py:261-265`, `288`, `306`, `331-344`: config and default plugins.
  - `orchestrate.py:320` (`is_git_repo`), `402` (`agents_md`); `uninstall.py:210`.
- Upstream, module-level imports:
  - `common.py:11`: `versioning`.
  - `repair.py:50`: `codex_guidance`.
  - `orchestrate.py:22` and `project_init.py:23`: `context.domains.config`.
  - `ownership.py:12`: `context.domains.atomic_io`.
- Cycles, each held apart by function-local imports:
  - `install` ↔ `repair`: `repair.py:65` imports eagerly; `orchestrate.py:187` and `288`
    import lazily.
  - `common` ↔ `ownership`: `common.py:255` and `ownership.py:169`, both lazy.
  - `installer` ↔ `cli`: the installer side is lazy (`project_init.py:56`, `196`). The cli
    side is lazy in `cli/check.py` and eager in `cli/onboard.py:54` and
    `cli/equip/dispatch.py:69`.
  - Package self-imports at `orchestrate.py:21`, `project_init.py:22` and
    `link/sweep.py:10` are safe according to their own docstrings.
- Layering: `.context/conventions/coding-practices.md:89-90` puts `cli` and `installer` in
  one tier and says nothing about imports between them, so the `installer` → `cli` imports
  are neither allowed nor forbidden. I kept this out of the plan.
- The forbidden direction `context` → `installer` is clean: no import found. It is
  documented at `versioning.py:4-6` and `context/build/upgrade.py:20-22`.
- Feature overlap: `equip` co-lists `hooks.py`, `default_plugins.py` and
  `lifecycle/status.py`. `index-lifecycle` owns `enriched_refresh.py`.

## Decisions promoted

- Hashes authorize writes, not stamps, because stock guidance can change within a
  development version (`orchestrate.py:205-206`).
- Non-COPY Claude also syncs `.agents` before linking, so links never target a stale or
  partial tree (`orchestrate.py:95-97`; `link/orchestrate.py:139-145`).
- One Claude allowlist per run, so preflight, links and commands never hold divergent
  notions of a dotfiles `.claude` (`orchestrate.py:115-126`, `306`).
- `versioning.py` is top-level because `context/` may not import `installer/`
  (`versioning.py:4-6`; `context/build/upgrade.py:20-22`).
- `VersionOrder` pins `__str__` because callers compare it to strings and put it in
  f-strings (`versioning.py:18-32`).
- A curated index is refreshed and never re-clustered, because a bare `install` (the
  `/dummyindex-update` flow) must not flatten council taxonomy (`project_init.py:74-81`).
- Degrade, don't fail, because the skill install already succeeded
  (`project_init.py:47-51`). Hooks likewise always return True (`project_init.py:232-234`).
- Calls go through the package object because tests monkeypatch the package attribute
  (`orchestrate.py:5-13`; `project_init.py:6-14`).
- `link/` is a leaf because install, repair and uninstall import it
  (`link/__init__.py:18-22`).
- Not promoted to "because":
  - One `--force-downgrade` for both stamps: the code gives no reason.
  - The 0.36.0-only legacy catalog: `legacy_fingerprints.py:1-4` gives its scope but not
    why only one version. It stays as a plain decision.
