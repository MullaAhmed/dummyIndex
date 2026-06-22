# Checklist — config-depth-wired-ux

> Derived from the revised `plan.md` tasks + `spec.md` Acceptance. Waves run in
> order; items inside a wave touch disjoint files and are mutually independent
> (safe to dispatch in parallel). Tick `- [x]` only after the item is verified
> (its test passes / behavior observed). No item is tagged `— via <tool>`:
> `.context/equipment.json` holds only generated specialists, no marketplace
> plugins, so build routes these by keyword.

## Wave 1 — schema + model foundation (everything depends on this)

- [x] TDD the v2 config model: `WiredEntry`/`WiredKind` in base-layer
      `default_plugins.py`; `DepthCommand` enum + `command_depths` + `wired` +
      `dummyindex_version` on `Config`; drop `wire_superpowers`; `resolve_depth`
      in `config.py`; bump `CONFIG_SCHEMA_VERSION`→2 with in-memory v1→v2
      migration; regenerate the module docstring schema example.
      (`dummyindex/context/domains/config.py`, `dummyindex/context/default_plugins.py`,
      `tests/context/domains/test_config.py`)

## Wave 2 — depth resolution & CLI threading (depends on Wave 1)

- [x] Delegate `audit/workspace.py:resolve_mode` to `config.resolve_depth`; thread
      `--depth` via the shared `cli/common.py:parse_kv_flags` alphabet into
      `init`/`reconcile`/build CLIs and pass the resolved `CouncilMode` into
      `council_batch.active_stages`; `audit` accepts `--depth`/`--mode` (errors if
      both); `rebuild` untouched. Add per-command CLI tests (flag overrides config;
      `config.json` bytes unchanged after the run).
      (`dummyindex/context/domains/audit/workspace.py`, `dummyindex/cli/common.py`,
      `dummyindex/cli/audit.py`, `dummyindex/cli/init.py`, `dummyindex/cli/reconcile.py`,
      build-loop CLI, + their tests)

## Wave 3 — wired reconciler, equip write-back, enum rename (disjoint files, parallel)

- [x] Evolve `wire_default_plugins` into a non-interactive `wired`-list reconciler
      (param `tuple[WiredEntry, ...]`, classify satisfied/acted/needs-user on the
      result, never `input()`, no version-staleness verdict); migrate the
      `test_install.py` opt-out case to `wired=()`. Assert each outcome on the
      result with an injected fake runner.
      (`dummyindex/context/default_plugins.py`, `tests/context/test_default_plugins.py`,
      `tests/test_install.py`)
- [x] `equip install` upserts a matching `WiredEntry` into `config.json` keyed on
      `<plugin>@<marketplace>` (project scope; absent config → skip-with-warning;
      never raise). Tests: wired/manifest agree & don't diverge; `--scope user`/
      no-config writes nothing & doesn't raise; `write_config` failure warned.
      (`dummyindex/cli/equip/discover.py`, existing equip install test)
- [x] Rename `ModelChoice.OPUS_4_7`→`OPUS_4_8` across all 8 occurrences / 3 files;
      confirm `grep -rn OPUS_4_7` is empty and the suite is green.
      (`dummyindex/context/domains/config.py`, `tests/context/domains/test_config.py`,
      `tests/context/domains/audit/test_audit_domain.py`)

## Wave 4 — wire-up & config-UX (disjoint files, parallel; depends on Wave 3)

- [x] Init/install wiring: replace `cfg.wire_superpowers` reads with `cfg.wired`
      into the reconciler; extend `describe_wire_result` to emit per-class summary
      lines; needs-user is **reported, not prompted** here. Tests assert the
      `capsys` summary lines.
      (`dummyindex/cli/init.py`, `dummyindex/installer/install.py`, + tests)
- [x] Config-UX: document `--depth`/`command_depths`/`wired` in `onboard` usage +
      `cli/help.py`; `status` surfaces effective depth per command, wired
      classification counts, and a config-writer-version line distinct from
      `meta.dummyindex_version`. Tests: help/usage substrings + a `status`
      no-mutate assertion (`config.json` bytes unchanged).
      (`dummyindex/cli/onboard.py`, `dummyindex/cli/help.py`, `dummyindex/cli/status.py`,
      `tests/cli/test_status.py`, help/usage tests)

## Wave 5 — integration, acceptance & escalation gate

- [x] **GATE** Wire the needs-user escalation into the interactive `/dummyindex`
      reconcile surface (main-session prompt; never reached from headless
      `install --defaults`). Main-session item — the build conductor handles it,
      not a subagent. Settle whether it lands in this proposal or a follow-up.
- [x] Run `python -m pytest tests/ -q --tb=short`; full suite green on 3.10/3.12.
- [x] Update affected `.context/features/<id>/` docs (`audit-panel`, `equip`,
      `install-surface`, `cli-dispatch`) or note for a follow-up `reconcile`.
- [x] Acceptance: `command_depths.reconcile=light` runs reconcile light while
      ingest runs the global `mode`; `--depth` overrides for one run without
      rewriting config.
- [x] Acceptance: v1 `wire_superpowers:true`→seeded `wired`; `false`→empty;
      `--no-superpowers`→empty `wired` **and** superpowers absent from settings.
- [x] Acceptance: reconcile classifies satisfied/acted/needs-user on the result
      (no hang); needs-user surfaced in the summary, never silently dropped.
- [x] Acceptance: `equip install` upsert + manifest agree; user-scope/no-config
      writes no config; `dummyindex_version` stamped & migration populates it.
