# Equip — spec

`confidence: INFERRED`

## Intent

Equip renders a project-tuned Claude Code toolkit from a repo's own `.context/`
spine — implementer/tester/reviewer agents, a verify skill, capability
specialists, and a format hook — so an AI session working in the repo dispatches
agents grounded in the project's real conventions instead of generic ones. It
also acts as a Claude plugin manager: it discovers marketplace plugins that fill
detected capability gaps and wires them natively into `.claude/settings.json`,
gated by source trust and a disclosed blast radius. Once applied, a
hash-baselined lifecycle lets generated tools evolve and refresh over time
without ever overwriting an edit the user made by hand.

## User-visible behavior

The surface is the `dummyindex context equip <verb>` CLI
(`dummyindex/cli/equip/dispatch.py:9-19`). `apply` is an explicit verb: a bare
`equip` prints usage and exits 2 so a help probe never mutates the repo, with
one carve-out — verbless `equip --dry-run` still previews
(`dispatch.py:104-109`, `:146-161`).

Verbs:
- `apply [path] [--root DIR] [--dry-run] [--for-proposal S] [--specialist C] [--json]`
  — render + write the toolkit. `--dry-run` writes nothing
  (`dispatch.py:352-378`); `--for-proposal` adds specialists a proposal's plan
  demands; `--specialist C` forces one templated specialist.
- `add-specialist CAPABILITY` — sugar over `apply --specialist`
  (`dispatch.py:193-225`).
- `discover ["query"] [--repo OWNER/NAME] [--json]` — dry-run plugin/skill
  search. With no query, ranks against the real capability gap
  (`generate/gaps.py:capability_gaps` = stack-required − manifest-covered), and
  enumerates `is_collection` seeds' skills as candidates (`discover.py`).
- `install <plugin>@<marketplace> [--yes] [--scope project|local|user] [--usage-doc P | --skip-usage-doc]`
  — NATIVE-enable a packaged plugin, **or** VENDOR a collection skill: fetch its
  `SKILL.md` at a pinned commit sha, stamp + write it to
  `.claude/skills/<name>/SKILL.md` under the never-clobber guard, and record a
  `source=vendored` item with `origin_ref=<sha>` (`cli/equip/install.py`). Same
  trust + usage-doc gate for both mechanisms.
- `verify <plugin>@<marketplace>` (`plugin_state.py`), `status [--json]`,
  `refresh [--dry-run]`, `reset NAME`, `remove NAME`, `uninstall [--dry-run]`,
  `patch --item NAME --from-file F` (`verbs.py`).

What gets written to `.claude/`: generated agent `.md` files under
`.claude/agents/`, a verify `SKILL.md` under `.claude/skills/{proj}-verify/`
(`generate/catalog.py:94-124`), and a PostToolUse format-hook entry in
`.claude/settings.json` when a formatter is detected
(`generate/catalog.py:127-158`). Every generated `.md` carries the
`<!-- dummyindex:generated -->` sentinel (`models.py:28`). The toolkit record is
written to `.context/equipment.json` (`models.py:222-244`).

The plugin-manager surface: `discover` collects seed marketplaces + declared +
GitHub-searched catalogs (`discover.py:_collect_catalogs`), ranks candidates by
capability overlap and query hits (`plugins/discover.py:98-142`), and prints each
with its blast radius (declared surfaces, runs-code, trust tier) and whether it
needs `--yes`. `install` enables the plugin in `settings.json`, records a
MARKETPLACE item in the manifest, **and (project/local scope) upserts the
matching `wired` entry into the committed `config.json`** keyed on
`<plugin>@<marketplace>` — so `config.wired` (declared intent) and
`equipment.json` (render manifest) stay reconcilable on that shared key
(`install.py:171-209`, `_write_back_wired` at `install.py:449-489`). The
write-back is **skipped with a warning when no committed `config.json` exists**
(e.g. `--scope user`, or a repo indexed before config existed) — it never
materialises a seeded config as a side effect of one install, and a write failure
leaves the install rc + manifest intact. An untrusted source requires `--yes`,
and a usage playbook (`--usage-doc` or `--skip-usage-doc`) is mandatory
(`install.py:131-148` approval gate, `_validate_usage_doc` at `install.py:492`).

`apply` refuses to write into an un-indexed repo — no `.context/` dir means
"run `dummyindex ingest` first" and exit 1 (`dispatch.py:256-262`).

## Contracts

CLI entry / dispatch:
- `run(args: list[str]) -> int` (`dispatch.py:96-134`) — routes the verb.
- `run_apply(rest) -> int` (`dispatch.py:167-190`),
  `run_add_specialist(rest) -> int` (`dispatch.py:193-225`).
- `run_discover(rest) -> int` (`discover.py:290`),
  `run_install(rest) -> int` (`install.py:62-215`) — the install verb +
  vendor/record helpers were extracted from `discover.py` into `install.py`
  (Wave 3); `install.py` reaches the runner + shared discovery helpers via
  `from . import discover` so the `discover._RUNNER` test seam is unchanged.

Pure policy core:
- `detect_stack(context_dir: Path) -> StackProfile`
  (`generate/detect.py:90-109`).
- `build_catalog(*, profile, conventions, preflight, proj, proposal_capabilities=(), forced_specialist_capabilities=()) -> CatalogDecision`
  (`generate/catalog.py:60-91`).
- `resolve_coverage(*, preflight, proposal_capabilities=(), forced_capabilities=(), templated_capabilities=frozenset(), stack_frontend=True) -> Coverage`
  (`generate/adopt.py:81-144`).
- `specialist_spec(capability, *, label, proj) -> GenerateSpec`
  (`generate/specialists.py:215-232`);
  `templated_capabilities() -> frozenset[str]` (`:189-195`).

Lifecycle (hash-baselined):
- `content_hash(text: str) -> str` (`lifecycle/hashing.py:16-18`).
- `classify_item(root: Path, item) -> ItemState` (`lifecycle/status.py:137-165`).
- `is_user_owned(state) -> bool` (`lifecycle/status.py:168-181`).
- `status / refresh / reset / uninstall` (`lifecycle/status.py:184-399`).
- `apply_patch(*, root, manifest, name, old, new) -> EquipmentItem`
  (`lifecycle/evolve.py:25-70`).

Plugin manager (pure):
- `match_candidates(catalogs, *, needed_caps=(), query=None, force_repos=frozenset()) -> tuple[Candidate, ...]`
  (`plugins/discover.py:98-142`).
- `capabilities_for(entry) -> tuple[str, ...]` (`plugins/discover.py:58-75`).
- `analyze_blast_radius(entry, *, trusted) -> BlastRadius`
  (`plugins/blast_radius.py:32-36`).
- `build_install_plan(candidates) -> InstallPlan` (`plugins/install_plan.py:51-52`).
- `SEED_MARKETPLACES: tuple[SeedMarketplace, ...]` (`plugins/marketplace.py:49-64`).

Data shapes (frozen): `StackProfile`, `EquipmentItem`, `EquipmentManifest`,
`AdoptSpec`, `GenerateSpec`, `HookSpec`, `CatalogDecision`
(`models.py:43-244`). Closed alphabets: `EquipmentKind`, `EquipmentSource`,
`EquipVerb`, `Capability`, `ItemState`, `TrustTier`, `InstallMechanism`,
`PluginSurface` (`enums.py:7-119`).

## Examples

Happy-path `equip apply` on a python repo:

1. `run(["apply"])` routes to `run_apply` → `_run_apply`
   (`dispatch.py:110-111`, `:241`).
2. `_run_apply` confirms `.context/` exists, reads the prior manifest, builds a
   `PreflightReport`, and drops equip's own generated agents from the
   project-agent set so they are never re-adopted (`dispatch.py:256-294`).
3. `detect_stack` tallies `map/files.json` languages → `label="python"`, scans
   root manifests → `formatter="ruff"`, `test_command="uv run pytest -q"`
   (`detect.py:90-109`, `:112-144`).
4. `build_catalog` returns the standard four generated specs
   (`python-implementer`, `python-tester`, `{proj}-reviewer`, `{proj}-verify`)
   plus a ruff PostToolUse format hook (`catalog.py:78-91`, `:94-158`).
5. `render_generated_set` renders each spec to `(item, path, content)`; the
   format hook command is `command -v ruff … || exit 0; ruff format … ; exit 0`
   (`catalog.py:144-158`).
6. `_apply_write` writes each file (skipping any USER_MODIFIED carry-forward),
   wires the hook into `.claude/settings.json`, and MERGES the manifest —
   carrying forward every prior record this run did not re-derive
   (`dispatch.py:381-547`).
7. Stdout: `equip: wrote 4 file(s), adopted 0 …, wired 1 hook event(s) …`;
   `.context/equipment.json` now holds five items (`dispatch.py:539-546`).
