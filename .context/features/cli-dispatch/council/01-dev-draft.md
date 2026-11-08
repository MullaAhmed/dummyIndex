# CLI command dispatch — plan

`confidence: INFERRED`

## Bounded context

CLI dispatch owns token-to-command resolution, mutation-free help interception,
command-specific argument parsing, human-readable output, and process exit codes.
It does not own indexing, config persistence, plugin policy, settings mutation,
or subprocess execution; handlers coordinate those downstream domains and map
their results to the process boundary (`dummyindex/cli/__init__.py:68-166`,
`dummyindex/cli/init.py:87-242`).

Default-plugin responsibility is intentionally split across two CLI surfaces.
`context init` is headless post-build orchestration for reviewed defaults;
`context wire` is interactive escalation for declared entries that remain
unsatisfied. Both reuse domain classifiers/declaration/materialisation, while the
CLI alone owns gates, prompts, ordering, and stdout/stderr policy
(`dummyindex/cli/init.py:17-84`, `dummyindex/cli/wire.py:46-244`).

## Where it lives

- `dummyindex/__main__.py` owns top-level verbs and aliases. `ingest` rewrites to
  `context init`; `status` rewrites to `context status`; neither alias enlarges
  the context dispatch alphabet (`dummyindex/__main__.py:333-348`).
- `dummyindex/cli/__init__.py` owns context dispatch: help interception, enum
  validation, and the complete handler table
  (`dummyindex/cli/__init__.py:68-166`).
- `dummyindex/context/enums.py` owns `ContextSubcommand`, the closed command
  alphabet (`dummyindex/context/enums.py:108-164`, including the
  maintenance-family members `MAINTAIN`, `FLEET`, `DRIFT_ACK`, `EVOLVE`),
  plus the scan wire-format
  enums `ScanEvidence` and `ScanViolationSeverity` that `scan-check` consumes
  (`dummyindex/context/enums.py:74-105`).
- `dummyindex/cli/common.py` owns cross-handler parsing primitives and the shared
  value-taking flag set used by both help scanning and path/root parsing
  (`dummyindex/cli/common.py:49-174`).
- `dummyindex/cli/help.py` owns the canonical context usage template and derives
  exact subcommand-family slices from it
  (`dummyindex/cli/help.py:1-42`, `dummyindex/cli/help.py:745-765`); the
  `graph` verb family's help block lives in that template
  (`dummyindex/cli/help.py:261-287`), as do the `maintain`, `fleet`,
  and `evolve` family blocks (`dummyindex/cli/help.py:517-648`).
- `dummyindex/cli/graph.py` owns the wire-only symbol-graph query surface:
  seven-verb parsing, per-verb arity/flag scoping, and exit mapping over
  `context.domains.graph_query`; it is registered like every other verb, as
  `ContextSubcommand.GRAPH` in `_HANDLERS` (`dummyindex/cli/graph.py:23-188`,
  `dummyindex/cli/__init__.py:119`). The same one-row pattern admits the
  maintenance family: `maintain`, `fleet`, `drift_ack`, and `evolve` wire
  modules register through `_HANDLERS` rows only
  (`dummyindex/cli/__init__.py:135-144`).
- `dummyindex/cli/init.py` owns build/init parsing and the ordered reviewed-default
  post-build boundary; `dummyindex/cli/wire.py` owns nonblocking interactive
  resolution of `config.wired` (`dummyindex/cli/init.py:17-242`,
  `dummyindex/cli/wire.py:46-244`).
- `dummyindex/cli/rebuild.py` owns rebuild mode selection, the curated-index
  refusal, and post-success reporting; `dummyindex/cli/reconcile.py` owns the
  read-only report and the `reconcile-stamp` write boundary's error rendering
  (`dummyindex/cli/rebuild.py:39-185`, `dummyindex/cli/reconcile.py:31-370`).

## Architecture in three sentences

Top-level aliases feed a context dispatcher that validates one enum-backed
command, intercepts help before any handler, and invokes exactly one registered
function. Each handler parses its own syntax and coordinates downstream domains;
`init` builds first and then runs reviewed defaults in the fixed order gate,
disclose, validate, reconcile, declare, materialise, render. `wire` keeps prompts
out of headless init by classifying the persisted ledger read-only and passing one
approved entry through the same declaration and materialisation seams.

## Dispatch flow

1. `__main__.main` resolves top-level commands. `context` forwards argv unchanged;
   `ingest` prepends `init`; `status` prepends `status`
   (`dummyindex/__main__.py:333-348`).
2. `dispatch` prints full context help for empty/bare-help input, constructs
   `ContextSubcommand` to reject unknown verbs, and returns exit 2 with canonical
   usage on failure (`dummyindex/cli/__init__.py:148-158`).
3. `_wants_help` scans the remaining tokens with the same value-taking flag set
   used by path parsing. Any actual help token short-circuits to `usage_for`
   before mandatory flags, prompts, or side effects
   (`dummyindex/cli/__init__.py:68-91`,
   `dummyindex/cli/__init__.py:163-165`).
4. `_HANDLERS` maps every enum member to one `run(list[str]) -> int` function.
   The table is the only execution edge after validation
   (`dummyindex/cli/__init__.py:94-145`,
   `dummyindex/cli/__init__.py:166`).
5. `usage_for` slices one canonical template by word-bounded top-level command
   tokens, so `reconcile` cannot capture `reconcile-stamp` or
   `reconcile-gate` accidentally (`dummyindex/cli/help.py:732-765`).

## Default-plugin orchestration flow

1. `init.run` removes one-run boolean gates before shared path parsing. The
   canonical `--no-default-plugins` and legacy `--no-superpowers` spellings
   collapse into one non-persisted boolean
   (`dummyindex/cli/init.py:90-107`).
2. Init validates platform/depth and rejects a destructive rebuild of an enriched
   index unless `--force`, then completes the deterministic build and selected
   host guidance (`dummyindex/cli/init.py:109-219`).
3. Claude hooks are installed as a best-effort integration. Codex-only returns
   immediately afterward, so it never imports or executes Claude default-plugin
   orchestration (`dummyindex/cli/init.py:221-234`).
4. `_wire_default_plugins_step` returns on the one-run opt-out before any
   default-specific import, disclosure, config read/migration, settings action,
   or runner probe (`dummyindex/cli/init.py:17-27`).
5. Active runs print third-party trust disclosure, strictly validate config,
   migrate stale schema, fold equipment plugins into `wired`, reconcile missing
   reviewed defaults, and reread config. Malformed config prints one warning and
   stops defaults instead of treating corruption as absence
   (`dummyindex/cli/init.py:29-68`).
6. The exact selected `wired` tuple and resolved applicability feed both
   `wire_default_plugins` and `install_default_plugins`. Declaration completes
   before materialisation, preventing an unrelated all-default second pass
   (`dummyindex/cli/init.py:70-78`).
7. Pure domain renderers split informational and warning lines; CLI sends them to
   stdout and stderr respectively without converting target failures into init
   failure after the index build (`dummyindex/cli/init.py:79-84`).

## Source-evidenced patterns

- **Closed-alphabet handler table.** `ContextSubcommand` is both validator and key
  type for `_HANDLERS`; routing cannot reach an unregistered string command
  (`dummyindex/context/enums.py:108-164`,
  `dummyindex/cli/__init__.py:94-166`). New commands cost one enum member, one
  import, one table row, and one help block — the `maintain`/`fleet`/
  `drift-ack`/`evolve` additions changed no dispatcher logic.
- **Help-before-handler guard.** Central interception makes every context help
  path read-only, independent of handler quality
  (`dummyindex/cli/__init__.py:68-91`,
  `dummyindex/cli/__init__.py:163-165`).
- **Command-scoped application boundary.** `init.run` owns parse/build/integration
  order but delegates build, guidance, hooks, config, and plugin effects to their
  domains (`dummyindex/cli/init.py:87-242`).
- **Ordered post-build saga.** Default-plugin steps are independently recoverable
  after build, but their order is strict and selected state flows forward through
  every stage (`dummyindex/cli/init.py:17-84`).
- **Fail-closed validation before tolerant healing.** A strict `read_config`
  precedes migration/reconciliation helpers, preventing corrupt config from
  seeding reviewed defaults (`dummyindex/cli/init.py:51-68`).
- **Selected-state continuity.** One `wired` tuple feeds declaration and
  materialisation; interactive wire narrows that invariant to a one-entry tuple
  (`dummyindex/cli/init.py:70-78`, `dummyindex/cli/wire.py:221-244`).
- **Dual-stream result rendering.** Domain functions render `(info, warn)` and the
  CLI assigns stdout/stderr; domain code does not print
  (`dummyindex/cli/init.py:79-84`).
- **Prompt adapter with non-TTY guard.** `_PROMPT` is injectable, `--yes` bypasses
  it, and non-TTY input reports planned prompts without blocking
  (`dummyindex/cli/wire.py:41-43`, `dummyindex/cli/wire.py:125-173`).
- **Doc-as-data slicing.** One help template serves full and per-command usage;
  word-bounded extraction supports verb families without prefix collisions
  (`dummyindex/cli/help.py:718-765`).
- **Shared parse alphabet.** `_FLAGS_TAKING_VALUE` drives both help scanning and
  path/root forwarding, preventing the two token walkers from disagreeing on
  which token is a value (`dummyindex/cli/common.py:66-93`,
  `dummyindex/cli/common.py:123-174`).

## Dependencies and ownership

- **Upstream:** `dummyindex.__main__.main` is the process entry and owns aliases;
  `cli.dispatch` owns only the context namespace
  (`dummyindex/__main__.py:281-358`).
- **Command identity:** `ContextSubcommand` is imported by dispatcher and help.
  Handler registration and help blocks must remain complete for the same enum
  (`dummyindex/cli/__init__.py:19-63`,
  `dummyindex/cli/help.py:14-15`).
- **Init downstream:** build runner owns deterministic output; config owns
  schema/migration/intent reconciliation; `default_plugins` owns trust registry,
  settings declaration, materialisation, and pure renderers; hook/output modules
  own host integrations (`dummyindex/cli/init.py:29-44`,
  `dummyindex/cli/init.py:191-240`).
- **Wire downstream:** config owns the persisted ledger; the shared plugin
  classifier defines satisfied/acted/needs-user; declaration/materialisation
  operate on the one approved entry (`dummyindex/cli/wire.py:88-115`,
  `dummyindex/cli/wire.py:221-244`).
- **Rebuild/reconcile downstream:** build and enriched refresh return a
  `LayoutMigration`; the pure `format_migration_report` (shared with install
  auto-init) renders it; `read_meta` owns the newer-schema text that
  `reconcile-stamp` classifies (`dummyindex/context/build/upgrade.py:524-665`,
  `dummyindex/context/build/meta.py:68-79`).
- **Persistent state:** CLI owns no stored model. It reads downstream
  `.context/config.json` and writes only through domain services.
- **Output contract:** handlers return integers and print only boundary text.
  Default-plugin target failures and interactive declines remain output states,
  not exceptions propagated through the dispatcher
  (`dummyindex/cli/init.py:63-84`, `dummyindex/cli/wire.py:137-173`).

## Data model

The dispatcher carries `list[str]`, `ContextSubcommand`, handler callables, and
integer exit codes. It persists nothing. `_HANDLERS` is the runtime routing table;
`USAGE` is the canonical human contract
(`dummyindex/cli/__init__.py:94-166`, `dummyindex/cli/help.py:17-715`).

`init` carries one local default-plugin state tuple: `(wired,
default_plugins_enabled)`. The tuple comes from reread config or
`default_wired()` only when config is absent, then the same `wired` selection
feeds both domain passes (`dummyindex/cli/init.py:51-78`). `wire` carries
classified `(WiredEntry, WiredClass)` pairs and transient `wired_now`, `skipped`,
and `remaining` output buckets; it never rewrites the config ledger
(`dummyindex/cli/wire.py:88-173`). `rebuild` only prints `LayoutMigration`
and `(artifact, error)` pairs (`dummyindex/cli/rebuild.py:139-158`).

Exit semantics are command-specific within a shared convention: 0 for success or
best-effort completion, 2 for usage/config validation at the boundary, and other
runtime codes where a handler explicitly defines them. The dispatcher forwards
handler codes unchanged (`dummyindex/cli/__init__.py:148-166`).

## Key decisions

- **Help wins before all handlers.** A literal help flag used as a value is an
  accepted sacrificed edge case; preventing accidental mutating probes is the
  stronger invariant (`dummyindex/cli/__init__.py:68-91`,
  `dummyindex/cli/__init__.py:163-165`).
- **Enum construction is command validation.** One alphabet drives routing and
  help identity; no duplicate string validator can drift
  (`dummyindex/cli/__init__.py:148-158`,
  `dummyindex/context/enums.py:108-164`).
- **The plugin opt-out gates plugin work, not indexing.** Init still builds and
  writes selected host guidance before the default step; the canonical help text
  correctly promises only to skip default Claude plugins
  (`dummyindex/cli/help.py:21-42`, `dummyindex/cli/init.py:191-240`).
- **Disclosure precedes mutation.** Reviewed third-party provenance appears before
  config healing, settings writes, or runner probes
  (`dummyindex/cli/init.py:46-62`).
- **Corruption is not absence.** Strict config validation stops defaults rather
  than falling back to `default_wired()` on malformed state
  (`dummyindex/cli/init.py:51-70`).
- **Reconciliation is visible in the same run.** Config is reread after migration,
  equipment folding, and reviewed-default backfill; that exact ledger drives both
  downstream stages (`dummyindex/cli/init.py:51-78`).
- **Headless init never prompts.** Best-effort classification and effects remain
  noninteractive; `context wire` owns explicit confirmation and non-TTY behavior
  (`dummyindex/cli/wire.py:1-26`, `dummyindex/cli/wire.py:125-173`).
- **Interactive approval is target-scoped.** The one selected entry is passed to
  both declaration and materialisation, so approving a custom target cannot
  install unrelated reviewed defaults (`dummyindex/cli/wire.py:221-244`).
- **Per-target failure is reported, not escalated to build failure.** The index is
  already complete when defaults run; init returns 0 after warning output
  (`dummyindex/cli/init.py:233-242`).
- **Upgrade effects are reported, never fatal.** Rebuild exits 0 after printing
  migration removals/backups/errors; a failed artefact names its retry command
  (`dummyindex/cli/rebuild.py:157-158`, `dummyindex/context/build/upgrade.py:660-664`).
- **Newer-schema meta is an upgrade problem, not a missing index.** Only on a
  no-commit stamp does `reconcile-stamp` re-read `meta.json`, so the advice
  never points a newer index at a re-clustering `ingest`
  (`dummyindex/cli/reconcile.py:160-173`, `dummyindex/cli/reconcile.py:205-227`).
- **Canonical help leads with the canonical flag.** The legacy
  `--no-superpowers` spelling remains visible only as a compatibility alias
  (`dummyindex/cli/help.py:21-36`, `dummyindex/__main__.py:150-195`).

## Open questions

- Should init return or emit a structured aggregate that separates build,
  guidance, hooks, declaration, and materialisation outcomes? Current automation
  must parse stdout/stderr to detect partial readiness.
- Should `context wire` recognize a reviewed built-in and render its pinned trust
  disclosure instead of labeling every absent valid plugin “untrusted”
  (`dummyindex/cli/wire.py:193-200`)?
- Should an interactive declaration/materialisation failure return nonzero or
  offer JSON output? The current command reports needs-user and exits 0
  (`dummyindex/cli/wire.py:156-173`).
- Should `usage_for` and handler completeness be generated directly from one
  declarative command registry? Enum, handler table, and help template are tested
  together but remain three authored structures.
- Should `_FLAGS_TAKING_VALUE` become command-aware? Its global view intentionally
  favors help over ambiguity, but a token such as `--status` can be a value flag
  for one command and a boolean mode for another.
- Rebuild's migration `warning:` lines go to stdout, unlike init's dual-stream
  rule (`dummyindex/cli/rebuild.py:139-146`), and `context init` runs the same
  `build_all` migration without printing it (`dummyindex/cli/init.py:191-207`).
  Intended?
- Newer-schema detection substring-matches `read_meta`'s prose
  (`dummyindex/cli/reconcile.py:205`, `dummyindex/context/build/meta.py:76-79`);
  rewording it silently restores the ingest advice. A typed exception would not.
- `maintain --help` shows three stray `gc signal` lines
  (`dummyindex/cli/help.py:543-545`).
