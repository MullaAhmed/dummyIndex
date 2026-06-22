# cli-dispatch — plan

`confidence: INFERRED`

## Bounded context

The CLI dispatch layer is a **one-directional sink**: `dummyindex/cli/` imports *from* `dummyindex/context/domains/`, and domains never import back. Its sole job is translation — raw `argv` in, a process exit code out — with zero business logic owned here. The boundary is enforced two ways: structurally (handlers lazy-import their domain function *inside* `run()`, so the import graph stays acyclic and `import dummyindex.cli` stays cheap) and by test (`test_every_enum_member_has_a_handler` keeps the dispatch table total over the alphabet).

Upstream of this layer: `__main__` (resolves the `ingest`->`init` top-level alias before the dispatcher ever sees argv). Downstream: every `context/domains/...` module. There are no cycles by construction — verified by the lazy-import discipline below.

## Patterns named

- **Command-enum -> handler-table dispatch.** `ContextSubcommand` (`context/enums.py:40-87`) is the closed alphabet; `_HANDLERS` (`cli/__init__.py:84-126`) is a `dict[ContextSubcommand, Callable[[list[str]], int]]` *total over that enum*. `ContextSubcommand(subcmd)` does validation and resolution in one step — the raised `ValueError` **is** the unknown-subcommand branch (`cli/__init__.py:134-139`). No `if/elif` chain, no string matching downstream of the enum.
- **Central help interceptor.** `_wants_help` + the guard at `cli/__init__.py:144-146` short-circuit *before* `_HANDLERS[sub](rest)` ever runs. This is the layer's one load-bearing safety property: no `--help` invocation can reach a handler's mandatory-flag parse or filesystem side effect.
- **Wire-only handler / lazy-domain-import.** Each `cli/<sub>.py` parses flags with `common.py` helpers, lazy-imports its domain function *inside* `run()` (e.g. `query.py:9-15`), prints, returns an `int`. The cli submodules themselves are imported eagerly at the top of `__init__.py`; only the heavy *domain* imports are deferred.
- **Single source of truth for value-flags.** `_FLAGS_TAKING_VALUE` (`common.py:64-75`) is one global frozenset, consumed by both `_wants_help`'s skip logic and `parse_path_and_root`. One set, two readers — no duplicated flag knowledge.

## Where it lives

- `dummyindex/cli/__init__.py` — the dispatcher: `_wants_help` (`:58-81`), `_HANDLERS` (`:84-126`), `dispatch` (`:129-147`). Public exports: `dispatch`, `resolve_context_root` (`:55`).
- `dummyindex/context/enums.py:40-87` — `ContextSubcommand`, the closed **41-member** alphabet (verified by direct count, `INIT`...`STATUSLINE`). This is the shared cross-area enum module; per-area enums (e.g. equip's) live in `context/domains/equip/enums.py`.
- `dummyindex/cli/common.py` — shared arg parsing, `resolve_context_root`, `_FLAGS_TAKING_VALUE`, `usage_error`.
- `dummyindex/cli/help.py` — `USAGE` block + `usage_for` (`:447-467`); the word-boundary helper `_line_starts_subcommand` (`:434-444`).
- One `cli/<sub>.py` (or subpackage) per handler — full roster in the table at `__init__.py:84-126`.
- Tests: `tests/cli/test_debt_statusline_dispatch.py` (exhaustiveness + routing), `tests/cli/test_cli_doc_sync.py` (USAGE <-> enum <-> skill-routing parity), `tests/cli/test_scope_vs_root.py` (root resolution), `tests/cli/test_wire.py`, `tests/cli/test_migrate.py`.

## Dependencies surfaced

| Direction | Edge | Mechanism |
|---|---|---|
| Upstream -> cli | `__main__` -> `dispatch` | `ingest`->`init` alias resolved before dispatch; `ingest` is **not** an enum member (`enums.py:43-44`). |
| cli -> domains | each handler `run()` -> `context/domains/...` | **lazy** import inside `run()` — keeps the graph acyclic. |
| cli intra-layer | `__init__` -> `common` (`_FLAGS_TAKING_VALUE`), `__init__` -> `help` (`USAGE`, `usage_for`) | eager top-level imports. |
| cli intra-layer | `reconcile_gate.run` -> `memory.read_hook_stdin`/`resolve_transcript` | shared hook-stdin parsing lifted to `memory.py`, reused not duplicated. |
| domains -> cli | **none** | the sink boundary; no reverse edge exists. |

Cycle check: none. The only path that could close a cycle (a domain importing `cli`) is structurally absent, and the lazy-import discipline means even adding one wouldn't fire at `import cli` time.

## Data model

- `ContextSubcommand(str, Enum)` — 41 string-valued members; the value *is* the CLI token, so `ContextSubcommand(subcmd)` both validates and resolves.
- `_HANDLERS: dict[ContextSubcommand, Callable[[list[str]], int]]` — total over the enum. Single-verb modules contribute `run`; multi-verb modules contribute `run_<verb>` siblings (e.g. `enrich.run_plan`/`run_apply`, `reconcile.run`/`run_stamp`, `audit.run`/`run_log`, `features.run_*`).
- `_FLAGS_TAKING_VALUE: frozenset[str]` (`common.py:64-75`) — the single global set of value-consuming flags.
- Handler return code is the contract: `0` ok, `2` usage/validation error, `1` reserved per-handler as a *signal* (e.g. `query` zero-match, `hooks defer-check`/`status` "not present").

## Decisions (decided X because Y)

- **Help wins everywhere, even over a value-flag's value** (`__init__.py:75-77`) — *because* a verb that probes by running bare can mutate the repo (the documented "bare-equip-mutates" hazard), so no `--help` invocation may ever reach a side effect. The accepted cost is the pathological "literal `--help` as a flag value" case, declared a non-use-case.
- **Closed enum as the alphabet** — *because* validation, dispatch, and the doc-sync test must all key off one source; a subcommand added to code but not wired/documented fails `test_every_enum_member_has_a_handler` or the doc-sync suite. The `ValueError` doubling as the unknown-branch is a deliberate use of the enum constructor as a validator.
- **Lazy domain imports inside each `run()`** (e.g. `query.py:9-15`) — *because* the layer must stay a one-directional sink with a flat, acyclic import graph and a cheap `import cli`. Deferring only the domain import (not the cli submodule) is the minimum that achieves this.
- **`usage_for` derives slices from `USAGE`'s own layout, word-bounded** (`help.py:447-467`, boundary at `:434-444`) — *because* help text must not drift from the canonical block, and prefix collisions (`reconcile` vs `reconcile-stamp`, `audit` vs `audit-log`) must be excluded by construction rather than by hand.
- **Hook-fed handlers invert the exit-code contract** (`memory`, `reconcile-gate` always return 0) — *because* a Stop/SessionStart/PreCompact hook that errors would break the user's session; correctness of the turn outranks signalling failure here.
- **Shared stdin/transcript parsing lifted to `memory.py`** (`read_hook_stdin`, `resolve_transcript`) — *because* `reconcile_gate` needs the identical parse; one home beats two copies.

## Open questions

- `config` is documented as `show`-only with `get/set` reserved (`help.py:253-255`) — a planned-but-unbuilt surface, not a dispatch gap.
- `_FLAGS_TAKING_VALUE` is global, so it cannot know that `--status` is council-log's *value* flag yet build's *boolean* verb (called out at `__init__.py:64-68`; `--status` confirmed in the set at `common.py:68`). The help-bias mitigates the only observable consequence. Whether a per-subcommand flag spec is worth the complexity is unresolved — the current single-set design is a deliberate simplicity bet.
