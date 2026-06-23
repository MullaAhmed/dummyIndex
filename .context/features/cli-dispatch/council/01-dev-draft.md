# cli-dispatch — plan

`confidence: INFERRED`

## Where it lives

- `dummyindex/cli/__init__.py` — the dispatcher: `_wants_help` (`:58-81`), the `_HANDLERS` table (`:84-126`), `dispatch` (`:129-147`).
- `dummyindex/context/enums.py:40-87` — `ContextSubcommand`, the closed 41-member alphabet (the shared cross-area enum module; per-area enums like equip's live in `context/domains/equip/enums.py`).
- `dummyindex/cli/common.py` — shared arg parsing + `resolve_context_root` + `_FLAGS_TAKING_VALUE`.
- `dummyindex/cli/help.py` — `USAGE` + the `usage_for` slicer.
- One `cli/<sub>.py` (or subpackage) per handler: `audit, check, config, conventions, council, council_batch, debt, dev_pick, doc_reorg, enrich, equip, features, hooks, init, memory, migrate, plan_update, preflight, query, reality_check, rebuild, reconcile, reconcile_gate, refresh, status, statusline, wire, bootstrap, build_loop, onboard, propose`.
- Tests: `tests/cli/test_debt_statusline_dispatch.py` (exhaustiveness + routing), `tests/cli/test_cli_doc_sync.py` (USAGE ↔ enum ↔ skill-routing parity), `tests/cli/test_scope_vs_root.py` (root resolution), `tests/cli/test_wire.py`, `tests/cli/test_migrate.py`.

## Architecture in three sentences

`dispatch(argv)` short-circuits empty/`--help`, converts the first token to a `ContextSubcommand` (the `ValueError` *is* the unknown-subcommand path), checks `_wants_help` over the rest, then calls the one handler in `_HANDLERS`. Every handler is wire-only — it parses flags with `cli/common.py` helpers, lazy-imports its `context/domains/...` function *inside* `run()` (so importing `cli` is cheap and circular-import-free), prints, and returns an exit code; the dispatcher owns no business logic. Help is intercepted centrally and before any handler runs, which is the layer's one load-bearing safety property.

## Data model

- `ContextSubcommand(str, Enum)` — 41 string-valued members; the value *is* the CLI token, so `ContextSubcommand(subcmd)` both validates and resolves.
- `_HANDLERS: dict[ContextSubcommand, Callable[[list[str]], int]]` — total over the enum; verb-bearing modules contribute `run_<verb>` callables.
- `_FLAGS_TAKING_VALUE: frozenset[str]` (`common.py:64-75`) — the single source of truth for which flags consume the next token; shared by `_wants_help`, `parse_path_and_root`, and `parse_kv_flags`.
- Handler return code is the contract: `0` ok, `2` usage/validation error, `1` reserved per-handler (e.g. `query` no-match, `hooks defer-check`/`status` "not present").

## Key decisions

- **Help wins everywhere, including over a value-flag's value** (`__init__.py:75-77`). The bias trades a pathological literal-`--help`-as-value case for the guarantee that no `--help` invocation ever triggers a side effect — the documented "bare-equip-mutates" hazard.
- **Closed enum as the alphabet.** Validation, dispatch, and the doc-sync test all key off one enum; a new subcommand that isn't wired or documented fails `test_every_enum_member_has_a_handler` / the doc-sync suite.
- **Lazy domain imports inside each `run()`** (e.g. `hooks.py:15-20`, `query.py:9-15`, `dev_pick.py:15-19`) — keeps the CLI import graph flat and the layering one-directional (cli → domains, never the reverse).
- **`usage_for` derives slices from `USAGE`'s own layout**, word-bounded on the token (`help.py:434-444`) — help text can't drift from the reference block, and prefix collisions (`reconcile` vs `reconcile-stamp`) are excluded by construction.
- **Hook-fed handlers swallow failure** (`memory`, `reconcile-gate` always return 0) — a hook that errors would break the user's session, so the exit-code contract is inverted for them.
- **Shared stdin/transcript parsing lifted to `memory.py`** (`read_hook_stdin`, `resolve_transcript`) and reused by `reconcile_gate.py` rather than duplicated.

## Open questions

- `config` is documented as `show`-only with `get/set` reserved (`help.py:253-255`) — a planned but unbuilt surface, not a gap in dispatch.
- `_FLAGS_TAKING_VALUE` is global, so it can't distinguish that `--status` is council-log's *value* flag yet build's *boolean* verb (`__init__.py:64-68` calls this out); the help-bias mitigates the only observable consequence. Whether a per-subcommand flag spec is worth the complexity is unresolved — the current single-set design is a deliberate simplicity bet.
