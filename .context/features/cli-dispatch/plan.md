# CLI command dispatch — plan

`confidence: INFERRED`

## Where it lives

**Boundary.** This feature owns argv → one `ContextSubcommand` → one handler,
read-only help, per-command flag parsing, stream choice, and exit codes. It
persists nothing and owns no domain policy (indexing, config schema, plugin
trust/settings, subprocess). Handlers for `graph`, `maintain`/`drift-ack`,
`fleet`, `evolve`, `equip`, and `build` belong to graph-query, maintenance,
fleet, evolution, and equip; here each is one `_HANDLERS` row plus one help
block. `dummyindex/__main__.py` is install-surface's (upstream);
`dummyindex/cli/__init__.py` is co-owned with tree-enrich.

- **Dispatcher** — `dummyindex/cli/__init__.py:139-156`. `dispatch` prints
  `USAGE` for empty/bare help (`:140-142`), validates the verb by constructing
  `ContextSubcommand` (unknown → stderr + exit 2, `:144-149`), runs the help
  guard (`:153-155`), then calls one handler and forwards its code (`:156`).
- **Registry** — `_HANDLERS: dict[ContextSubcommand, Callable[[list[str]], int]]`,
  one row per member (`dummyindex/cli/__init__.py:85-136`).
- **Closed alphabet** — `ContextSubcommand` (`dummyindex/context/enums.py:101-157`)
  is both validator and registry key; aliases are deliberately absent
  (`:104-105`). The other enums in that file are not dispatch surface.
- **Help guard** — `_wants_help` (`dummyindex/cli/__init__.py:63-82`) is true
  for `-h`/`--help` anywhere, including a value flag's value slot.
- **Doc-as-data help** — one hand-written `_USAGE_TEMPLATE`
  (`dummyindex/cli/help.py:14-707`; `USAGE` at `:712`) is both full help and the
  source of every per-verb slice: `usage_for` keeps each two-space block whose
  first token equals `sub.value` (`:720-762`), so `reconcile` never captures
  `reconcile-stamp` and `equip` collects its whole verb family.
- **Shared parsing** — `dummyindex/cli/common.py`: `resolve_context_root`
  (`:13-38`), `usage_error` (`:41-52`), `pull_repeatable_flag` (`:85-109`),
  `parse_path_and_root` (`:112-155`), `parse_kv_flags` (`:191-223`).
  `_FLAGS_TAKING_VALUE` (`:55-82`) is one alphabet for three walkers —
  `_wants_help` (`dummyindex/cli/__init__.py:76`), `parse_path_and_root`
  (`:138-147`), `parse_kv_flags`'s allowlist assertion (`:202-207`) — and is
  authoritative only for them; self-parsing handlers own their value flags
  (`dummyindex/cli/graph.py:46-76`).
- **Wire-only handler shape** — lazy-import the domain inside `run`, print,
  return a code (`dummyindex/cli/init.py:88`, `dummyindex/cli/scan.py:20-25`;
  `.context/conventions/folder-organization.md:32-36`). Domain renderers return
  `(info, warn)`; the CLI assigns stdout/stderr
  (`dummyindex/cli/init.py:79-84`).
- **`init`** — `dummyindex/cli/init.py:87-242`: parse, build, guidance, hooks,
  then, only when `use_claude` (`:233-240`), `_wire_default_plugins_step`
  (`:17-84`), a **fixed-order pipeline, fail-closed at the first gate**:
  one-run opt-out (`:26-27`) → disclosure (`:48-49`) → strict `read_config`
  (`:55`) → migrate/fold/reconcile (`:56-61`) → reread (`:62`) → declare
  (`:73`) → materialise (`:74-78`) → render (`:79-84`). Nothing rolls back;
  `ConfigError`/`OSError` prints one stderr warning and returns (`:63-68`).
- **`wire`** — `dummyindex/cli/wire.py:27-211`, the only `cli/` module that
  prompts. **Callable seam**: `_PROMPT = input` (`:24`) is passed into `_wire`
  (`:44`, `:47-53`), the project's DI convention
  (`.context/conventions/coding-practices.md:64-67`). Non-TTY without `--yes`
  lists would-prompt entries and exits 0 (`:95-105`); prompt errors read as
  decline (`:179-188`).
- **`rebuild`, `reconcile`, `scan`, …** — the remaining handlers in
  `feature.json` `files`; their user-visible contracts are in `spec.md`.

**Dependencies.**

- Upstream: `main` calls `dispatch` three ways — `context` unchanged,
  `ingest` → `["init", …]`, `status` → `["status", …]`
  (`dummyindex/__main__.py:317-332`); `_print_help` also reads the alphabet
  (`:224-233`).
- Import fan-in: `dummyindex/cli/__init__.py:16-56` imports every handler
  module eagerly, so module-level domain imports load on every call, `--help`
  included: `dummyindex/cli/help.py:11` (equip domain),
  `dummyindex/cli/config.py:13`, `dummyindex/cli/onboard.py:17,27`,
  `dummyindex/cli/plan_update.py:16-17`, and `dummyindex/cli/equip/*` (which
  reaches `context.default_plugins` via `dummyindex/cli/equip/install.py:17`).
  Lazy import is the convention, not an invariant.
- Package cycle `cli ⇄ installer`: `dummyindex/cli/init.py:128`,
  `dummyindex/cli/bootstrap.py:16`, `dummyindex/cli/onboard.py:27`,
  `dummyindex/cli/equip/dispatch.py:48`, `dummyindex/cli/check.py:181,233,325`
  import `installer.*`; `dummyindex/installer/install/project_init.py:41,174`
  imports `cli.migrate` and `cli.equip.common`. The installer side is
  function-local, so no import-time cycle; the layering rule treats
  `cli/installer` as peers (`.context/conventions/coding-practices.md:89-90`).
- Handler → handler: `dummyindex/cli/check.py:21` → `rebuild.run`,
  `dummyindex/cli/maintain.py:333` → `reconcile.run_stamp`,
  `dummyindex/cli/rebuild.py:29` / `dummyindex/cli/bootstrap.py:18` / `refresh.py:10` →
  `migrate`, `guard_doc_write.py:17` / `reconcile_gate.py:13` → `memory`,
  `statusline.py:15` → `plan_update` (all under `dummyindex/cli/`).
  `rebuild.run` and `run_stamp` exit codes propagate to `check`
  (`dummyindex/cli/check.py:120-124`) and `maintain stamp`
  (`dummyindex/cli/maintain.py:363-366`). Already flagged against the stated rule
  (`.context/conventions/folder-organization.md:77-83`).
- Downstream: `init` → `build_all`, `domains.config` (`resolve_depth`,
  `read_config`, migrators), `context.default_plugins`, `output.agents_md`,
  `context.hooks`; `wire` → `read_config`, `classify_wired_entry`, and the
  private `_already_decided` / `_split_target`
  (`dummyindex/cli/wire.py:63`, `:164`, `:174`, `:198`); `rebuild` →
  `format_migration_report` (`dummyindex/context/build/upgrade.py:577-615`,
  shared with `dummyindex/installer/install/project_init.py:47`);
  `reconcile-stamp` → `read_meta` by message text
  (`dummyindex/cli/reconcile.py:199-221` ↔
  `dummyindex/context/build/meta.py:73-76`). Nothing under `context/domains/`
  imports `cli` (`.context/conventions/folder-organization.md:27-28`).

## Architecture in three sentences

`__main__` rewrites aliases into context argv, and `dispatch` validates the
verb by enum construction, answers any help token from the template slice
before a handler runs, and invokes exactly one registered
`run(list[str]) -> int`. Each handler parses its own syntax with
`cli/common.py`, by convention lazy-imports its domain, prints, and returns a
code the dispatcher forwards unchanged. `init` fails closed before the build
and runs guidance → hooks → default plugins best-effort after it, and `wire` is
the separate interactive surface that routes one approved entry through the
same declare/materialise seams.

## Data model

- Dispatcher: `list[str]` in, `ContextSubcommand`, one handler, `int` out.
  Runtime tables only: `_HANDLERS` (`dummyindex/cli/__init__.py:85-136`) and
  `USAGE` (`dummyindex/cli/help.py:712`).
- `init`: one-run booleans stripped before parsing
  (`dummyindex/cli/init.py:92-107`); post-build state is `(wired, enabled)` —
  `cfg.wired` from the reread config, `default_wired()` only when config is
  absent (`:70-72`).
- `wire`: `(WiredEntry, WiredClass)` pairs plus transient `wired_now` /
  `skipped` / `remaining` lists (`dummyindex/cli/wire.py:84-143`); never
  rewrites `config.wired`.
- Exit codes: `0` success or best-effort completion, `2` usage/validation,
  `1` only where a handler defines it (`dummyindex/cli/scan.py:88`,
  `dummyindex/cli/reconcile.py:154-167`). The dispatcher itself adds only `2`
  for an unknown verb (`dummyindex/cli/__init__.py:146-149`).

## Key decisions

- **Help beats every handler, even in a value slot**, because a bare mutating
  verb (`equip`) was the probing hazard; the cost is a literal `--help` value
  (`dummyindex/cli/__init__.py:66-69`, `:150-152`). Every verb × `-h`/`--help`
  exits 0 without mutating cwd (`tests/cli/test_subcommand_help.py:23-49`).
- **Enum construction is the only verb validator**, so routing, help slices,
  and the top-level list share one alphabet ("derived from the enum so this
  list can never drift", `dummyindex/__main__.py:225-226`). Aliases rewrite
  argv upstream (`:322-332`) and never enter it. The three authored structures
  are aligned by tests, not generation: `test_every_enum_member_has_a_handler`
  (`tests/cli/test_debt_statusline_dispatch.py:27-30`),
  `test_usage_documents_every_subcommand`
  (`tests/cli/test_cli_doc_sync.py:43-56`), and the help test above.
- **Value flags are allowlisted per command**, because the shared alphabet let
  `--platform codex` be parsed and silently ignored
  (`dummyindex/cli/common.py:196-201`).
- **Usage errors point at `--help`**, because bare-verb probing used to mutate
  the repo for `equip` (`dummyindex/cli/common.py:41-52`).
- **One-run flags never persist.** `--no-default-plugins` / `--no-superpowers`
  collapse to one boolean stripped before parsing
  (`dummyindex/cli/init.py:90-107`); `--depth` is per-run (`:111-113`,
  `dummyindex/cli/reconcile.py:29-31`). The opt-out returns before any
  default-specific import, config, settings, or runner work
  (`dummyindex/cli/init.py:24-27`) and skips neither indexing nor guidance.
  Help leads with the canonical flag and labels the alias
  (`dummyindex/cli/help.py:30-32`, `dummyindex/__main__.py:134-141`).
- **A curated index refuses a destructive build** (exit 2 without
  `--force` / `--full`), because a stray `ingest` "silently shatters the
  curated taxonomy" and hooks may call `rebuild` expecting a cheap refresh
  (`dummyindex/cli/init.py:167-182`, `dummyindex/cli/rebuild.py:107-121`).
- **Disclosure precedes plugin mutation**, because defaults include reviewed
  third-party code (`dummyindex/cli/init.py:46-49`).
- **Strict read before tolerant healing**, so malformed state never falls back
  to `default_wired()` (`dummyindex/cli/init.py:53-55`); the reread ledger
  drives both passes so backfilled defaults apply in the same run (`:60-62`,
  `:70-78`).
- **Only `wire` prompts**, so install/ingest never block a pipe or CI
  (`dummyindex/cli/wire.py:3-5`, `:6-7`; `dummyindex/cli/help.py:662-665`).
- **Approval is target-scoped**: `(entry,)` feeds both seams so a custom
  plugin can never install unrelated defaults
  (`dummyindex/cli/wire.py:194-196`, `:206-211`).
- **Post-build failures are warnings, not exit codes**, because the index is
  already complete: guidance (`dummyindex/cli/init.py:213-217`), hooks
  (`:229-231`), plugins (`:83-84`), migration steps
  (`dummyindex/context/build/upgrade.py:492-498`), legacy CLAUDE.md fold
  (`dummyindex/cli/rebuild.py:26-27`).
- **Newer-schema meta means "upgrade", not "ingest"**: only a newer-schema
  `read_meta` refusal changes the fix
  (`dummyindex/cli/reconcile.py:154-167`, `:202-208`).

## Open questions

- **One declarative registry?** Enum, `_HANDLERS`, and `_USAGE_TEMPLATE` are
  aligned only by tests, and the template already drifts inside blocks:
  `maintain --help` prints three stray `gc signal` lines
  (`dummyindex/cli/help.py:540-542`).
- **Command-aware `_FLAGS_TAKING_VALUE`?** The global set biases to help
  (`dummyindex/cli/__init__.py:67-69`), but `--status` is council-log's value
  flag and build's boolean verb.
- **Config validity gates indexing.** Without `--depth`, `resolve_depth` reads
  the full config (`dummyindex/context/domains/config.py:466-469`) and `init`
  exits 2 on `ConfigError` before the build (`dummyindex/cli/init.py:158-165`),
  so neither `--no-default-plugins` nor `--platform codex` isolates indexing
  from a malformed plugin field; the post-build branch (`:63-68`) is the only
  guard when `--depth` skips that read. Intended?
- **Exit code for partial outcomes.** `init` returns 0 after plugin warnings
  (`dummyindex/cli/init.py:242`), `wire` after `could not wire`
  (`dummyindex/cli/wire.py:132`, `:143`); automation must scrape streams.
- **Stream policy is per-handler.** `rebuild` prints migration `warning:`
  lines to stdout (`dummyindex/cli/rebuild.py:144-145`), unlike `init`'s
  dual-stream rule, and `init` runs the same `build_all` migration without
  printing it (`dummyindex/cli/init.py:191-207`).
- **Text-coupled meta check.** `_NEWER_SCHEMA_MARKER` substring-matches
  `read_meta`'s prose (`dummyindex/cli/reconcile.py:199`, `:218` ↔
  `dummyindex/context/build/meta.py:73-76`); rewording it silently restores
  the ingest advice. A typed exception would not.
- **Private cross-feature imports.** `wire` depends on underscore-private
  `context.default_plugins` helpers (`dummyindex/cli/wire.py:63`, `:164`,
  `:174`, `:198`); a rename there breaks this feature with no public contract
  between.
