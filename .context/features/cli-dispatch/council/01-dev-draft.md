# CLI command dispatch — plan

`confidence: INFERRED`

## Where it lives

- `dummyindex/cli/__init__.py` — the dispatcher: `_wants_help` (`:58-81`), `_HANDLERS` (`:84-126`), `dispatch` (`:129-147`). Public exports: `dispatch`, `resolve_context_root` (`:55`).
- `dummyindex/context/enums.py` — `ContextSubcommand`, the closed **44-member** alphabet (`INIT`…`GUARD_DOC_WRITE`). The shared cross-area enum module; per-area enums (e.g. equip's) live in `context/domains/equip/enums.py`.
- `dummyindex/cli/common.py` — shared arg parsing, `resolve_context_root`, `_FLAGS_TAKING_VALUE` (incl. `--depth`), `parse_kv_flags`, `usage_error`.
- `dummyindex/cli/help.py` — `USAGE` block + `usage_for` (`:449-469`); the word-boundary helper `_line_starts_subcommand` (`:436-446`).
- `dummyindex/cli/init.py` and `dummyindex/cli/reconcile.py` — the two depth-bearing handlers; both validate `--depth` against `CouncilMode` up front, then surface a real `ConfigError` from `resolve_depth` (`init.py:42-56`, `reconcile.py:56-68`).
- One `cli/<sub>.py` (or subpackage) per handler — full roster in the table at `__init__.py:84-126`.
- `dummyindex/context/domains/config.py` — `CouncilMode` (`:68-72`), `DepthCommand` (`:84-99`), `ConfigError` (`:104-105`), `resolve_depth` (`:323-341`) — the depth-resolution seam the CLI delegates to.
- Tests: `tests/cli/test_debt_statusline_dispatch.py` (exhaustiveness + routing), `tests/cli/test_cli_doc_sync.py` (USAGE ↔ enum ↔ skill-routing parity), `tests/cli/test_scope_vs_root.py` (root resolution), `tests/cli/test_wire.py`, `tests/cli/test_migrate.py`.

## Architecture in three sentences

`dispatch(argv)` resolves the first token through the `ContextSubcommand` enum constructor (validation *is* dispatch — `ValueError` is the unknown-subcommand branch), intercepts `-h`/`--help` anywhere via `_wants_help` before any handler runs, then calls the single `_HANDLERS[sub]` entry, an O(1) table lookup total over the enum. Each `cli/<sub>.py` handler is a wire-only sink: it parses flags with `common.py` helpers, lazy-imports its `context/domains/...` function *inside* `run()` to keep the import graph acyclic and `import cli` cheap, prints, and returns an `int`. The dominant patterns are command-enum→handler-table dispatch and central-help-interception; the layer owns zero business logic and never imports back from domains.

## Data model

- `ContextSubcommand(str, Enum)` — 44 string-valued members; the value *is* the CLI token, so `ContextSubcommand(subcmd)` both validates and resolves.
- `_HANDLERS: dict[ContextSubcommand, Callable[[list[str]], int]]` — total over the enum. Single-verb modules contribute `run`; multi-verb modules contribute `run_<verb>` siblings.
- `_FLAGS_TAKING_VALUE: frozenset[str]` (`common.py:64-75`) — the single global set of value-consuming flags, now including `--depth`.
- `CouncilMode` / `DepthCommand` (`config.py:68-99`) — the depth alphabet `init`/`reconcile` validate against and pass to `resolve_depth`; `DepthCommand` omits `rebuild` by design.
- Handler return code is the contract: `0` ok, `2` usage/validation error, `1` reserved per-handler as a *signal* (e.g. `query` zero-match, `hooks defer-check`/`status` "not present").

No tables or transactions in this layer — it is pure argv→exit-code translation; persistence lives downstream in `context/domains/...`.

## Key decisions

- **Help wins everywhere, even over a value-flag's value** (`__init__.py:75-77`) — because a verb that probes by running bare can mutate the repo (the "bare-equip-mutates" hazard), so no `--help` invocation may ever reach a side effect. Cost: the pathological "literal `--help` as a flag value" case, declared a non-use-case.
- **Closed enum as the alphabet** — because validation, dispatch, and the doc-sync test all key off one source; the `ValueError` doubling as the unknown-branch is a deliberate use of the enum constructor as a validator. A subcommand in code but unwired/undocumented fails `test_every_enum_member_has_a_handler` or the doc-sync suite.
- **Lazy domain imports inside each `run()`** — because the layer must stay a one-directional sink with an acyclic graph and a cheap `import cli`. Only the *domain* import is deferred; the cli submodules are imported eagerly at the top of `__init__.py`.
- **Validate `--depth` in the handler before delegating, and stop masking `ConfigError`** (`init.py:42-56`, `reconcile.py:56-68`) — load-bearing change. `resolve_depth` raises `ConfigError` both for a bad depth flag *and* for a malformed `config.json`; catching that one exception type and always printing the depth message conflated the two. The handlers now reject a bad `--depth` themselves against `CouncilMode`, so the surviving `except ConfigError` can only be a real config problem and is surfaced verbatim. Rejected alternative: inspect the `ConfigError` message text to tell the two apart (brittle string-matching).
- **`usage_for` derives slices from `USAGE`'s own layout, word-bounded** (`help.py:449-469`, boundary at `:436-446`) — because help text must not drift from the canonical block, and prefix collisions (`reconcile` vs `reconcile-stamp`, `audit` vs `audit-log`) must be excluded by construction.
- **Hook-fed handlers invert the exit-code contract** (`memory`, `reconcile-gate` always return 0) — because a Stop/SessionStart/PreCompact hook that errors would break the user's session.

## Open questions

- `config` is documented as `show`-only with `get/set` reserved (`help.py:255-257`) — a planned-but-unbuilt surface, not a dispatch gap.
- `_FLAGS_TAKING_VALUE` is global, so it cannot know that `--status` is council-log's *value* flag yet build's *boolean* verb (called out at `__init__.py:64-68`). The help-bias mitigates the only observable consequence; whether a per-subcommand flag spec is worth the complexity is unresolved — the current single-set design is a deliberate simplicity bet.
