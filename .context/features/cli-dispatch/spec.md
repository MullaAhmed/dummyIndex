# CLI command dispatch — spec

confidence: INFERRED

## Intent

The thin command-routing surface for `dummyindex context <subcommand>`. Each
`cli/<sub>.py` module is **wire-only**: parse `argv` → lazy-import a domain
function → print the result → return an `int` exit code. No business logic lives
here; logic lives under `context/domains/<x>/`
(`.context/conventions/folder-organization.md:30-37`). The layer exists to keep a
single closed dispatch alphabet, a uniform help surface, and a uniform
exit-code contract in one place, decoupled from what each verb actually does.

This is a clean routing layer — the two former business-logic
modules (`context/domains/council.py`, `dev_pick.py`) were removed from the
cluster; what remains is the `cli/<sub>.py` modules plus shared `cli/common.py`,
`cli/help.py`, and the two enum sources that define the alphabet. `cli/wire.py`
(the interactive `dummyindex context wire` escalation surface for `config.wired`)
is the newest member.

## User-visible behavior

- The `dummyindex context <sub> [args]` surface. A bare invocation or a top-level
  `-h`/`--help` prints the full `USAGE` block and exits 0
  (`cli/__init__.py:128-130`).
- An unknown subcommand prints `error: unknown context subcommand '<x>'` plus
  `USAGE` to stderr and returns 2 (`cli/__init__.py:133-137`).
- **Help wins everywhere.** A `-h`/`--help` anywhere in a subcommand's args
  prints that subcommand's usage slice and returns 0 *before* any mandatory-flag
  parsing or side effect runs — read-only, never touching the filesystem
  (`cli/__init__.py:138-144`). `_wants_help` even biases to help when `--help`
  appears in a value position, so `build --status --help` still shows help
  (`cli/__init__.py:57-80`).
- Per-subcommand help is sliced out of the single hand-maintained `USAGE`
  reference by layout (a two-space-indented line opening a subcommand block, its
  more-deeply-indented continuation lines), so help can never drift from the
  reference text (`cli/help.py:1-9`, `usage_for` at `cli/help.py:427-447`).
- Enum-driven dispatch: only the closed `ContextSubcommand` alphabet routes;
  the verb family `equip`, `equip add-specialist`, `equip status` … all share one
  enum member and one handler (`cli/help.py:427-434`).

## Contracts

- **Handler shape.** Every subcommand exports `run(argv: list[str]) -> int`;
  multi-handler modules export `run_<verb>` siblings
  (`cli/__init__.py:3-7`) — e.g. `features.run_rename` / `features.run_merge` /
  `features.run_section_write` (`cli/features.py:33,119,243`),
  `audit.run` / `audit.run_log`, `enrich.run_plan` / `enrich.run_apply`
  (`cli/__init__.py:89-90,119-120`).
- **Exit-code contract.** `0` ok, `2` bad args / usage, `1` runtime failure; the
  boundary translates typed domain exceptions to codes, catching
  specific-before-base (`.context/conventions/coding-practices.md:57-62`). The
  `usage_error(subcommand, message) -> int` helper centralises the
  terse-error-plus-help-pointer pattern and always returns `2`
  (`cli/common.py:47-61`).
- **`ContextSubcommand` enum.** The closed dispatch alphabet — a
  `str, Enum` of 40 members from `INIT = "init"` through `STATUSLINE =
  "statusline"` (`context/enums.py:47-87`), including `WIRE = "wire"`
  (`context/enums.py:85`). `ingest` is a top-level alias for
  `init`, handled before the context dispatcher, and does not appear here
  (`context/enums.py:42-45`). `dispatch` constructs `ContextSubcommand(subcmd)`
  and rejects an unknown token via the `ValueError`
  (`cli/__init__.py:131-137`). The per-area equip alphabet
  (`enums_capability`, `enums_equipverb`, …) lives in
  `context/domains/equip/enums.py`, off the cross-area module by design
  (`context/enums.py:1-6`).
- **`_HANDLERS` table.** `dict[ContextSubcommand, Callable[[list[str]], int]]`
  maps every enum member to its handler `run`/`run_<verb>`
  (`cli/__init__.py:83-124`). `dispatch` resolves `_HANDLERS[sub](rest)` as its
  final step (`cli/__init__.py:145`). A test asserts every enum member has a
  handler (`test_debt_statusline_dispatch_test_every_enum_member_has_a_handler`,
  feature.json:120).
- **Shared parsing seam.** `cli/common.py` owns scope/root resolution and flag
  parsing reused by every subcommand: `resolve_context_root` (absolute scope =
  explicit root; relative subdir → enclosing repo) at `cli/common.py:13-45`,
  `parse_path_and_root` at `cli/common.py:103-148`, `pull_repeatable_flag` at
  `cli/common.py:77-100`, `parse_kv_flags` at `cli/common.py:182-203`. The
  value-taking flag alphabet is the single `_FLAGS_TAKING_VALUE` frozenset
  (`cli/common.py:64-74`), shared with `_wants_help`; it includes `--depth` (the
  one-run council-effort override threaded into the depth-bearing verbs
  `init`/`ingest`, `reconcile`, `audit`, `build`, each resolved through
  `config.resolve_depth`).

## Examples

- `dummyindex context query "retrieval" --top-k 5 --json` → `query.run` lazy-
  imports `query, render_json, render_markdown` from `context.domains.query`
  inside the function body and prints the scored top-K (`cli/query.py:7-15`).
- `dummyindex context section-write --feature cli-dispatch --section spec
  --from-file PATH` → `features.run_section_write` validates the section name at
  the boundary, then calls `write_section` and prints the target path
  (`cli/features.py:243-297`).
- `dummyindex context statusline` → `statusline.run` echoes the pre-computed
  freshness badge cache and **always exits 0** — a missing `.context/`, missing
  cache, or any exception collapses to empty stdout (`cli/statusline.py:37-66`).
- `dummyindex context debt --json` → `debt.run` lazy-imports `harvest_debt`,
  renders the JSON structure, and prints to stdout; `--write` also persists the
  markdown ledger (`cli/debt.py:34-68`).
- `dummyindex context refresh-indexes` → `refresh.py` calls
  `migrate.migrate_legacy_layout`, whose CLAUDE.md step is `migrate_claude_md_location`
  (`cli/migrate.py:72-87`). As of commit `1a2c212` this is now a pure wire-only
  wrapper: it lazy-imports `reconcile_claude_md` from
  `context/output/claude_md.py`, prints `result.message` to stdout, and prints any
  `result.warnings` to stderr — all folding/stripping/atomic-write/delete now lives
  in the domain helper and returns a frozen `ClaudeMdReconcileResult`. The
  `graph/` migration in `migrate_legacy_layout` is unchanged
  (`cli/migrate.py:12-69`), so `refresh-indexes` still works.
- `dummyindex context wire [--yes]` → `wire.run` re-classifies `config.wired`
  read-only (the same `default_plugins.classify_wired_entry` helper `status`
  uses), then prompts to wire each declared-but-absent plugin — the interactive
  escalation surface for the headless reconciler's *needs-user* bucket. It never
  hangs: `--yes` auto-affirms and a non-TTY stdin without `--yes` prints what
  *would* be prompted and exits 0 (`cli/wire.py`).
- `dummyindex context reconcile --depth light` → `reconcile.run` resolves the
  council effort via `config.resolve_depth(context_dir, DepthCommand.RECONCILE,
  "light")` (flag → `command_depths[reconcile]` → `mode` → `standard`) — a
  one-run override never written back to `config.json` (`cli/reconcile.py:52-56`).
