# Checklist — Fix weak task-specific agents and add a hard-gated, shareable required-setup manifest (.context/config.toml)

> Waves run in order. Items inside one wave touch disjoint files. Tick `- [x]` only after the item's tests pass. Task numbers refer to `plan.md`.

## Wave 1 — foundations

- [x] T1 Equip enums + models: `RequestedBy`, `EquipmentScope`, `EquipmentItem.requested_by/scope/task_refs`, `StackProfile.data_stores/search_backends`. Add a golden-bytes v4 test (`dummyindex/context/domains/equip/enums.py`, `dummyindex/context/domains/equip/models.py`, `tests/context/domains/equip/test_equip_manifest_v3.py`)
- [x] T2 Move fresh-render helpers to `dummyindex/context/domains/equip/generate/fresh.py` and re-export them from `dummyindex/cli/equip/common.py`. The equip suite stays green
- [x] T3 Requirements package: `__init__`, `errors`, `enums`, `constants`, `models`, `toml_io`, `seed` (`dummyindex/context/domains/requirements/`, `tests/context/domains/requirements/__init__.py`, `test_toml_io.py`, `test_seed.py`)
- [x] T4 `installed_plugin_record(target, *, config_dir, project_root)` in `dummyindex/context/claude_plugins.py`. `dummyindex/cli/equip/plugin_state.py` uses it (`tests/context/test_claude_plugins.py`)
- [x] T5 `refresh_deterministic_artifacts(advance_stamp=...)` + public `advance_version_stamp` (`dummyindex/context/build/enriched_refresh.py`, `tests/context/build/test_enriched_refresh_stamp.py`)

## Wave 2 — agents core + requirements core

- [x] T6 Adapter description + structural ownership (`dummyindex/context/domains/equip/generate/adapters.py`, `tests/context/domains/equip/test_equip_adapters.py`)
- [x] T8 Grounding sidecar + `{{framework_clause}}`/`{{focus_query}}` slots + 17 templates (`dummyindex/context/domains/equip/generate/grounding.py`, `dummyindex/context/domains/equip/generate/render.py`, `dummyindex/skills/equip/templates/*.md.tmpl`, `tests/context/domains/equip/test_equip_grounding.py`)
- [x] T9 Requirements check + gate decision (`dummyindex/context/domains/requirements/check.py`, `dummyindex/context/domains/requirements/gate.py`, `tests/context/domains/requirements/test_check.py`, `test_gate.py`)
- [x] T10 Requirements hooks module + `hooks.install/uninstall` calls. `test_hooks.py` counts move to named constants (`dummyindex/context/hooks_requirements.py`, `dummyindex/context/hooks.py`, `tests/context/test_hooks_requirements.py`, `tests/context/test_hooks.py`)

## Wave 3 — evidence, sync, single owner, removal

- [x] T7 Evidence detection with word-boundary tokens and file patterns (`dummyindex/context/domains/equip/generate/detect.py`, `tests/context/domains/equip/test_equip.py`)
- [x] T12 Requirements sync: adapters, skill family via runner, plugins with `(name, repo)` trust (`dummyindex/context/domains/requirements/sync.py`, `tests/context/domains/requirements/test_sync.py`)
- [x] T13 `config.toml` as single owner of `wired` (`dummyindex/context/domains/config.py`, `dummyindex/cli/equip/install.py`, `tests/context/domains/test_config.py`, `tests/cli/equip/test_equip_install_writeback.py`)
- [x] T14 Structural adapter removal at `remove` and `uninstall` (`dummyindex/context/domains/equip/lifecycle/remove.py`, `dummyindex/context/domains/equip/lifecycle/status.py`, `tests/context/domains/equip/test_equip_remove.py`, `tests/context/domains/equip/test_equip_lifecycle.py`)

## Wave 4 — gating, upgrade pipeline, requirements CLI

- [x] T11 Evidence-gated db/search specialists + carry-forward rule. Catalog/specialist count tests use `_ALWAYS_ON`/`_EVIDENCE_GATED` (`dummyindex/context/domains/equip/generate/catalog.py`, `dummyindex/context/domains/equip/generate/specialists.py`, `dummyindex/context/domains/equip/generate/fresh.py`, `tests/context/domains/equip/test_equip_catalog.py`, `tests/context/domains/equip/test_equip_specialists.py`)
- [x] T17 Upgrade pipeline with lock, containment, stamp-last, newer-stamp no-op, gitignore warning (`dummyindex/context/build/context_upgrade.py`, `tests/context/build/test_context_upgrade.py`)
- [x] T18 Requirements CLI `check|sync|gate|bypass`. `is_present` skill presence in `wire`/`status` (`dummyindex/cli/requirements.py`, `dummyindex/context/enums.py`, `dummyindex/cli/__init__.py`, `dummyindex/cli/wire.py`, `dummyindex/cli/status.py`, `tests/cli/test_requirements_cli.py`)

## Wave 5 — equip dispatch + GC candidates

- [x] T15 Equip dispatch: adapter descriptions, sidecar writes, `--for-proposal` provenance, `add-specialist` stamp, evidence report (`dummyindex/cli/equip/dispatch.py`, `tests/context/domains/equip/test_equip_apply_merge.py`)
- [x] T16 GC equipment candidates + liveness move + recommend/scan/signal (`dummyindex/context/domains/gc/enums.py`, `dummyindex/context/domains/gc/liveness.py`, `dummyindex/context/domains/gc/equipment.py`, `dummyindex/context/domains/gc/enumerate.py`, `dummyindex/context/domains/gc/recommend.py`, `dummyindex/context/domains/gc/scan.py`, `dummyindex/context/domains/gc/signals.py`, `tests/context/domains/gc/test_equipment_candidates.py`)

## Wave 6 — GC delete, upgrade CLI, installer, docs

- [ ] T19 GC delete for equipment with `--force` (`dummyindex/context/domains/gc/delete.py`, `dummyindex/cli/gc.py`, `tests/context/domains/gc/test_equipment_delete.py`, `tests/cli/test_gc_cli.py`)
- [ ] T20 `context upgrade [--if-stale]` + help and docs for `requirements`, `upgrade`, `gc delete --kind equipment` (`dummyindex/cli/upgrade.py`, `dummyindex/context/enums.py`, `dummyindex/cli/__init__.py`, `dummyindex/cli/help.py`, `docs/COMMANDS.md`, `docs/guide/07-cli.md`, `tests/cli/test_upgrade_cli.py`, `tests/cli/test_cli_doc_sync.py`)
- [ ] T21 Installer, `context init` and the Codex path call `upgrade_project`. Delete `_refresh_equipment_step`. A user-scope install writes the requirements hooks (`dummyindex/installer/install/project_init.py`, `dummyindex/installer/install/__init__.py`, `dummyindex/installer/install/orchestrate.py`, `dummyindex/cli/init.py`, `tests/test_install.py`, `tests/cli/test_init_cli.py`)
- [ ] T22 Skill and guidance text for the update, equip and gc skills. Also the `instructions.py` generator (`dummyindex/skills/update/SKILL.md`, `dummyindex/skills/equip/SKILL.md`, `dummyindex/skills/gc/SKILL.md`, `dummyindex/context/output/instructions.py`, `tests/test_skills_doc_hygiene.py`, `tests/context/output/test_instructions.py`, `tests/data/skill-budget.txt`)

## Wave 7 — acceptance

- [ ] Acceptance: adapter tests in `test_equip_adapters.py` cover the sanitiser cases, the legacy and description-change upgrade, CRLF, user-owned keep and new-format removal
- [ ] Acceptance: detect, catalog and specialist tests show no db/search specialist without evidence. They show db with `sqlalchemy` and db on an explicit ask. A fixture that mirrors this repo has no evidence
- [ ] Acceptance: `test_context_upgrade.py` shows `legacy` backfill and the `specialist without evidence` report with no deletion
- [ ] Acceptance: `test_equip_grounding.py` shows the sidecar content and the 6,000-byte line-boundary cut. It shows byte-identical output across two copies and CRLF. Body bytes stay unchanged after a feature-doc edit. All 17 templates render with no `{{` and no `the project's stack`
- [ ] Acceptance: `test_toml_io.py`, `test_seed.py` and `test_config.py` show lossless round-trip and comment-keeping line edits. They show invalid-file cases, the `tomli` fallback, seeding rules and the single owner of `wired`
- [ ] Acceptance: `test_check.py`, `test_sync.py` and `test_gate.py` show every row status and exit code. They show the `CLAUDE_CONFIG_DIR` case and the `(name, repo)` trust rule. They show the allowlisted prompts, fail-open cases and the bypass
- [ ] Acceptance: `test_hooks_requirements.py` shows that the shell bodies block on a missing CLI and skip with no `config.toml`. They skip the spawn on a fresh `requirements.ok` or an equal stamp. They run globally despite old local hooks
- [ ] Acceptance: `test_context_upgrade.py` and `test_upgrade_cli.py` show the full upgrade, the no-op second run and retry after a failed step. They show the newer-stamp no-op, path containment and the lock under two concurrent runs. They show `features/INDEX.json` byte-identity and the single gitignore warning. They show no `tree_sitter` import on a current stamp
- [ ] Acceptance: `test_install.py` shows `upgrade_project` once per repo pass on both paths. It shows opt-out and malformed-config byte stability. It shows user-scope requirements hooks in the temp config dir
- [ ] Acceptance: `test_equip_apply_merge.py`, `test_equipment_candidates.py`, `test_equipment_delete.py` and `test_gc_cli.py` show task provenance and promotion. They show the candidate and liveness rules. They show deletion of the body, adapter, manifest and `config.toml` entry, with the library kept. They show the `--force` refusal
- [ ] Acceptance: `uv run pytest -q` passes and `uv run ruff check .` is clean
- [ ] Review the full diff — via /code-review
