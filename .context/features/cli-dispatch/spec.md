# cli-dispatch — spec

`confidence: INFERRED`

## Intent

The wire-only layer behind `dummyindex context <subcommand>`. Its job is narrow on purpose: take raw `argv`, map the first token to a closed alphabet of subcommands, intercept `-h`/`--help` everywhere, then hand the remaining args to exactly one domain handler that returns a process exit code. No business logic lives here — every handler is a thin `cli/<sub>.py` module that parses flags, lazy-imports a `context/domains/...` function, prints, and returns an `int`. The dispatcher itself is `dummyindex/cli/__init__.py:129-147`; the alphabet is `ContextSubcommand` in `dummyindex/context/enums.py:40-87`.

The hard invariant the layer protects: **a `-h`/`--help` anywhere in a subcommand's args prints usage and returns 0 *before* any handler-side mandatory-flag check or filesystem side effect** (`cli/__init__.py:140-146`). The docstring there names the original hazard — "the bare-equip-mutates hazard lived exactly here" — a verb that probed by running bare would mutate the repo, so help must short-circuit first.

## User-visible behavior

- `dummyindex context` (no args) or `dummyindex context -h|--help` → prints the full `USAGE` block, exit 0 (`cli/__init__.py:130-132`).
- `dummyindex context <unknown>` → `error: unknown context subcommand '<x>'` + `USAGE` to **stderr**, exit **2** (`cli/__init__.py:135-139`).
- `dummyindex context <sub> ... -h|--help` → prints `usage_for(sub)` (the slice of `USAGE` for that verb family) to stdout, exit 0, no side effects (`cli/__init__.py:144-146`).
- `dummyindex context <sub> <args>` → delegates to `_HANDLERS[sub](rest)` and returns its exit code (`cli/__init__.py:147`).
- A handler missing a required flag prints `error: ...` + a hint pointing at `dummyindex context <sub> --help`, exit 2 — centralized in `common.usage_error` (`cli/common.py:47-61`).

Help-token detection is deliberately biased toward help. `_wants_help` (`cli/__init__.py:58-81`) walks the args; when it lands on a flag in `_FLAGS_TAKING_VALUE` it normally skips the *next* token as that flag's value — **except** if that value is itself `-h`/`--help`, in which case help still wins (`cli/__init__.py:75-77`). The documented cost is the pathological "pass the literal string `--help` as a flag value" case, declared a non-use-case.

Two recent value-flag behaviors worth stating as user-visible contract:
- `query` errors (exit 2) on a *trailing* `--top-k`/`--budget` with no value following, instead of silently folding the flag name into the search string (`cli/query.py:60-68`). Non-integer values also exit 2 (`cli/query.py:34-58`); the `--top-k=`/`--budget=` empty form raises via `int("")` on the `startswith` arms.
- `query` exits **1** (not an error, a signal) when there were zero matches, so shells can detect "no hit" (`cli/query.py:101-102`).

## Contracts

**The dispatch alphabet — `ContextSubcommand` (`dummyindex/context/enums.py:40-87`).** A `str, Enum` with **41 members**, verified by direct count of the source: `init, rebuild, bootstrap, check, hooks, enrich-plan, enrich-apply, features-rename, features-merge, flow-remove, section-write, scaffold-feature, assign-files, unassign-files, features-remove, mark-enriched, reconcile, reconcile-stamp, council-log, council-batch, conventions-write, refresh-indexes, query, reality-check, plan-update, reconcile-gate, dev-pick, onboard, config, preflight, doc-reorg, memory, propose, equip, build, audit, audit-log, status, wire, debt, statusline`. Both `HOOKS = "hooks"` (`enums.py:51`) and `WIRE = "wire"` (`enums.py:85`) are present. `ingest` is **not** here — it's a top-level alias for `init` resolved in `__main__`, called out in the enum docstring (`enums.py:41-45`).

**The dispatch contract (`cli/__init__.py:129-147`).** `dispatch(argv: list[str]) -> int`. `ContextSubcommand(subcmd)` does the membership check by construction — a `ValueError` is the "unknown subcommand" branch. `dispatch` and `resolve_context_root` are the only public exports (`cli/__init__.py:55`).

**Handler shape.** `_HANDLERS: dict[ContextSubcommand, Callable[[list[str]], int]]` (`cli/__init__.py:84-126`) maps every enum member to a handler. Single-verb modules export `run(argv) -> int`; multi-verb modules export `run_<verb>` siblings — e.g. `enrich.run_plan`/`enrich.run_apply`, `reconcile.run`/`reconcile.run_stamp`, `audit.run`/`audit.run_log`, and `features.run_rename`/`run_merge`/`run_flow_remove`/`run_section_write`/`run_scaffold`/`run_assign_files`/`run_unassign_files`/`run_remove`/`run_mark_enriched`. The map is exhaustive: a test (`test_every_enum_member_has_a_handler`) enforces that every enum member has a wired handler.

**The `hooks` handler (`cli/hooks.py:7-89`) is real and dispatched** (`cli/__init__.py:89`). Verb-dispatched: `install | uninstall | status | defer-check` (`hooks.py:31`). `--global` targets `~/.claude/settings.json`, default `--local` is the repo's `.claude/settings.json` (`hooks.py:36-44`). `defer-check` is a pure exit-code probe for the global hook guard — exit 0 when the repo has its own local install, else 1 (`hooks.py:53-55`).

**`council` and `dev-pick` are live.** `council.run` (`cli/council.py`, also hosting the `council-log backfill` subverb) is wired at `cli/__init__.py:103`; `dev_pick.run` at `cli/__init__.py:111`. Both lazy-import real domain modules — `context/domains/council.py` and `context/domains/dev_pick.py` exist on disk. Neither was removed.

**Shared parsing surface (`cli/common.py`).** `resolve_context_root(scope, *, explicit_root, cwd) -> Path` (`common.py:13-45`) decides where `.context/`/`CLAUDE.md` live: explicit root wins; an absolute scope is its own root; a relative scope under cwd resolves to cwd (the enclosing repo); else the scope itself. `parse_path_and_root` (`common.py:104-149`) pulls the positional scope + `--root`, forwarding `_FLAGS_TAKING_VALUE` flags *with* their values so subcommand parsers see them paired. `_FLAGS_TAKING_VALUE` (`common.py:64-75`) is the single global set of value-taking flags — the same set drives `_wants_help`'s skip logic. `usage_error` (`common.py:47-61`), `pull_repeatable_flag` (`common.py:78-101`), `resolve_doc_paths` (`common.py:154-181`), and `parse_kv_flags` (`common.py:183-204`) round out the helpers.

**Help text (`cli/help.py`).** `USAGE` is the hand-maintained canonical block (`help.py:17-417`), with the live equip schema version interpolated once at import (`help.py:414-417`). `usage_for(sub)` (`help.py:447-467`) slices `USAGE` by walking it and capturing every block whose opening line's first token equals `sub.value` plus its continuation lines — so `equip` returns the whole verb family. `_line_starts_subcommand` (`help.py:434-444`) is word-bounded so `reconcile` never matches `reconcile-stamp`/`reconcile-gate` and `audit` never matches `audit-log`.

**Shared hook-stdin helpers.** `memory.read_hook_stdin()` and `memory.resolve_transcript(hook, root)` are public (`cli/memory.py:22-51`) and consumed by `reconcile_gate.run` (`cli/reconcile_gate.py:12, 24-25`). Both hook-fed handlers (`memory` nudge/breadcrumb/session-start, `reconcile-gate`) **always return 0** — a Stop/SessionStart/PreCompact hook must never fail the turn (`memory.py:94, 101, 107`; `reconcile_gate.py:35`).

## Examples

```text
$ dummyindex context                      # → full USAGE, exit 0
$ dummyindex context bogus                # → "error: unknown context subcommand 'bogus'" (stderr), exit 2
$ dummyindex context query --help         # → usage_for(QUERY) slice, exit 0, no FS touch
$ dummyindex context build --status --help  # help wins even after a value-flag → exit 0
$ dummyindex context query "auth flow"    # delegates to query.run; exit 0 if matches else 1
$ dummyindex context query find --top-k   # trailing value-flag, no value → exit 2
$ dummyindex context hooks defer-check    # silent probe; exit 0 if repo has local install else 1
```
