# Spec — Fix weak task-specific agents and add a hard-gated, shareable required-setup manifest (.context/config.toml)

## Intent

Four user-reported defects. One proposal, four tracks.

**Track A — task-specific agents are weak.** Claude cannot route to generated agents. They are generic. Some do not fit the repo.

- A1. Every native adapter has `description: Use the project's <name> capability.` (`dummyindex/context/domains/equip/generate/adapters.py:33-42`). Claude selects a subagent or skill by its description, so routing fails.
- A2. `write_native_adapter` and `remove_native_adapter` (`adapters.py:54-106`) compare the whole file with one render. A changed adapter format or description never reaches an equipped repo, and a changed adapter is never removed.
- A3. `_all_templated_capabilities` (`dummyindex/context/domains/equip/generate/catalog.py:79-95`) generates the db, security, performance, docs and search specialists for every repo. This repo has no database (0 `*.sql`, `migrations/`, `alembic.ini` or `schema.prisma` in 614 mapped paths) but has a db specialist with Supabase/Postgres instructions.
- A4. Templates fill only stack, project slug, convention paths and commands (`generate/plan.py:24-60`). With no framework, `render.py:34` writes the filler `the project's stack`. No agent knows the repo's features, key files or recorded risks.

**Track B — a repo cannot require a setup that every dev shares.** User decision: hard gate. Each `.context/` ships a committed `config.toml` that lists the required plugins, skills, equipment and a minimum dummyindex version. A dev can have more. A dev cannot work while a required item is missing. The committed `.context/` is the source of truth. `.claude/` is derived from it, because many repos (this one too, `.gitignore:23`) gitignore `.claude/`.

- B1. `classify_wired_entry` (`dummyindex/context/default_plugins.py:424-438`) returns `NEEDS_USER` for every skill.
- B2. `cli/init.py` and `installer/install/project_init.py` do not restore `.claude/agents` or `.claude/skills` adapters from the committed `.context/equipment.json`.
- B3. Nothing detects a gitignored `.claude/`.
- B4. No hook checks declared requirements. Every managed hook exits 0 when the CLI is missing (`dummyindex/context/hooks.py:84-91`).
- B5. `config.wired[].version` is descriptive only.

**Track C — a dummyindex update must always carry `.context/` forward.** User statement: "each dummyindex update also should change the .context it should not be option". Today the per-repo pass runs only when `install` runs inside that repo. Equipment refresh is best-effort. The update skill tells the user to run `equip refresh` by hand if it was skipped.

**Track D — one-time task agents stay forever.** User statement: "dummyindex also creates a lot of shitty one time task specific agents which are useless once the task is done so i need them to be clean up in gc too". `equip apply --for-proposal <slug>` adds proposal-signalled specialists, adopted agents and sourced items. Nothing records which task created them. `specialist_caps_from_manifest` (`dummyindex/cli/equip/common.py:115`) carries every applied specialist forward on each apply. The GC sweeps only proposal, audit, orphan-scaffold and archived workspaces (`dummyindex/context/domains/gc/enums.py:23-29`).

Who: every dev on a repo that uses dummyindex, and the agents they dispatch.

## Contracts

### A — generated agents

1. **Adapter description.** `native_adapter_content(item, *, description: str | None = None)` writes the canonical body's frontmatter `description` into the adapter. `adapter_description(body_text)` reads it with `split_frontmatter` (`dummyindex/context/domains/equip/plugins/sourcing.py:98`). It strips control characters and U+2028/U+2029, collapses whitespace to one line, cuts at 300 characters on a character boundary, and emits the value with `json.dumps(ensure_ascii=True)` (valid YAML double-quoted). An empty or absent description gives the current generic text. A sourced item uses its upstream description.
2. **Adapter ownership by structure.** An adapter is pristine when its decoded, newline-normalised text equals `native_adapter_content(item, description=<its own description line>)`, so any description is accepted when the rest of the skeleton and both sentinels match exactly. This rule replaces the whole-file comparison in `write_native_adapter` and `remove_native_adapter`. It needs no body, so `equip remove`, `equip uninstall` and GC delete still remove new-format adapters. A pre-fix generic adapter matches the same rule. Any other text stays user-owned. The symlink rules stay.
3. **Evidence-gated specialists.** `StackProfile` gains `data_stores` and `search_backends` (`tuple[str, ...]`, default `()`, never written into `project_binding` or manifest bytes). `detect_stack` fills them with word-boundary regexes over the manifests that the existing scan reads, plus paths in `map/files.json` (separators normalised to `/`):
   - db tokens: `sqlalchemy`, `alembic`, `psycopg`, `psycopg2`, `asyncpg`, `pymongo`, `motor`, `prisma`, `drizzle-orm`, `typeorm`, `sequelize`, `knex`, `mongoose`, `django`, `supabase`, `peewee`, `tortoise-orm`, `sqlite3`, `mysql`, `mysqlclient`, `pgx`, `gorm`, `sqlx`, `sqlc`, `diesel`, `activerecord`, `dapper`, `hibernate`, `jdbc`. db files: `*.sql`, `alembic.ini`, `prisma/schema.prisma`, any `migrations/` directory.
   - search tokens: `elasticsearch`, `opensearch`, `meilisearch`, `typesense`, `algoliasearch`, `whoosh`, `tantivy`, `pgvector`, `faiss`, `faiss-cpu`, `qdrant-client`, `chromadb`, `weaviate-client`, `pinecone`, `rank_bm25`, `lunr`.
   - security, performance, docs: baseline for every non-`generic` stack.
   The db and search specialists generate only with evidence, an explicit `add-specialist` ask, or a proposal capability. `EquipmentItem.requested_by: RequestedBy | None` (new `(str, Enum)` in `equip/enums.py`: `add_specialist`, `proposal`, `legacy`). The first upgrade after this change backfills `legacy` on every existing specialist. An upgrade never deletes a specialist. It reports `specialist without evidence: <name> (see dummyindex-gc)`, and deletion is a GC decision (Track D).
4. **Repo-grounded agents, without body churn.** Each generated agent and skill body gets one fixed instruction block: read the grounding sidecar `.context/equipment/grounding/<name>.md`, and run `dummyindex context query "<focus query>"` for the task at hand. The body bytes do not depend on `.context/` content, so `origin_hash` and refresh semantics do not change. The sidecar is CLI-owned and fully regenerated (header `<!-- dummyindex:generated-grounding — do not edit -->`), with no ownership hash. It is written by `equip apply`, `equip refresh` and the upgrade. It contains:
   - the project one-liner from `PROJECT.md` (first non-heading paragraph, max 300 characters);
   - the focus features: top 5 by `query` score (`dummyindex/context/domains/query.py:271`) for the capability's fixed focus query (`_FOCUS_QUERIES`; implementer/tester/reviewer/verify: top 5 by `member_count`), each `` `<feature_id>` — <summary> `` plus up to 3 entry files;
   - recorded risks: up to 5 first-level bullets from those features' `concerns.md`, each with its `path:line` citation.
   Limit: 6,000 UTF-8 bytes. The cut happens only at line boundaries, so no citation or multibyte character is split. Sorting is stable, with ties broken by `feature_id`. CRLF input gives the same bytes as LF, and paths use `/`. An absent `features/INDEX.json` or `concerns.md` gives a shorter sidecar, never an error.
   Templates replace `(framework: {{framework}})` with `{{framework_clause}}`, which renders ` (framework: X)` or nothing. The text `the project's stack` is removed.
5. **Layer fix.** `fresh_rendered`, `fresh_renders`, `specialist_caps_from_manifest`, `drop_generated_stems`, `filter_grounding_docs` and `project_slug` move from `dummyindex/cli/equip/common.py` to `dummyindex/context/domains/equip/generate/fresh.py`. `cli/equip/common.py` re-exports them. The rule is `context/` never imports `cli/` (`conventions/folder-organization.md:21`).

### B — `.context/config.toml` required setup

6. **File.** `.context/config.toml`, committed. The CLI writes it in full only when it creates it. Later CLI changes are line-level edits of the one key they change, so hand-written comments survive. Schema v1:
   ```toml
   # Required setup for every dev on this repo. Extras are allowed.
   schema_version = 1

   [dummyindex]
   min_version = "0.39.0"

   [[plugins]]
   id = "superpowers@claude-plugins-official"
   version = ">=7.0.0"       # optional; ">=" or "==" only

   [[skills]]
   name = "dummyindex-plan"
   from = "dummyindex"       # "dummyindex" | "plugin:<id>" | "project"

   [equipment]
   require_native_adapters = true
   ```
   `toml_io.py` reads with `tomllib`/`tomli` (pattern `dummyindex/codex_guidance.py:16-18`) and catches `ValueError`. A `schema_version` above 1, a duplicate `id`, an unknown `from` or a bad version constraint makes the file `invalid`. Unknown keys are kept on rewrite. A CRLF file or a UTF-8 BOM parses. The managed `.context/.gitignore` never ignores `config.toml`.
7. **Single owner.** When `config.toml` exists, it is the only source for required plugins and skills. `read_config` derives `Config.wired` from it, and the CLI writes no mirror. The writers `_write_back_wired` (`dummyindex/cli/equip/install.py:441`), `reconcile_wired_with_equipment` and `reconcile_default_plugins` (`dummyindex/context/domains/config.py:561,606`) write through `write_requirements`. `requirements/` imports nothing from `domains/config.py`. A CLI older than this change ignores `config.toml` and is not gated. This is a documented limit.
8. **Creation and seeding.** The upgrade creates `config.toml` once, when it is absent and `config.json` parses. It seeds:
   - `[[plugins]]` from `wired`, without the reviewed defaults when `default_plugins_enabled` is false;
   - `[[skills]]` with the dummyindex skill family;
   - `min_version` with the running CLI version, only when that version is a parseable release (no `.dev`, no pre-release, not `unknown`); otherwise the key is left out;
   - `require_native_adapters = true` only when the repo has Claude wiring (platform `claude` or `both`, or one `.claude/agents|skills` adapter exists); otherwise `false`.
   A malformed `config.json` creates no `config.toml`. After creation, the upgrade never raises `min_version` on its own. The repo owner sets the floor.
9. **Check.** `check_requirements(project_root, requirements, *, claude_config_dir, family_stamp, cli_version) -> tuple[RequirementRow, ...]`. The CLI wrapper reads the inputs: `resolve_claude_config_dir()` (`dummyindex/context/domains/memory/miner/resolve.py:18`, honours `CLAUDE_CONFIG_DIR`), and the family stamp through the existing `--versions` reader (`dummyindex/cli/check.py:274-461`). Rows are `satisfied`, `missing`, `version-mismatch`, `unknown` or `invalid`. `check` exits 0 when no row is `missing` or `version-mismatch`, and 3 otherwise. Presence rules:
   - plugin: enabled in project, local or user settings, and present in `<config_dir>/plugins/installed_plugins.json`. A project-scope record counts only when its `projectPath` is this repo. `installed_plugin_record(target, *, config_dir, project_root)` moves to `dummyindex/context/claude_plugins.py`, and `cli/equip/plugin_state.py` re-exports it. An unreadable registry or an unparseable recorded version gives `unknown`. A dev's explicit `enabledPlugins: false` gives `missing` with the reason `disabled by you`.
   - skill `dummyindex`: family stamp ≥ `min_version`. Skill `plugin:<id>`: that plugin row. Skill `project`: `.claude/skills/<name>/SKILL.md` or `.agents/skills/<name>/SKILL.md` exists.
   - equipment (only when `require_native_adapters`): each project-scoped generated item's adapter exists. Task-scoped items are never checked.
   - dummyindex: CLI ≥ `min_version`. An unparseable CLI version (a dev build) gives `unknown`.
   Extras never fail the check.
10. **Sync.** `dummyindex context requirements sync [--yes] [--local-only]`.
    - Local files, always: native adapters from the committed manifest (when `require_native_adapters`); the skill family through `dummyindex install --scope user --skill-only` run by the injected `Runner`.
    - Plugins, only without `--local-only`: through the `context wire` path (`_wire_plugin`, `dummyindex/cli/wire.py:191`). A plugin is trusted only when its `(marketplace name, repo)` pair matches a `DEFAULT_PLUGINS` entry or a `SEED_MARKETPLACES` entry with `trusted=True` (`dummyindex/context/domains/equip/plugins/marketplace.py:48-64`). `config.toml` content never grants trust. A trusted plugin installs without a prompt. An untrusted plugin asks y/N per plugin on a TTY. `--yes` approves without a prompt (for CI). Without a TTY and without `--yes`, the plugin is skipped and listed.
    - Sync never deletes extras and never changes a dev's explicit `enabledPlugins: false`.
11. **Hard gate.** A `UserPromptSubmit` command in the new `dummyindex/context/hooks_requirements.py` (own sentinel `DUMMYINDEX_REQUIREMENTS`, never passed through `_guard_body`). Its shell body, in order:
    1. no `"$CLAUDE_PROJECT_DIR/.context/config.toml"` → `exit 0`;
    2. fast path: `.context/cache/requirements.ok` newer than `config.toml`, `equipment.json` and the settings and registry files → `exit 0`;
    3. no `dummyindex` on PATH → print a block JSON with the install command;
    4. otherwise `dummyindex context requirements gate`.
    The `gate` command reads the hook stdin JSON. A prompt that starts with `/dummyindex`, `/plugin`, `/clear` or `/exit` passes. It blocks (`{"decision":"block","reason":…}`, exit 0) only when a row is `missing` or `version-mismatch`. The reason lists each unmet row and its fix: `dummyindex context requirements sync` run in a separate terminal (then resend), `/plugin install <id>`, or the CLI install command. It also names the bypass. Rows that are `unknown` or `invalid`, a malformed `config.toml`, and any internal error pass the prompt with an `additionalContext` warning (fail-open), because those are not proven gaps. All satisfied → write `requirements.ok` and print nothing. The hook entry sets `timeout: 20`; a timeout passes the prompt.
    Bypass: `dummyindex context requirements bypass --hours N` (1–24) writes the gitignored `.context/cache/requirements-bypass.json`. While it is valid, the gate passes and adds a warning. The environment variable `DUMMYINDEX_ALLOW_UNMET_REQUIREMENTS=1` does the same.
12. **Reach on a fresh clone.** A user-scope Claude `dummyindex install` writes the requirements hooks into `<claude_config_dir>/settings.json`. The global gate defers only when the project settings contain the `DUMMYINDEX_REQUIREMENTS` sentinel, which is tested with a shell `grep`, not a Python spawn. Old local hooks do not mute it. Limit: a dev with no dummyindex CLI, on a repo whose `.claude/` is gitignored, has no hook that can fire. The committed guidance (CLAUDE.md/AGENTS.md block) names the install command. This is documented, not solved.
13. **Gitignored `.claude/`.** The upgrade runs `git check-ignore -q .claude/settings.json` through the injected git runner (`dummyindex/context/git.py`). When it is ignored, the upgrade prints one warning: `.claude/ is gitignored — teammates get this setup from .context/config.toml via the global dummyindex hooks`. It never edits `.gitignore`.

### C — mandatory `.context/` upgrade

14. **One pipeline.** `upgrade_project(project_root, *, package_version, refresh: RefreshResult | None = None, runner) -> UpgradeReport` in the new `dummyindex/context/build/context_upgrade.py`. Each step is contained (pattern `_attempt`, `dummyindex/context/build/upgrade.py:490`):
    1. the deterministic refresh: `refresh_deterministic_artifacts(..., advance_stamp=False)` (new parameter; the cache stays scoped to the version). It is skipped when the caller passes its own `refresh` result. It never re-clusters;
    2. `config.toml` creation (contract 8) and the `requested_by="legacy"` backfill;
    3. equipment: re-render pristine bodies (`refresh`, `lifecycle/status.py:200`), write grounding sidecars, write and upgrade native adapters (when Claude wiring exists), and report specialists without evidence;
    4. a refresh of the managed project hooks when the project already has managed hooks, so old repos get the gate;
    5. the `.claude/` gitignore warning;
    6. the stamp, through the public `advance_version_stamp` (renamed `_advance_version_stamp`, `dummyindex/context/build/enriched_refresh.py:305`), as the true last step. Any failed step leaves the stamp, so the next run retries.
    Before any write or delete, every manifest path must resolve inside `.context/equipment/` or `.claude/{agents,skills}/`. Other paths are skipped and reported. When the stamp is newer than the CLI, steps 1–4 do nothing and the report says `stamp newer than CLI`. The upgrade never deletes files and never installs plugins. A second run changes nothing.
15. **Lock.** `.context/cache/upgrade.lock` (`O_EXCL`; stale after 10 minutes). When the lock is held, the run exits 0 and prints `upgrade in progress`.
16. **Always runs.**
    - `install` (`project_init.py`), `context init` (`cli/init.py`) and the Codex path (`installer/install/orchestrate.py:318-323`) call `upgrade_project` with the refresh result they already have. `_refresh_equipment_step` is deleted. The existing `config.json` migration order and the opt-out byte-stability rules stay.
    - A SessionStart command runs one sequential shell body. It compares the `meta.json` stamp with the CLI version baked into the hook body at install time, in shell. Equal → `exit 0` with no spawn. Different → `dummyindex context upgrade --if-stale` (proper compare, lock, upgrade), then `dummyindex context requirements sync --local-only`. Its first output line is `dummyindex: upgraded .context/ to <v>` or nothing. When the upgrade wrote adapters, the output adds `restart Claude Code to load new agents`. The global copy of this command checks `meta.json`, not `config.toml`.
    - The update skill states that the upgrade is automatic and drops the manual `equip refresh` fallback.

### D — GC retires task-scoped agents

17. **Provenance.** `EquipmentItem` gains `scope: EquipmentScope` (`project` default, `task`) and `task_refs: tuple[str, ...]` (each `proposal:<slug>` or `audit:<slug>`). Default values are not serialised, so v4 manifests stay byte-identical. When `equip apply --for-proposal <slug>` writes an item that the baseline catalog (no proposal, no carry-forward) does not generate, the item gets `scope=task`, `requested_by=proposal` and `proposal:<slug>` in `task_refs`. When a later baseline apply also generates it, it becomes `scope=project` with empty `task_refs`. `specialist_caps_from_manifest` carries forward project-scoped items, items with `requested_by` in {`add_specialist`, `legacy`}, and task-scoped items with at least one live ref.
18. **Candidates.** The GC adds `CandidateKind.EQUIPMENT`. An item is a candidate when:
    - it is task-scoped and every ref is finished: the proposal `status` is `done` or `superseded`, or the audit is closed, or the workspace is gone; or
    - it is a `legacy` or unrequested generated specialist that the current baseline catalog does not produce (for example, a db specialist with no data-store evidence).
    Pristine task-scoped → `delete`. Pristine legacy without evidence → `review`. User-modified, evolved or sourced → `review`. A ref to an `in_progress` proposal or a partial checklist blocks the item (`_liveness_block`, `dummyindex/context/domains/gc/delete.py:234`; the liveness readers move to `gc/liveness.py`). Items with `requested_by=add_specialist` are never candidates.
19. **Delete.** `dummyindex context gc delete --kind equipment --slug <item-name> [--yes] [--force]` checks path containment, removes the adapter, then calls `remove_item(..., delete_file=True)` (`dummyindex/context/domains/equip/lifecycle/remove.py:38`). It drops the item from `config.toml`. The library entry is kept, so `equip reuse` can restore it. A user-modified body needs `--force`, which the GC skill passes only after the user confirms that item. Each deletion is user-confirmed, as for every GC deletion.
20. **Sweep cascade.** The GC report lists, under each proposal or audit candidate, the task-scoped items it orphans. `gc signal` counts equipment candidates.

### Invariants

- Tests never touch the real `~/.claude`. Tests rely on the autouse isolation in `tests/conftest.py:10-35`. Plugin-install tests unset `SKIP_INSTALL_ENV` and inject a fake runner. A test with `CLAUDE_CONFIG_DIR` set covers the alternate profile.
- No network and no real `git` in tests. Git and `claude` run through injected runners.
- Never-clobber: hashes own only their recorded paths. A user-modified body, adapter or hand-edited `config.toml` line is never overwritten.
- No bare rebuild and no re-clustering anywhere in the upgrade.
- New tests carry `@pytest.mark.unit` or `@pytest.mark.integration` (`--strict-markers`).

## Acceptance

- [ ] `test_equip_adapters.py`: the adapter carries the body description. Sanitiser cases: a multi-line `>-` block, a colon, a quote, `#`, a leading `-`, an inner `---`, 400 characters, non-ASCII, empty (gives the generic fallback), no frontmatter, a CRLF body. The output is valid YAML, one line, ≤ 300 characters.
- [ ] `test_equip_adapters.py`: a pre-fix generic adapter is replaced on apply. An adapter rendered with description X is updated to Y after the template description changes. A CRLF adapter is pristine. A hand-edited adapter stays with `(user-owned)`. `equip remove --delete-file` and `equip uninstall` remove a new-format adapter.
- [ ] `test_equip.py` detect cases: no evidence; `sqlalchemy` dependency; `*.sql` only; `migrations\` with a Windows separator; `faiss-cpu`; `lunr` inside a README sentence does not count; a fixture that mirrors this repo gives no db and no search evidence.
- [ ] `test_equip_catalog.py` / `test_equip_specialists.py`: a profile with no evidence generates no db or search specialist. `sqlalchemy` generates db. `add-specialist db` generates db with no evidence. The expected counts come from named sets (`_ALWAYS_ON`, `_EVIDENCE_GATED`).
- [ ] An upgrade test on a manifest with a pristine db specialist and no evidence: the item gets `requested_by=legacy`, the body and adapter stay, and the report has `specialist without evidence`.
- [ ] `test_equip_grounding.py`: for a 3-feature fixture, the sidecar names each `feature_id` and one `concerns.md` citation. It is ≤ 6,000 bytes for a 50-feature fixture with non-ASCII summaries, and is cut on a line boundary. Two temp copies of one `.context/` give byte-identical sidecars. A CRLF `concerns.md` gives the same bytes. An empty `.context/` gives a sidecar with only the header. The body render is byte-identical before and after a feature-doc edit.
- [ ] Every one of the 17 templates renders with no `{{` left and without `the project's stack`, both with and without a framework. `test_equip_specialist_invariants.py` stays green.
- [ ] `test_toml_io.py`: parse → render → parse is equal, and a second render is byte-identical. Unknown top-level keys and unknown `[[plugins]]` keys are kept. A line-level `min_version` edit keeps comments. CRLF, BOM, empty file, `schema_version = 2`, a duplicate `id`, a bad `from` and `~=1.0` give the stated results. The `tomli` fallback is covered by patching `sys.modules["tomllib"] = None`.
- [ ] `test_seed.py`: a `config.json` with 4 `wired` plugins seeds 4 `[[plugins]]` plus the skill family. With `default_plugins_enabled=false`, no defaults are seeded. A malformed `config.json` creates no `config.toml` and keeps its bytes. A `.dev` CLI version leaves out `min_version`.
- [ ] `test_config.py`: with `config.toml` present, `read_config().wired` equals the toml list. `equip install` write-back and `reconcile_wired_with_equipment` change `config.toml` and leave `config.json` `wired` untouched.
- [ ] `test_check.py` (temp config dir; also a `CLAUDE_CONFIG_DIR` case): satisfied → exit 0. Missing plugin, plugin below `version`, plugin enabled `false` by the dev, missing project skill, missing adapter (`require_native_adapters=true`) and CLI below `min_version` each give their row and exit 3. A project-scope record for another repo gives `missing`. An unreadable registry and a dev CLI version give `unknown` and exit 0. An extra plugin changes nothing. Task-scoped items are not checked.
- [ ] `test_sync.py`: a deleted `.claude/agents/<name>.md` is restored. A trusted `(name, repo)` plugin installs through the fake runner. An untrusted one is skipped without a TTY and without `--yes`, and is installed with `--yes`. A toml entry that claims `claude-plugins-official` with a different repo is untrusted. `--local-only` makes no runner call for plugins. An `enabledPlugins:false` entry is left as is.
- [ ] `test_gate.py`: unmet → block JSON that lists each row with its fix and names the bypass. Met → no output, and `requirements.ok` is written. `/dummyindex-update` and `/plugin install x` prompts pass. Malformed stdin is gated like a normal prompt. A forced internal error, an `unknown` row and an invalid `config.toml` pass with a warning. A valid bypass file or the bypass env var passes with a warning. An expired bypass file is ignored. No `config.toml` → no output.
- [ ] `test_hooks_requirements.py` runs each shell body through the native shell with a restricted `PATH`: no `config.toml` → exit 0 and no output. CLI absent with `config.toml` → block JSON with the install command. A fresh `requirements.ok` → no spawn. The global gate runs although local hooks without the requirements sentinel exist. The global upgrade body runs on a `0.30.0` stamp with no `config.toml`. An equal stamp → no spawn. `test_hooks.py` count and order assertions are updated to named constants, and the existing entries keep their positions.
- [ ] `test_context_upgrade.py`: a `0.30.0` stamp → after `upgrade --if-stale`, `config.toml`, the pristine bodies, the sidecars, the adapters and then the stamp are current. A second run reports no changes. A step-3 failure leaves the stamp, and the next run retries. A newer stamp changes nothing. A path outside the allowed roots is skipped. Two concurrent runs leave a valid state and one reports `upgrade in progress`. `features/INDEX.json` is byte-identical before and after. The `.claude/` gitignore warning is printed once, and not on the second run.
- [ ] `test_upgrade_cli.py`: with the stamp current, `context upgrade --if-stale` writes nothing and does not import `tree_sitter` (subprocess check of `sys.modules`).
- [ ] `test_install.py`: `upgrade_project` is called once per repo pass on both the enriched path and the full-build path with the existing refresh result. An unequipped repo gets no `equipment.json`. The opt-out and malformed-config byte-stability tests (`:2715-2764`) stay green. The tests that import `_refresh_equipment_step` (`:2899-2953`) are rewritten as behaviour tests. A user-scope install writes only the requirements hooks to the temp config dir.
- [ ] `test_equip_apply_merge.py`: `--for-proposal p1` that signals `frontend` on a backend fixture records the frontend specialist as `scope=task`, `task_refs=["proposal:p1"]`, `requested_by=proposal`. Baseline items write no `scope` key. A later baseline apply promotes a shared item to `project`. A golden-bytes test shows that a v4 manifest without the new fields serialises identically.
- [ ] `test_equipment_candidates.py`: `p1` `done` → its pristine task item is `delete`. `p1` `in_progress` → blocked. Refs `p1` (done) and `p2` (in progress) → not a candidate. A user-modified copy → `review`. A legacy pristine db specialist with no evidence → `review`. An `add_specialist` item → never a candidate.
- [ ] `test_equipment_delete.py` / `test_gc_cli.py`: `gc delete --kind equipment --slug <name> --yes` removes the body, the adapter and the manifest entry, drops the item from `config.toml` and keeps the library entry. A user-modified body without `--force` exits non-zero and changes nothing. A path outside the allowed roots is refused.
- [ ] Doc and skill tests: `test_cli_doc_sync.py` covers `requirements check|sync|gate|bypass`, `upgrade --if-stale` and `gc delete --kind equipment`. `test_skills_doc_hygiene.py:503-514` asserts the new automatic-upgrade text instead of the manual `equip refresh` text. The doc budget ratchets pass.
- [ ] `uv run pytest -q` passes, and `uv run ruff check .` is clean.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `equip`
- `equip`
- `session-memory`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
