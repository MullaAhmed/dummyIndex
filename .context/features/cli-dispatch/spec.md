# CLI command dispatch — spec

`confidence: INFERRED`

## Intent

The wire-only layer behind `dummyindex context <subcommand>`. Its job is narrow on purpose: take raw `argv`, map the first token to a closed alphabet of subcommands, intercept `-h`/`--help` everywhere, then hand the remaining args to exactly one domain handler that returns a process exit code. No business logic lives here — every handler is a thin `cli/<sub>.py` module that parses flags, lazy-imports a `context/domains/...` function, prints, and returns an `int`. The hard invariant the layer protects: a `-h`/`--help` anywhere in a subcommand's args prints usage and returns 0 *before* any handler-side mandatory-flag check or filesystem side effect — the documented "bare-equip-mutates" hazard lived exactly at that seam, so help must short-circuit first.

## User-visible behavior

- `dummyindex context` (no args) or `dummyindex context -h|--help` → prints the full `USAGE` block, exit 0 (`cli/__init__.py:130-132`).
- `dummyindex context <unknown>` → `error: unknown context subcommand '<x>'` + `USAGE` to **stderr**, exit **2** (`cli/__init__.py:135-139`).
- `dummyindex context <sub> ... -h|--help` → prints `usage_for(sub)` (the slice of `USAGE` for that verb family) to stdout, exit 0, no side effects (`cli/__init__.py:144-146`).
- `dummyindex context <sub> <args>` → delegates to `_HANDLERS[sub](rest)` and returns its exit code (`cli/__init__.py:147`).
- A handler missing a required flag prints `error: ...` + a hint pointing at `dummyindex context <sub> --help`, exit 2 — centralized in `common.usage_error` (`cli/common.py:47-61`).

Help-token detection is deliberately biased toward help. `_wants_help` (`cli/__init__.py:58-81`) walks the args; when it lands on a flag in `_FLAGS_TAKING_VALUE` it normally skips the *next* token as that flag's value — **except** if that value is itself `-h`/`--help`, in which case help still wins (`cli/__init__.py:75-77`). The documented cost is the pathological "pass the literal string `--help` as a flag value" case, declared a non-use-case.

**`--depth` validation surfaces the real error (current behavior).** `init` and `reconcile` both accept a one-run `--depth light|standard|deep` council-effort override (parsed via `parse_kv_flags`, never written to config). Each validates the flag against `CouncilMode` values *up front* — an invalid value prints `error: --depth must be light|standard|deep, got <x>` and exits 2 (`cli/init.py:42-48`, `cli/reconcile.py:56-62`). Because the flag is already validated by that point, the subsequent `except ConfigError` around `resolve_depth` no longer masks a real config problem: a malformed `config.json` surfaces its actual `ConfigError` message via `error: <exc>`, exit 2 (`cli/init.py:49-56`, `cli/reconcile.py:63-68`). This replaces the old behavior where a `ConfigError` from any source was always misreported as the depth-flag message.

Two value-flag behaviors worth stating as user-visible contract:
- `query` errors (exit 2) on a *trailing* `--top-k`/`--budget` with no value following, instead of silently folding the flag name into the search string; non-integer values also exit 2.
- `query` exits **1** (not an error, a signal) when there were zero matches, so shells can detect "no hit" — documented in the `query` USAGE block itself (`cli/help.py:201-208`).

## Contracts

**The dispatch alphabet — `ContextSubcommand` (`dummyindex/context/enums.py:40-87`).** A `str, Enum` with **41 members** (verified by direct count of the block): `init, rebuild, bootstrap, check, hooks, enrich-plan, enrich-apply, features-rename, features-merge, flow-remove, section-write, scaffold-feature, assign-files, unassign-files, features-remove, mark-enriched, reconcile, reconcile-stamp, council-log, council-batch, conventions-write, refresh-indexes, query, reality-check, plan-update, reconcile-gate, dev-pick, onboard, config, preflight, doc-reorg, memory, propose, equip, build, audit, audit-log, status, wire, debt, statusline`. `ingest` is **not** here — it is a top-level alias for `init` resolved in `__main__`, called out in the enum docstring (`enums.py:41-45`).

**`dispatch(argv: list[str]) -> int` (`cli/__init__.py:129-147`).** `ContextSubcommand(subcmd)` does the membership check by construction — a raised `ValueError` is the "unknown subcommand" branch. `dispatch` and `resolve_context_root` are the only public exports (`cli/__init__.py:55`).

**Handler shape.** `_HANDLERS: dict[ContextSubcommand, Callable[[list[str]], int]]` (`cli/__init__.py:84-126`) maps every enum member to a handler. Single-verb modules export `run(argv) -> int`; multi-verb modules export `run_<verb>` siblings — e.g. `enrich.run_plan`/`enrich.run_apply`, `reconcile.run`/`reconcile.run_stamp`, `audit.run`/`audit.run_log`, and `features.run_rename`/`run_merge`/`run_flow_remove`/`run_section_write`/`run_scaffold`/`run_assign_files`/`run_unassign_files`/`run_remove`/`run_mark_enriched`. The map is exhaustive: `test_every_enum_member_has_a_handler` enforces that every enum member has a wired handler.

**`init` / `reconcile` depth contract.** Both call `resolve_depth(context_dir, DepthCommand.<X>, depth)` (`cli/init.py:50`, `cli/reconcile.py:64`). `resolve_depth` (`context/domains/config.py:323-341`) resolves precedence `depth_flag → config.command_depths[cmd] → config.mode → STANDARD` and raises `ConfigError` for an invalid flag — but the CLI's own up-front `CouncilMode`-membership guard means the only `ConfigError` reaching the handler's `except` is a malformed-config one, which is surfaced verbatim. `DepthCommand` (`config.py:84-99`) deliberately omits `rebuild` (deterministic, no council stage to consume a depth).

**Shared parsing surface (`cli/common.py`).** `resolve_context_root(scope, *, explicit_root, cwd) -> Path` (`common.py:13-45`): explicit root wins; an absolute scope is its own root; a relative scope under cwd resolves to cwd (the enclosing repo); else the scope itself. `parse_path_and_root` (`common.py:104-149`) pulls the positional scope + `--root`, forwarding `_FLAGS_TAKING_VALUE` flags *with* their values so subcommand parsers see them paired. `_FLAGS_TAKING_VALUE` (`common.py:64-75`) is the single global frozenset of value-taking flags — including `--depth` (`common.py:73`) — and drives both `_wants_help`'s skip logic and `parse_path_and_root`. `parse_kv_flags` (`common.py:183-204`) is the tiny `--key value` parser that recognizes `--depth`. `usage_error` (`common.py:47-61`), `pull_repeatable_flag` (`common.py:78-101`), and `resolve_doc_paths` (`common.py:154-181`) round out the helpers.

**Help text (`cli/help.py`).** `USAGE` is the hand-maintained canonical block (`help.py:17-419`), with the live equip schema version interpolated once at import (`help.py:416-419`). `usage_for(sub)` (`help.py:449-469`) slices `USAGE` by capturing every block whose opening line's first token equals `sub.value` plus its continuation lines — so `equip` returns the whole verb family. `_line_starts_subcommand` (`help.py:436-446`) is word-bounded so `reconcile` never matches `reconcile-stamp`/`reconcile-gate` and `audit` never matches `audit-log`.

**Shared hook-stdin helpers.** `memory.read_hook_stdin()` and `memory.resolve_transcript(hook, root)` are public (`cli/memory.py`) and consumed by `reconcile_gate.run` (`cli/reconcile_gate.py`). Both hook-fed handlers (`memory` nudge/breadcrumb/session-start, `reconcile-gate`) **always return 0** — a Stop/SessionStart/PreCompact hook must never fail the turn.

## Examples

Happy-path trace of `dummyindex context reconcile --depth deep`:
1. `__main__` resolves no alias; `dispatch(["reconcile", "--depth", "deep"])` runs (`cli/__init__.py:129`).
2. `ContextSubcommand("reconcile")` resolves to `RECONCILE`; `_wants_help(["--depth", "deep"])` is False (`__init__.py:144`).
3. `_HANDLERS[RECONCILE]` → `reconcile.run(["--depth", "deep"])` (`__init__.py:101, 147`).
4. `parse_path_and_root` + `parse_kv_flags` yield `parsed = {"depth": "deep"}`, `rest = []` (`reconcile.py:29-38`).
5. `"deep"` is in `{m.value for m in CouncilMode}`, so the up-front guard passes (`reconcile.py:56-62`).
6. `resolve_depth(context_dir, DepthCommand.RECONCILE, "deep")` returns `CouncilMode.DEEP`; no `ConfigError` (`reconcile.py:63-64`).
7. The read-only report prints with `council depth: deep`, exit 0 (`reconcile.py:76-77, 293`).

Error trace: `dummyindex context init --depth fast` → guard fails at `init.py:43`, prints `error: --depth must be light|standard|deep, got 'fast'`, exit 2 (`init.py:44-48`).

Error trace (malformed config): `dummyindex context reconcile` with a broken `config.json` → guard passes (no `--depth`), `resolve_depth` raises `ConfigError`, caught and printed as `error: <real message>`, exit 2 (`reconcile.py:65-68`).
