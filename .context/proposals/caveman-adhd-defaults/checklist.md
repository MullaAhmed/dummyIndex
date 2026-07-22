# Checklist — Add https://github.com/juliusbrussee/caveman and https://github.com/ayghri/i-have-adhd as defaults similar to superpowers and make sure they are always used

> Work wave-by-wave. Items in one wave touch disjoint files and may run in
> parallel. Tick `- [x]` only after verifying each item.

## Wave 1 — default policy and host guidance

- [x] Implement the pinned, vetted, target-aware default declaration/install
  policy and trust disclosure (`dummyindex/context/default_plugins.py`).
- [x] Add one shared always-on output policy to Claude project guidance and
  Codex project-only guidance (`dummyindex/context/output/bootstrap.py`,
  `dummyindex/context/output/agents_md.py`).

## Wave 2 — durable config state

- [x] Add the config-schema migration, explicit applicability/opt-out state,
  and idempotent pre-wire default reconciliation
  (`dummyindex/context/domains/config.py`).

## Wave 3 — independent CLI surfaces

- [x] Add `--no-default-plugins` plus the legacy `--no-superpowers` alias and
  one early-gate value (`dummyindex/installer/args.py`,
  `dummyindex/installer/install.py`, `dummyindex/cli/init.py`,
  `dummyindex/__main__.py`, `dummyindex/cli/help.py`).
- [x] Make interactive wiring use the one-target seam and never install
  unrelated defaults (`dummyindex/cli/wire.py`).

## Wave 4 — same-run orchestration

- [x] Order installer/init migration, reconciliation, fail-closed config reads,
  disclosure, declaration, and one-pass materialization correctly
  (`dummyindex/installer/install.py`, `dummyindex/cli/init.py`).

## Wave 5 — policy and domain tests

- [x] Cover pinned default metadata, trust/ref validation, marketplace
  declaration/conflicts, filtered materialization, failure isolation, config
  migration/transition, false tombstones, idempotency, and one-target
  interactive wiring (`tests/context/test_default_plugins.py`,
  `tests/context/test_claude_plugins.py`,
  `tests/context/domains/test_config.py`, `tests/cli/test_wire.py`).

## Wave 6 — entrypoint and guidance tests

- [x] Cover fresh Claude/both behavior, Codex non-mutation/transition,
  same-run backfill, malformed-config fail-closed behavior, byte-exact opt-outs,
  shared project-only guidance, marker refresh, and user-content preservation
  (`tests/test_install.py`, `tests/cli/test_init_cli.py`,
  `tests/context/output/test_bootstrap.py`,
  `tests/context/output/test_agents_md.py`).

## Wave 7 — user-facing documentation

- [x] Document all three defaults, pinned-source trust surfaces, host scope, the
  canonical/legacy flags, and durable/individual/one-run opt-outs
  (`docs/COMMANDS.md`, `docs/guide/07-cli.md`,
  `dummyindex/skills/skill.md`).

## Wave 8 — help and documentation guards

- [x] Add exact help/documentation regression coverage for the flags, targets,
  trust disclosure, host scope, and opt-out semantics (`tests/test_install.py`,
  `tests/cli/test_subcommand_help.py`, `tests/cli/test_cli_doc_sync.py`).

## Wave 9 — verification

- [x] Run focused tests, `python -m pytest tests/ -q --tb=short`,
  `ruff check .`, and `ruff format --check .`; fix any failures before
  continuing.

## Wave 10 — context reconciliation

- [x] Refresh deterministic maps, inspect drift, and reconcile every reported
  curated feature affected by the implementation — via $dummyindex.

## Wave 11 — acceptance

- [x] Acceptance: `DEFAULT_PLUGINS` is exactly the existing superpowers entry
  plus the two reviewed full-SHA records, with unique ordered targets and
  explicit surfaces/`runs_code` metadata.
- [x] Acceptance: pre-mutation output discloses each third-party source/ref,
  surfaces, code execution, and `--no-default-plugins` before runner calls,
  without weakening equip's approval policy.
- [x] Acceptance: both `install` and `context init` on Claude/both declare the
  pinned marketplaces, enable all three targets, and install each eligible
  target once in marketplace-before-install order.
- [x] Acceptance: a missing Claude CLI leaves resolvable declarations and exact
  deferred results; one target's marketplace/install failure is isolated and
  never fails init/install.
- [x] Acceptance: identical marketplace declarations are no-ops and conflicting
  same-name sources are preserved, skipped, and reported needs-user.
- [x] Acceptance: Codex-only runs never mutate `.claude/**` or invoke Claude,
  include the project policy, and transition to Claude/both in one run unless
  explicitly opted out.
- [x] Acceptance: one reinstall backfills, persists, and materializes missing
  defaults before wiring without losing/duplicating custom entries; reruns are
  byte- and call-idempotent.
- [x] Acceptance: explicit project/local false tombstones and omitted defaults
  are not materialized; a disabled/empty selected set makes zero runner calls.
- [x] Acceptance: canonical and legacy one-run opt-outs skip every config,
  marketplace, settings, runner, and backfill action and leave a current config
  byte-identical.
- [x] Acceptance: malformed config warns and causes no default config,
  marketplace, enabled-plugin, or runner mutation.
- [x] Acceptance: Claude project and Codex project guidance contain the same
  policy exactly once, preserve user content, and Codex global guidance omits it.
- [x] Acceptance: help and documentation consistently cover all targets,
  canonical/legacy flags, host scope, trust disclosure, and opt-out semantics.
- [x] Acceptance: focused and full pytest suites plus Ruff lint/format checks
  pass without network access.
