# Checklist — dummyindex internally uses ponytail: reviewed default plugin plus default-on subagent mandate

> Derived from plan tasks + spec Acceptance. Tick `- [x]` only after verifying.
> New code carries no long comments.

## Wave 1 — independent surfaces

- [x] Append the ponytail `DefaultPlugin` record and fix the tuple comment; update and add tests (`dummyindex/context/default_plugins.py`, `tests/context/test_default_plugins.py`, `tests/context/domains/test_config.py`, `tests/test_install.py`) — plan task 1
- [x] Replace the Ponytail sentence with the default-on text; update hygiene tests (`dummyindex/skills/build/SKILL.md`, `dummyindex/skills/plan/SKILL.md`, `dummyindex/skills/equip/SKILL.md`, `tests/test_skills_doc_hygiene.py`) — plan task 2
- [x] Add the ponytail default bullet, Codex sentence and count fixes outside the anchors; extend doc-sync tokens (`dummyindex/skills/skill.md`, `docs/COMMANDS.md`, `docs/guide/07-cli.md`, `tests/cli/test_cli_doc_sync.py`) — plan task 3

## Wave 2 — dogfood + reconcile

- [x] Backfill `ponytail@ponytail` into this repo's `.context/config.json` via `reconcile_default_plugins(Path(".context"), platform="both")` — plan task 4
- [x] Rewrite the Ponytail bullet in `.context/features/equip/spec.md` to the default-on rule; grep verifiers pass — plan task 5

## Wave 3 — acceptance

- [ ] Acceptance: `DEFAULT_PLUGINS[-1]` equals the spec record; the exact-records test pins all four in order
- [ ] Acceptance: `describe_default_plugin_trust()` returns 3 lines; `lines[2]` equals the spec's ponytail trust line
- [ ] Acceptance: `wire_default_plugins` declares marketplace `ponytail` from `DietrichGebert/ponytail`, enables `ponytail@ponytail`, makes zero runner calls
- [ ] Acceptance: fake-runner `calls` show `marketplace add DietrichGebert/ponytail` before `plugin install ponytail@ponytail --scope project`
- [ ] Acceptance: `reconcile_default_plugins` appends `ponytail@ponytail` last after a custom entry; `default_config()` wired ends with it
- [ ] Acceptance: a `"ponytail@ponytail": false` tombstone survives wiring and gets no install call
- [ ] Acceptance: `tests/test_install.py` sees the ponytail trust line before the first runner call
- [ ] Acceptance: doc-sync requires `ponytail@ponytail`, `DietrichGebert/ponytail`, `SubagentStart` in all three docs; policy canary passes
- [ ] Acceptance: build, plan, equip skills carry the default-on phrases; "Ponytail is selected and exposed" is absent from `dummyindex`, `tests`, `docs`, `.context/features`
- [ ] Acceptance: `.context/config.json` `wired` ends with `ponytail@ponytail`
- [ ] Acceptance: `pytest -q` exits 0
