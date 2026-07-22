# Plan — Add https://github.com/juliusbrussee/caveman and https://github.com/ayghri/i-have-adhd as defaults similar to superpowers and make sure they are always used

> Ordered, file-path-naming tasks. Cite reused symbols from
> `.context/map/symbols.json` where you can reuse instead of writing new.

## Tasks

1. Define the vetted built-in records and a target-aware declaration/install
   seam in `dummyindex/context/default_plugins.py`, reusing `DefaultPlugin`,
   `DEFAULT_PLUGINS`, `default_wired`, `wire_default_plugins`,
   `install_default_plugins`, `_install_one`, and the injected `Runner` from the
   `install-surface` feature. Add the two full-SHA refs plus reviewed
   surfaces/`runs_code` metadata; validate unique targets and immutable refs;
   render a pre-mutation trust/blast-radius disclosure; declare exact third-party
   repo/ref entries with `add_marketplace`; refuse conflicting declarations;
   separate declaration from one filtered materialization pass; continue after
   independent per-target failures; and preserve best-effort result reporting.

2. Add explicit default-plugin applicability/opt-out state and upgrade behavior
   in `dummyindex/context/domains/config.py`. Bump the config schema, migrate
   existing Claude/both opt-ins, explicit opt-outs, and the canonical Codex-only
   baseline without conflating them, and add a defaults-specific reconciliation
   beside `reconcile_wired_with_equipment`. When a run includes Claude and is
   opted in, append missing `default_wired()` targets before wiring while
   preserving custom entries/order; when disabled or Codex-only, write nothing.
   Reuse `Config`, `default_config`, `_parse_wired`, `migrate_config_in_place`,
   `read_config`, `write_config`, and `reconcile_wired_with_equipment`.

3. Order and gate the shared orchestration in
   `dummyindex/installer/install.py` and `dummyindex/cli/init.py`: resolve the
   one-run opt-out before any config/plugin mutation; migrate/reconcile an
   opted-in config before `_wire_default_plugins_step` reads it; fail closed on
   `ConfigError`; print the trust disclosure before settings or runner calls;
   then declare and materialize the selected effectively-true defaults exactly
   once. Keep formatting/printing at each boundary rather than importing the
   private installer wrapper into the CLI. Verify a Codex-only-to-Claude/both
   transition completes in one run and Codex-only never touches `.claude/**`.

4. Thread the canonical flag through `dummyindex/installer/args.py`,
   `dummyindex/installer/install.py`, `dummyindex/cli/init.py`,
   `dummyindex/__main__.py`, and `dummyindex/cli/help.py`. Accept
   `--no-default-plugins`, retain `--no-superpowers` as a compatibility alias,
   and resolve both to the one early gate without persisting or backfilling an
   opt-out. Reuse `resolve_enabled` and the existing platform gates.

5. Update the interactive path in `dummyindex/cli/wire.py` to call the same
   one-target declaration/materialization seam rather than
   `install_default_plugins()` over the whole default tuple. Preserve its
   prompt/non-TTY behavior and ensure wiring a custom plugin cannot install an
   unrelated default. Reuse `_wire_plugin`, `classify_wired_entry`, and the
   existing boundary runner/error handling.

6. Add the stable always-on activation fallback to managed project guidance in
   `dummyindex/context/output/bootstrap.py` and
   `dummyindex/context/output/agents_md.py`. Define the policy once beside
   `generate_managed_block`, include it in Claude's managed block and Codex's
   `_PROJECT_BLOCK`, leave `_GLOBAL_BLOCK` unchanged, and continue using
   `bootstrap_claude_md`, `reconcile_claude_md`, and
   `bootstrap_project_agents_md` so user content and marker ownership remain
   intact.

7. Expand unit coverage in `tests/context/test_default_plugins.py`,
   `tests/context/test_claude_plugins.py`,
   `tests/context/domains/test_config.py`, and `tests/cli/test_wire.py`. Assert
   the exact pinned three-entry set and trust metadata; unique/ref validation;
   disclosure-before-action; exact/ conflicting marketplace handling;
   declaration when the CLI is absent; one filtered install pass; no unrelated
   interactive installs; project/local false precedence; per-target failure
   isolation/result buckets; schema migration; Codex applicability transition;
   custom-entry preservation; opt-out preservation; and idempotency. Keep every
   subprocess behind the existing fake `Runner`.

8. Expand install/init and guidance integration coverage in
   `tests/test_install.py`, `tests/cli/test_init_cli.py`,
   `tests/context/output/test_bootstrap.py`, and
   `tests/context/output/test_agents_md.py`. Verify fresh Claude/both defaults,
   Codex-only non-mutation plus one-run host transition, same-run upgrade
   backfill/materialization, malformed-config fail-closed behavior, byte-exact
   one-run opt-outs under both spellings, explicit-false preservation, shared
   project-only policy text, marker refresh, and surrounding user-content
   preservation.

9. Add help/documentation regression coverage in `tests/test_install.py`,
   `tests/cli/test_subcommand_help.py`, and `tests/cli/test_cli_doc_sync.py` for
   top-level/install/ingest/init output, the canonical flag and legacy alias,
   all three targets, Claude-versus-Codex scope, pinned-source trust disclosure,
   and the documented opt-out semantics.

10. Update user-facing wording in `docs/COMMANDS.md`,
   `docs/guide/07-cli.md`, and `dummyindex/skills/skill.md`. Name all three
   defaults, make `--no-default-plugins` canonical, label `--no-superpowers` as
   a compatibility alias, explain the vetted pinned-source exception and
   reviewed hook surfaces, distinguish Claude-native plugin wiring from Codex
   managed-guidance behavior, and document durable/global, individual-false,
   and one-run opt-outs.

11. Verify the implementation with the focused suites for the files above,
    then `python -m pytest tests/ -q --tb=short`, `ruff check .`, and
    `ruff format --check .`.

12. Refresh deterministic context maps with
    `dummyindex context rebuild --changed`, inspect the resulting reconcile
    report, and reconcile every drifted curated feature (including, when
    reported, `install-surface`, `bootstrap`, `cli-dispatch`, and the config-owning
    feature) through the `$dummyindex` workflow — via $dummyindex.

## Critique revision

Folded every BLOCK/HIGH finding and the agreed MEDIUM findings: immutable refs
and reviewed blast-radius disclosure, declaration-time marketplaces with
conflict safety, same-run reconciliation ordering, explicit Codex applicability,
malformed-config fail-closed behavior, target-aware interactive wiring, isolated
failure tests, byte-exact opt-outs, project-only guidance checks, documentation
tests, and reconciliation of every reported feature. Deliberately kept native
Codex third-party plugin installation out of scope; Codex gets the requested
always-on behavior through its managed project guidance, matching the existing
superpowers comparison's Claude-only plugin seam.
