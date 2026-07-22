# CLI command dispatch — plan

`confidence: INFERRED`

## Where it lives

- `dummyindex/__main__.py` owns top-level help and routes `install`, `ingest`,
  `context`, and aliases (`dummyindex/__main__.py:103-173`,
  `dummyindex/__main__.py:259-324`).
- `dummyindex/cli/help.py` owns canonical context help text and exact
  subcommand-block extraction (`dummyindex/cli/help.py:17-42`,
  `dummyindex/cli/help.py:504-557`).
- `dummyindex/cli/init.py` owns init parsing plus the ordered, best-effort
  default-plugin orchestration boundary (`dummyindex/cli/init.py:17-84`,
  `dummyindex/cli/init.py:87-231`).
- `dummyindex/cli/wire.py` owns the only interactive `wired` escalation and the
  one-target declaration/materialization seam
  (`dummyindex/cli/wire.py:46-173`, `dummyindex/cli/wire.py:221-244`).
- `tests/cli/test_init_cli.py`, `tests/cli/test_wire.py`,
  `tests/cli/test_subcommand_help.py`, and `tests/cli/test_cli_doc_sync.py` pin
  orchestration order, byte-exact opt-outs, target filtering, help safety, and
  cross-surface wording.

## Architecture in three sentences

The top-level entrypoint and context dispatcher reduce aliases and help requests before a command handler can mutate state. The init handler builds the index and host guidance, then runs one default-plugin boundary whose internal order is gate, disclose, validate, reconcile, declare, materialize, and render. Interactive wire reuses the same domain seams with a one-entry selection, keeping prompts at the CLI boundary and unrelated defaults outside the action set.

## Data model

This layer owns no persistent model: handlers consume `list[str]`, call domain
functions, print structured human output, and return integer exit codes. Init
reads downstream `Config.wired` and `default_plugins_enabled`, then carries one
`tuple[WiredEntry, ...]` through both declaration and materialization
(`dummyindex/cli/init.py:51-78`). Wire consumes the same ledger plus
`WiredClass`, `PluginWireResult`, and `PluginInstallResult`; its local state is
only classified entries and the `wired_now`, `skipped`, and `remaining` output
buckets (`dummyindex/cli/wire.py:88-173`,
`dummyindex/cli/wire.py:221-244`).

The process contract is `0` for success or best-effort completion, `2` for
usage/config validation at the command boundary, and per-handler `1` where a
domain operation uses it as a runtime signal. The plugin step deliberately does
not convert per-target failure into init failure after the index is built
(`dummyindex/cli/init.py:63-84`).

## Key decisions

- Make `--no-default-plugins` canonical and retain `--no-superpowers` as a
  non-persisted parser alias. Both collapse before any default-specific work
  (`dummyindex/cli/init.py:90-107`).
- Print reviewed third-party disclosure before strict config reads, migrations,
  settings writes, or runner probes (`dummyindex/cli/init.py:46-60`).
- Validate config before tolerant migration and stop all default mutation on
  `ConfigError`; do not synthesize `default_wired()` from malformed state
  (`dummyindex/cli/init.py:51-68`).
- Re-read config after migration/reconciliation and reuse its exact selected
  `wired` set for declaration and materialization. This makes same-run backfill
  visible and prevents duplicate all-default install passes
  (`dummyindex/cli/init.py:56-78`).
- Keep Codex-only init outside Claude plugin orchestration while still writing
  managed project guidance (`dummyindex/cli/init.py:121-129`,
  `dummyindex/cli/init.py:197-229`).
- Keep headless init non-interactive and isolate prompting in `context wire`.
  Non-TTY input never blocks, and `--yes` bypasses the prompt seam
  (`dummyindex/cli/wire.py:125-173`).
- Pass one selected entry through interactive declaration and materialization;
  never call an all-default installer from a one-target action
  (`dummyindex/cli/wire.py:221-244`).
- Treat help as executable documentation: canonical flag precedes legacy alias,
  nested context help is extracted from one template, and all help paths are
  mutation-free (`dummyindex/__main__.py:141-173`,
  `dummyindex/cli/help.py:504-557`,
  `tests/cli/test_subcommand_help.py:27-53`).

## Open questions

- `context wire` labels every valid absent plugin as untrusted, including a
  reviewed built-in default, and does not print the built-in pinned-source blast
  disclosure before acting. Should the one-target path render the reviewed
  disclosure when its selected target is a built-in
  (`dummyindex/cli/wire.py:193-200`, `dummyindex/cli/wire.py:221-244`)?
- Per-entry declaration/install failure leaves the target needs-user but
  `context wire` still exits `0`. Should a machine-readable or nonzero aggregate
  result be added for automation without changing the interactive best-effort
  contract (`dummyindex/cli/wire.py:156-173`)?
- The canonical flag suppresses default-specific work only after index and host
  guidance generation. The wording says “skip all default Claude plugins,” which
  matches behavior; should help explicitly state that indexing and managed
  guidance still run (`dummyindex/cli/help.py:21-42`,
  `dummyindex/cli/init.py:180-229`)?
