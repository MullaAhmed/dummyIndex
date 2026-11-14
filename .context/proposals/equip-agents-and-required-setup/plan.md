# Plan — Fix weak task-specific agents and add a hard-gated, shareable required-setup manifest (.context/config.toml)

> Ordered tasks in dependency order. Each task names its files and the symbols it reuses (from `.context/map/symbols.json`). Spec contract numbers are in brackets. The build close-out (recouncil of `equip`, `install-surface` and `gc` docs, then `reconcile-stamp`) is automatic and is not a task here.

## Tasks

### Foundations

1. **Equip enums + models** [3, 17] — `dummyindex/context/domains/equip/enums.py`: add `RequestedBy` (`add_specialist`, `proposal`, `legacy`) and `EquipmentScope` (`project`, `task`). `dummyindex/context/domains/equip/models.py`: add `EquipmentItem.requested_by`, `scope` and `task_refs`, each serialised only when it is not the default (same rule as `dimension`). Add `StackProfile.data_stores` and `search_backends`, which never enter `project_binding`. Tests: `tests/context/domains/equip/test_equip_manifest_v3.py` (golden bytes for a v4 manifest without the new fields, and a round-trip with them).

2. **Move fresh-render helpers into the domain** [5] — create `dummyindex/context/domains/equip/generate/fresh.py`. Move into it, unchanged, `fresh_rendered`, `fresh_renders`, `specialist_caps_from_manifest`, `drop_generated_stems`, `filter_grounding_docs` and `project_slug` from `dummyindex/cli/equip/common.py:115-236`. `cli/equip/common.py` re-exports them, and the `drop_generated_stems` docstring is corrected. Tests: the existing equip suite stays green, with no import changes in tests.

3. **Requirements package: model + TOML I/O + seed** [6, 8] — new `dummyindex/context/domains/requirements/` with these modules:
   - `__init__.py`: the re-export surface, like `gc/__init__.py`.
   - `errors.py`: `RequirementsError`.
   - `enums.py`: `RequirementStatus`, `RequirementKind`, `SkillOrigin`.
   - `constants.py`: `CONFIG_TOML_REL`, `BYPASS_ENV`, `BYPASS_REL`, `OK_MARKER_REL`, `SCHEMA_VERSION`.
   - `models.py`: frozen `Requirements`, `PluginRequirement`, `SkillRequirement`, `RequirementRow`, each with `extra` for unknown keys.
   - `toml_io.py`: `read_requirements`, `render_requirements`, `write_requirements`, `set_min_version_line`. It uses the tomllib/tomli pattern from `dummyindex/codex_guidance.py:16-18` and `write_text_atomic`.
   - `seed.py`: `seed_requirements(wired, *, default_plugins_enabled, cli_version, claude_wired) -> Requirements`. It takes plain `WiredEntry` data from `dummyindex/context/default_plugins.py`, never `Config`.

   Tests: new `tests/context/domains/requirements/__init__.py`, `test_toml_io.py`, `test_seed.py`.

4. **Plugin registry reader** [9] — `dummyindex/context/claude_plugins.py`: add `installed_plugin_record(target, *, config_dir, project_root)`. It is moved from `_installed_plugin_record` (`dummyindex/cli/equip/plugin_state.py:124`), takes the config dir (from `resolve_claude_config_dir`, `dummyindex/context/domains/memory/miner/resolve.py:18`) and matches project-scope records by `projectPath`. `plugin_state.py` calls it with the resolved dir. Tests: `tests/context/test_claude_plugins.py` (alt config dir, project-scope mismatch, undecodable registry).

5. **Refresh without the stamp** [14] — `dummyindex/context/build/enriched_refresh.py`: add `advance_stamp: bool = True` to `refresh_deterministic_artifacts`. Rename `_advance_version_stamp` to the public `advance_version_stamp`, and keep the old name as an alias. Tests: `tests/context/build/` (with `advance_stamp=False` the stamp is unchanged and the cache is still version-scoped).

### Agents

6. **Adapter description + structural ownership** [1, 2] — in `dummyindex/context/domains/equip/generate/adapters.py`, add `adapter_description(body_text)`, `native_adapter_content(item, *, description=None)` and `_own_description(text)`. `_own_description` parses the adapter's `description:` line. Apply the structural pristine rule in `write_native_adapter` and `remove_native_adapter`. Tests: `tests/context/domains/equip/test_equip_adapters.py` (existing `:49-58`, `:98-109` stay byte-identical with `description=None`).

7. **Evidence detection** [3] — `dummyindex/context/domains/equip/generate/detect.py`: `_DATA_STORE_TOKENS`, `_SEARCH_TOKENS` and `_DB_FILE_PATTERNS`. They use word-boundary regexes over the manifests that `_detect_frameworks` (`detect.py:183`) scans, plus `map/files.json` paths. Tests: `tests/context/domains/equip/test_equip.py` (detect cases from the acceptance list).

8. **Grounding sidecar + template slots** [4] — new `dummyindex/context/domains/equip/generate/grounding.py`: `render_grounding(context_dir, *, capability, budget=6000) -> str`, `_FOCUS_QUERIES`, `grounding_path(name)`. It reuses `query` (`dummyindex/context/domains/query.py:271`) and reads `features/INDEX.json`, `feature.json` and `concerns.md`. `dummyindex/context/domains/equip/generate/render.py`: add the `{{framework_clause}}` and `{{focus_query}}` slots, and remove `_NO_FRAMEWORK`. All 17 templates in `dummyindex/skills/equip/templates/*.md.tmpl` (not `sourced-overlay.md.tmpl`) change. Replace `(framework: {{framework}})` with `{{framework_clause}}`, also in the line-wrapped form (for example `docs-specialist-agent.md.tmpl:11`). Add the fixed block that names `.context/equipment/grounding/<name>.md` and `dummyindex context query "{{focus_query}}"`.

   Tests: new `tests/context/domains/equip/test_equip_grounding.py`. Also, `test_equip.py:219,292` and `test_equip_specialists.py:247` (`"{{" not in body`) and `test_equip_specialist_invariants.py` stay green.

9. **Requirements check + gate** [9, 11] — two new modules:
   - `dummyindex/context/domains/requirements/check.py`: `check_requirements`. It reuses `installed_plugin_record` from task 4, `compare_versions` from `dummyindex/versioning.py:64` and `_effective_enabled` from `dummyindex/context/default_plugins.py`. It also reuses `load_settings` from `dummyindex/context/claude_settings.py` and `native_adapter_path`.
   - `gate.py`: `gate_decision(rows, *, prompt, bypass) -> GateDecision`, `read_bypass`, `write_bypass`, `write_ok_marker`.

   Tests: `tests/context/domains/requirements/test_check.py`, `test_gate.py`.

10. **Requirements hooks module** [11, 12, 16] — new `dummyindex/context/hooks_requirements.py` holds these parts:
    - The sentinel `DUMMYINDEX_REQUIREMENTS`.
    - The gate body and the SessionStart body, in local and global variants. They are written by hand, with `timeout: 20` on the gate.
    - The functions `install_requirements_hooks(settings_path, *, cli_version)` and `uninstall_requirements_hooks`. The CLI version is baked into the upgrade body.

    `dummyindex/context/hooks.py`: `install`/`uninstall` call these. No new bodies go inside `hooks.py`, which is already 686 lines.

    Tests: new `tests/context/test_hooks_requirements.py`. It runs the bodies through the native shell with a restricted `PATH`. The count and order assertions in `tests/context/test_hooks.py` (`:84`, `:103-106`, `:169-178`, `:1113`, `:1124-1126`, `:1170`) move to named constants. The existing entries keep their positions.

### Behaviour

11. **Gate specialists on evidence + carry-forward rules** [3, 17] — `dummyindex/context/domains/equip/generate/catalog.py`: `_all_templated_capabilities` forces db/search only with `profile.data_stores` / `profile.search_backends`. `dummyindex/context/domains/equip/generate/specialists.py`: mark db/search as evidence-gated. `fresh.py` `specialist_caps_from_manifest`: the carry-forward rule of contract 17. Tests: `tests/context/domains/equip/test_equip_catalog.py` (`:24,78,140,237,269`) and `test_equip_specialists.py` (`:60,204,219,270,544`) with `_ALWAYS_ON` and `_EVIDENCE_GATED` sets plus evidence and no-evidence fixtures.

12. **Requirements sync** [10] — `dummyindex/context/domains/requirements/sync.py`: `sync_requirements(project_root, requirements, *, approve, local_only, runner, confirm) -> SyncReport`. Adapters through `write_native_adapter` with the description (task 6). The skill family through `runner(["dummyindex", "install", "--scope", "user", "--skill-only"])`. Plugins through a domain copy of the `_wire_plugin` selection logic (`dummyindex/cli/wire.py:191`), which the CLI keeps calling. Trust comes from `DEFAULT_PLUGINS` and `SEED_MARKETPLACES` (`dummyindex/context/domains/equip/plugins/marketplace.py:48-64`), matched by `(name, repo)`. Tests: `tests/context/domains/requirements/test_sync.py`.

13. **Single owner for wired** [7] — `dummyindex/context/domains/config.py`: `read_config` derives `wired` from `read_requirements` when `config.toml` exists. `reconcile_wired_with_equipment` and `reconcile_default_plugins` write through `write_requirements` in that case. `dummyindex/cli/equip/install.py` `_write_back_wired` does the same. Tests: `tests/context/domains/test_config.py`, `tests/cli/equip/` write-back case.

14. **Adapter removal call sites** [2] — `dummyindex/context/domains/equip/lifecycle/remove.py:61-63` and `lifecycle/status.py:376-385` use the structural rule from task 6 (no body needed). Tests: `tests/context/domains/equip/test_equip_remove.py`, `test_equip_lifecycle.py`.

15. **Equip dispatch** [1, 4, 17] — `dummyindex/cli/equip/dispatch.py`: the three `write_native_adapter` calls (`:620`, `:727`, `:817`) pass the body description. `apply` and `refresh` write the grounding sidecars. `--for-proposal` stamps `scope`, `task_refs` and `requested_by` by comparison with a baseline `build_catalog`. `add-specialist` stamps `requested_by=add_specialist`. Apply reports specialists without evidence. Tests: `tests/context/domains/equip/test_equip_apply_merge.py`.

16. **GC equipment candidates** [18, 20] — changes by file:
    - `dummyindex/context/domains/gc/enums.py`: `CandidateKind.EQUIPMENT`.
    - New `dummyindex/context/domains/gc/liveness.py`: `_proposal_status` and `_checklist_partial` move here from `gc/delete.py:247,262`, and aliases stay.
    - New `dummyindex/context/domains/gc/equipment.py`: `enumerate_equipment_candidates(context_dir)`. It reuses `read_manifest`, `classify_item`, `is_user_owned`, `is_sourced`, `is_evolved` and `fresh_rendered` from task 2.
    - `gc/enumerate.py` appends them. `gc/recommend.py` maps them. `gc/scan.py` lists orphaned task items under each proposal or audit candidate. `gc/signals.py` counts them.

    Tests: new `tests/context/domains/gc/test_equipment_candidates.py`.

### Integration

17. **Upgrade pipeline** [13, 14, 15] — new `dummyindex/context/build/context_upgrade.py`: `upgrade_project`, `is_stale(context_dir, cli_version)`, `_acquire_lock`, `_contained(root, rel)`. It reuses these symbols:
    - `refresh_deterministic_artifacts(advance_stamp=False)` and `advance_version_stamp` (task 5).
    - `seed_requirements` and `write_requirements` (task 3).
    - equip `refresh` (`lifecycle/status.py:200`) and `fresh_renders` (task 2).
    - `render_grounding` (task 8) and `write_native_adapter` (task 6).
    - `install_requirements_hooks` and `hooks.install` (task 10), for repos with managed hooks.
    - `dummyindex/context/git.py` for `check-ignore`.

    Tests: new `tests/context/build/test_context_upgrade.py`.

18. **Requirements CLI** [9-11] — new `dummyindex/cli/requirements.py` (`context requirements check|sync|gate|bypass`). It reads the claude config dir, the family stamp and the CLI version, then calls the domain. The family stamp reader is in `dummyindex/cli/check.py:274-461`. `ContextSubcommand.REQUIREMENTS` in `dummyindex/context/enums.py:101`, registration in `dummyindex/cli/__init__.py:113`. `dummyindex/cli/wire.py` and `dummyindex/cli/status.py` pass skill presence through the `is_present` callback. Tests: new `tests/cli/test_requirements_cli.py`.

19. **GC delete for equipment** [19] — `dummyindex/context/domains/gc/delete.py`: route `CandidateKind.EQUIPMENT` to `delete_equipment_item(root, name, *, force)` (containment check, adapter removal, `remove_item(..., delete_file=True)` from `lifecycle/remove.py:38`, `config.toml` drop). `dummyindex/cli/gc.py`: `--kind equipment` and `--force`. Tests: new `tests/context/domains/gc/test_equipment_delete.py`, `tests/cli/test_gc_cli.py`.

### Wiring + docs

20. **Upgrade CLI + help/docs** [16] — new `dummyindex/cli/upgrade.py` (`context upgrade [--if-stale]`). The stale check runs before heavy imports. `ContextSubcommand.UPGRADE`, registration, and `dummyindex/cli/help.py`, `docs/COMMANDS.md` and `docs/guide/07-cli.md` for `requirements`, `upgrade` and `gc delete --kind equipment`. Tests: new `tests/cli/test_upgrade_cli.py`, `tests/cli/test_cli_doc_sync.py` (add `RequirementsVerb` parametrisation) and `test_cli_doc_sync_policy_canary.py`.

21. **Installer always upgrades** [12, 16] — `dummyindex/installer/install/project_init.py`: call `upgrade_project` with the refresh result on both paths (`:67`, `:114`). Delete `_refresh_equipment_step` and its re-export (`installer/install/__init__.py:24,36`). `dummyindex/cli/init.py` and `dummyindex/installer/install/orchestrate.py:318-323` call the same helper. A user-scope Claude install calls `install_requirements_hooks` on the claude config dir. Tests: `tests/test_install.py` (`:2899-2953` rewritten, `:2715-2764` stay green) and `tests/cli/test_init_cli.py`.

22. **Skill and guidance text** [16, 18-20] — four files change:
    - `dummyindex/skills/update/SKILL.md`: the upgrade is automatic, with no manual fallback.
    - `dummyindex/skills/equip/SKILL.md`: `config.toml`, `requirements sync` and the grounding sidecar.
    - `dummyindex/skills/gc/SKILL.md`: equipment candidates, per-item confirmation, and `--force` only after confirmation.
    - `dummyindex/context/output/instructions.py`: the generator of `HOW_TO_USE.md` and `playbooks/gc-context.md`. Never hand-edit `.context/`.

    Tests: `tests/test_skills_doc_hygiene.py:503-514`, `tests/context/output/test_instructions.py`, doc budget ratchets (`tests/cli/test_check_budget.py`, `tests/data/skill-budget.txt`).

23. **Verify** — `uv run pytest -q` and `uv run ruff check .`, then review the diff.
