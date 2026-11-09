# Plan — dummyindex internally uses ponytail: reviewed default plugin plus default-on subagent mandate

> Rule for every task: new code carries no long comments. One-line docstrings only.
> Never run `rebuild`. Edit `.context/` docs in place only. No live network or
> `claude` CLI calls; tests use the existing fake runner. Line numbers are
> hints; locate by symbol or phrase.

## Tasks

1. **Default record + its tests.** Files: `dummyindex/context/default_plugins.py`,
   `tests/context/test_default_plugins.py`, `tests/context/domains/test_config.py`,
   `tests/test_install.py`.
   - Append the spec's `DefaultPlugin` record to `DEFAULT_PLUGINS`, after
     `i-have-adhd`. In the comment above the tuple, change "both third-party
     sources" to "all three third-party sources". Touch nothing else.
   - `test_default_plugins.py`:
     - add the record to `test_default_plugins_are_exact_reviewed_ordered_records`;
     - extend `_TARGETS`;
     - add the ponytail line to
       `test_trust_disclosure_is_pure_exact_and_names_reviewed_blast_radius`;
     - add the `ponytail` marketplace to
       `test_wire_declares_all_defaults_without_invoking_runner` and to the
       marketplace set in `test_install_defers_all_selected_when_claude_absent`;
     - add one test: an ordered runner check, marketplace add before install,
       for ponytail;
     - add one test: a `"ponytail@ponytail": false` tombstone survives
       `wire_default_plugins`; `install_default_plugins` never installs it.
   - `test_config.py`: append `"ponytail@ponytail"` to the hardcoded targets in
     `test_default_config_seeds_wired_from_default_plugins` and in
     `test_reconcile_default_plugins_preserves_custom_order_and_is_idempotent`.
   - `test_install.py`: add the ponytail line to `expected_trust_disclosures`.
   - Reuse: `default_wired`, `describe_default_plugin_trust`,
     `wire_default_plugins`, `install_default_plugins`,
     `reconcile_default_plugins`, existing `_FakeRunner` / `_read_settings`.
   - Verify: `pytest -q tests/context/test_default_plugins.py tests/context/domains/test_config.py tests/test_install.py tests/cli/test_init_cli.py tests/cli/test_wire.py`.

2. **Skill text.** Files: `dummyindex/skills/build/SKILL.md`,
   `dummyindex/skills/plan/SKILL.md`, `dummyindex/skills/equip/SKILL.md`,
   `tests/test_skills_doc_hygiene.py`.
   - Replace only the Ponytail sentence (build ~82-84, plan ~72-73, equip
     ~34-36) with the spec's skill text. Re-wrap to the file's width. Leave the
     build `"policies"` sentence unchanged.
   - `test_skills_doc_hygiene.py`: in
     `test_build_delegates_selected_capability_and_policy_on_every_host`
     replace the two old Ponytail asserts. Add one parametrized test over
     build, plan and equip: new phrases present, old phrase absent. Use the
     file's flattening idiom (`" ".join(text.split())`).
   - Verify: `pytest -q tests/test_skills_doc_hygiene.py`.

3. **Default-plugin docs.** Files: `dummyindex/skills/skill.md`, `docs/COMMANDS.md`,
   `docs/guide/07-cli.md`, `tests/cli/test_cli_doc_sync.py`.
   - Add the ponytail bullet after `<!-- test-anchor:policy-selfapply:end -->`
     in each doc. Keep both anchored regions byte-identical. The `skill.md`
     Codex sentence also goes outside the anchors.
   - Change these counts:
     - `skill.md`: "exactly three reviewed native defaults" (~19), "These two
       records" (~37), "all three defaults" (~58), "the three reviewed native
       defaults" (~227).
     - `COMMANDS.md`: "these three native Claude plugins" (~60), "The two
       third-party records" (~80), "all three native" (~101).
     - `07-cli.md`: "The two third-party entries" (~84), "One run, all three"
       (~111), "Durable, all three" (~115).
   - Do NOT change opt-out layer counts: `skill.md` "three native-default
     opt-outs" (~52), `07-cli.md` "three distinct opt-out layers" (~109).
   - Keep "narrow, reviewed built-in exception" wording; the bullet's surface
     list and `runs_code=true` keep it true.
   - `test_cli_doc_sync.py`: add `"ponytail@ponytail"`, `"DietrichGebert/ponytail"`,
     `"SubagentStart"` to `required_tokens` in
     `test_default_plugin_docs_pin_targets_and_reviewed_trust`.
   - Verify:
     - `pytest -q tests/cli/test_cli_doc_sync.py tests/cli/test_cli_doc_sync_policy_canary.py`;
     - `grep -nE "\b(three|two) (reviewed |native |third-party)|all three" docs/COMMANDS.md docs/guide/07-cli.md dummyindex/skills/skill.md`;
       each hit must be an opt-out count;
     - `git diff` shows no line changed between any `test-anchor` begin/end pair.

4. **Dogfood config.** File: `.context/config.json`. Needs task 1.
   - Confirm `default_plugins_enabled` is `true` first (it is today).
   - Run `python -c "from pathlib import Path; from dummyindex.context.domains.config import reconcile_default_plugins as r; print(r(Path('.context'), platform='both'))"`.
   - Expect `True`, then `wired` ends with `ponytail@ponytail`. No hand edit.

5. **Reconcile feature doc.** File: `.context/features/equip/spec.md`. Needs task 2.
   - Rewrite the Ponytail bullet (~28-31): Ponytail applies by default when
     exposed; Claude gets it through the plugin's `SubagentStart` hook; other
     hosts paste the loaded mandate; never silently installed. Cite no
     proposal or audit path.
   - Verify: `grep -c "applies by default when exposed" .context/features/equip/spec.md`
     prints 1; `grep -c "not installed or assumed automatically"` prints 0.

6. **Acceptance.** Run `pytest -q`; exit 0. Run
   `grep -rn "Ponytail is selected and exposed" dummyindex tests docs .context/features`;
   no hits.

## Reused symbols

- `DefaultPlugin`, `DEFAULT_PLUGINS`, `default_wired`,
  `describe_default_plugin_trust`, `wire_default_plugins`,
  `install_default_plugins` (`dummyindex/context/default_plugins.py`).
- `reconcile_default_plugins`, `default_config`
  (`dummyindex/context/domains/config.py`).

## Out of scope

- A Codex plugin installer. A dummyindex-owned subagent hook.
- Changes to `envelopes.py`, `bootstrap.py`, the managed policy constants, or
  the policy anchors.
- Audit, evolve, gc and fleet skill text.
- An upstream surface drift check.
- `.claude/settings.json` in this repo; it is per-machine and untracked.

## Critique outcome

Folded: count sites, skill text for hooks-inactive Claude, session-scoped
"off", pinned upstream SHA, webhook wording, ordered runner check, verifiers
for docs and equip spec, intent scope wording. Left: new consent flag for
upgrade backfill (D7), ponytail-specific marketplace-conflict and
malformed-settings tests (generic tests cover), `test_wire.py` ponytail
assert (single-target test), drift-check task (D6).
