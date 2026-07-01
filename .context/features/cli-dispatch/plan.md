# CLI command dispatch — plan

`confidence: INFERRED`

## Bounded context

This feature is the **argv → exit-code router** for `dummyindex context <sub>`, and nothing more. It owns three responsibilities and explicitly disowns a fourth:

1. Resolve the first token to a closed subcommand alphabet.
2. Intercept `-h`/`--help` anywhere, before any side effect.
3. Hand the rest of `argv` to exactly one handler and return its `int`.

It does **not** own what each handler *does* — every `cli/<sub>.py` is a wire-only sink whose business logic lives downstream in `context/domains/...`. Those domains are out of scope here; this doc covers the dispatcher, the shared parse/help surface it leans on, and the one cross-cutting handler contract (depth validation) that the dispatcher's invariants depend on.

## Where it lives

- `dummyindex/cli/__init__.py` — **the dispatcher**: `_wants_help` (`:58-81`), the `_HANDLERS` table (`:84-126`), `dispatch` (`:129-147`). Re-exports `dispatch` + `resolve_context_root` (`:52,55`); the latter's body lives in `common.py`.
- `dummyindex/context/enums.py` — `ContextSubcommand`, the closed **44-member** alphabet (`INIT`…`GUARD_DOC_WRITE`; count verified, `len(list(ContextSubcommand)) == 44`). Shared cross-area enum module; per-area enums (e.g. equip's) live in `context/domains/equip/enums.py`.
- `dummyindex/cli/common.py` — the **shared parse surface**: `resolve_context_root`, `_FLAGS_TAKING_VALUE` (`:64-75`, incl. `--depth` at `:73`), `parse_path_and_root` (`:104`), `parse_kv_flags` (`:183`), `usage_error` (`:47`).
- `dummyindex/cli/help.py` — the canonical `USAGE` block + `usage_for` (`:447`); the word-boundary helper `_line_starts_subcommand` (`:434`).
- `dummyindex/cli/init.py`, `dummyindex/cli/reconcile.py` — the two depth-bearing handlers; each validates `--depth` against `CouncilMode` up front, then surfaces a real `ConfigError` from `resolve_depth` (`init.py:42-56`, `reconcile.py:56-68`).
- `dummyindex/context/domains/config.py` — the depth-resolution seam the CLI delegates to: `CouncilMode` (`:68`), `DepthCommand` (`:84`), `ConfigError` (`:104`), `resolve_depth` (`:323`).
- Tests: `tests/cli/test_debt_statusline_dispatch.py` (exhaustiveness + routing), `tests/cli/test_cli_doc_sync.py` (USAGE ↔ enum ↔ skill-routing parity), `tests/cli/test_scope_vs_root.py` (root resolution), `tests/cli/test_wire.py`, `tests/cli/test_migrate.py`.

Individual command handlers (`audit`, `equip`, `build`, `query`, …) belong to *their own* features; this plan names them only where their shape constrains the dispatcher.

## Patterns

- **Command-enum → handler-table dispatch.** `ContextSubcommand(subcmd)` is the membership check *by construction* — the raised `ValueError` **is** the unknown-subcommand branch (`__init__.py:135-139`). `_HANDLERS` (`:84-126`) is total over the enum, so routing is one `dict` lookup, O(1) over the alphabet.
- **Central help interception.** A single `_wants_help` walk (`:58-81`) short-circuits at `dispatch:144-146`, ahead of any handler. Lives only in the dispatcher — no handler re-implements help detection.
- **Wire-only command handler.** Each `cli/<sub>.py` parses flags with `common.py` helpers, lazy-imports its `context/domains/...` function *inside* `run()`, prints, returns `int`. The layer holds zero business logic and never imports back from domains.
- **Lazy-import table.** The domain function is imported inside `run()` (e.g. `init.py:38-40` imports `CouncilMode`/`DepthCommand`/`resolve_depth` at call time); only the cli submodules are imported eagerly at the top of `__init__.py`.
- **Doc-as-data parity.** `usage_for` slices the canonical `USAGE` text by its own layout (`help.py:447-469`), word-bounded by `_line_starts_subcommand` (`:434-446`) so prefix collisions are excluded by construction.

## Data model

- `ContextSubcommand(str, Enum)` — 44 string-valued members; the value *is* the CLI token, so `ContextSubcommand(subcmd)` both validates and resolves. `ingest` is **not** a member — it is a top-level alias for `init` resolved in `__main__`. The newer members include `gc`, `migrate-docs`, and `guard-doc-write`.
- `_HANDLERS: dict[ContextSubcommand, Callable[[list[str]], int]]` — total over the enum. Single-verb modules contribute `run`; multi-verb modules contribute `run_<verb>` siblings (e.g. `enrich.run_plan`/`run_apply`, `reconcile.run`/`run_stamp`, `audit.run`/`run_log`, `features.run_*`).
- `_FLAGS_TAKING_VALUE: frozenset[str]` (`common.py:64-75`) — the single global set of value-consuming flags, including `--depth`. Drives both `_wants_help`'s value-skip and `parse_path_and_root`.
- `CouncilMode` / `DepthCommand` (`config.py:68-99`) — the depth alphabet `init`/`reconcile` validate against and pass to `resolve_depth`; `DepthCommand` omits `rebuild` by design (deterministic, no council stage to consume a depth). `init` resolves with `DepthCommand.INGEST` (`init.py:50`), `reconcile` with `DepthCommand.RECONCILE` (`reconcile.py:64`).
- **Exit-code contract:** `0` ok; `2` usage/validation error; `1` reserved per-handler as a *signal* (e.g. `query` zero-match, `hooks defer-check`/`status` "not present"). No tables or transactions in this layer — pure argv→exit-code translation; persistence is downstream.

## Dependencies

- **Upstream (callers):** `__main__` resolves the `ingest`→`init` alias, then calls `dispatch(argv)`. The dispatcher has exactly one entry point.
- **Downstream (callees):** each handler lazy-imports `context/domains/...`. `init`/`reconcile` additionally depend on `config.resolve_depth` + `CouncilMode`/`DepthCommand`/`ConfigError`.
- **Acyclic by enforcement:** the lazy-import pattern keeps the edge cli→domains one-directional; domains never import `cli`, so `import cli` stays cheap and the graph has no cycle. This is a structural invariant, not a convention — breaking it would re-couple the layers.
- **Shared, not duplicated:** `_FLAGS_TAKING_VALUE` is one global set consumed by both the help walk and the path/root parser — a single source the two readers can't disagree on.

## Decisions

- **Decided help wins everywhere — even over a value-flag's value** (`__init__.py:75-77`) — because a verb that probes by running bare can mutate the repo (the "bare-equip-mutates" hazard), so no `--help` invocation may ever reach a side effect. Trade-off: the pathological "literal `--help` as a flag value" case is sacrificed, declared a non-use-case (docstring `:64-68`).
- **Decided the enum constructor doubles as the validator** — because validation, dispatch, and the doc-sync test all key off one source of truth, and `ValueError` is a free unknown-subcommand branch (`:135-139`). Trade-off: a subcommand added in code but left unwired/undocumented fails `test_every_enum_member_has_a_handler` or the doc-sync suite rather than failing at runtime.
- **Decided O(1) table dispatch + lazy domain imports** — because the layer must stay a one-directional sink with an acyclic graph and a cheap `import cli`. Trade-off: the domain import cost is paid per-invocation inside `run()` instead of at module load; acceptable because the CLI runs one subcommand per process.
- **Decided to validate `--depth` in the handler *before* `resolve_depth`, and stop masking `ConfigError`** (`init.py:42-56`, `reconcile.py:56-68`) — load-bearing change. `resolve_depth` raises `ConfigError` for *both* a bad depth flag and a malformed `config.json`; the old single `except ConfigError` always printed the depth message, conflating the two. The handlers now reject a bad `--depth` against `CouncilMode` up front (`init.py:43`, `reconcile.py:57`), so the surviving `except ConfigError` can only be a real config problem, surfaced verbatim (`init.py:51-56`, `reconcile.py:65-68`). Trade-off / rejected alternative: inspecting the `ConfigError` message text to disambiguate (brittle string-matching).
- **Decided `usage_for` derives slices from `USAGE`'s own layout, word-bounded** (`help.py:447-469`; boundary `:434-446`) — because help text must not drift from the canonical block. Trade-off: prefix collisions (`reconcile` vs `reconcile-stamp`/`reconcile-gate`, `audit` vs `audit-log`) must be excluded by the word-boundary check rather than by naming discipline.
- **Decided hook-fed handlers invert the exit-code contract** (`memory`, `reconcile-gate` always return 0) — because a Stop/SessionStart/PreCompact hook that errors would break the user's session. Trade-off: these two handlers can't signal failure via exit code; they must degrade silently.

## Open questions

- `config` is documented as `show`-only with `get/set` reserved (`help.py:255-257`) — a planned-but-unbuilt surface, not a dispatch gap.
- `_FLAGS_TAKING_VALUE` is global, so it can't know `--status` is council-log's *value* flag yet build's *boolean* verb (called out at `__init__.py:64-68`). The help-bias mitigates the only observable consequence; whether a per-subcommand flag spec is worth the complexity is unresolved — the current single-set design is a deliberate simplicity bet.
