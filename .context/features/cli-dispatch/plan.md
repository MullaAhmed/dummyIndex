# CLI command dispatch — plan

confidence: INFERRED

## Bounded context

CLI dispatch owns token-to-command resolution, mutation-free help interception,
command-specific argument parsing, human-readable output, and process exit codes.
It does not own indexing, config persistence, plugin policy, settings mutation,
or subprocess execution; handlers coordinate those downstream domains and map
their results to the process boundary (`dummyindex/cli/__init__.py:62-154`,
`dummyindex/cli/init.py:87-231`).

Default-plugin responsibility is intentionally split across two CLI surfaces.
`context init` is headless post-build orchestration for reviewed defaults;
`context wire` is interactive escalation for declared entries that remain
unsatisfied. Both reuse domain classifiers/declaration/materialisation, while the
CLI alone owns gates, prompts, ordering, and stdout/stderr policy
(`dummyindex/cli/init.py:17-84`, `dummyindex/cli/wire.py:46-244`).

## Where it lives

- `dummyindex/__main__.py` owns top-level verbs and aliases. `ingest` rewrites to
  `context init`; `status` rewrites to `context status`; neither alias enlarges
  the context dispatch alphabet (`dummyindex/__main__.py:259-315`).
- `dummyindex/cli/__init__.py` owns context dispatch: help interception, enum
  validation, and the complete handler table
  (`dummyindex/cli/__init__.py:62-154`).
- `dummyindex/context/enums.py` owns `ContextSubcommand`, the closed command
  alphabet (`dummyindex/context/enums.py:41-91`).
- `dummyindex/cli/common.py` owns cross-handler parsing primitives and the shared
  value-taking flag set used by both help scanning and path/root parsing
  (`dummyindex/cli/common.py:50-172`).
- `dummyindex/cli/help.py` owns the canonical context usage template and derives
  exact subcommand-family slices from it
  (`dummyindex/cli/help.py:1-42`, `dummyindex/cli/help.py:504-557`).
- `dummyindex/cli/init.py` owns build/init parsing and the ordered reviewed-default
  post-build boundary; `dummyindex/cli/wire.py` owns nonblocking interactive
  resolution of `config.wired` (`dummyindex/cli/init.py:17-231`,
  `dummyindex/cli/wire.py:46-244`).

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
   (`dummyindex/__main__.py:259-315`).
2. `dispatch` prints full context help for empty/bare-help input, constructs
   `ContextSubcommand` to reject unknown verbs, and returns exit 2 with canonical
   usage on failure (`dummyindex/cli/__init__.py:136-146`).
3. `_wants_help` scans the remaining tokens with the same value-taking flag set
   used by path parsing. Any actual help token short-circuits to `usage_for`
   before mandatory flags, prompts, or side effects
   (`dummyindex/cli/__init__.py:62-85`,
   `dummyindex/cli/__init__.py:147-153`).
4. `_HANDLERS` maps every enum member to one `run(list[str]) -> int` function.
   The table is the only execution edge after validation
   (`dummyindex/cli/__init__.py:88-133`,
   `dummyindex/cli/__init__.py:154`).
5. `usage_for` slices one canonical template by word-bounded top-level command
   tokens, so `reconcile` cannot capture `reconcile-stamp` or
   `reconcile-gate` accidentally (`dummyindex/cli/help.py:524-557`).

## Default-plugin orchestration flow

1. `init.run` removes one-run boolean gates before shared path parsing. The
   canonical `--no-default-plugins` and legacy `--no-superpowers` spellings
   collapse into one non-persisted boolean
   (`dummyindex/cli/init.py:90-107`).
2. Init validates platform/depth and rejects a destructive rebuild of an enriched
   index unless `--force`, then completes the deterministic build and selected
   host guidance (`dummyindex/cli/init.py:109-208`).
3. Claude hooks are installed as a best-effort integration. Codex-only returns
   immediately afterward, so it never imports or executes Claude default-plugin
   orchestration (`dummyindex/cli/init.py:210-229`).
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
  (`dummyindex/context/enums.py:41-91`,
  `dummyindex/cli/__init__.py:88-154`).
- **Help-before-handler guard.** Central interception makes every context help
  path read-only, independent of handler quality
  (`dummyindex/cli/__init__.py:62-85`,
  `dummyindex/cli/__init__.py:147-153`).
- **Command-scoped application boundary.** `init.run` owns parse/build/integration
  order but delegates build, guidance, hooks, config, and plugin effects to their
  domains (`dummyindex/cli/init.py:87-231`).
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
  (`dummyindex/cli/help.py:504-557`).
- **Shared parse alphabet.** `_FLAGS_TAKING_VALUE` drives both help scanning and
  path/root forwarding, preventing the two token walkers from disagreeing on
  which token is a value (`dummyindex/cli/common.py:66-91`,
  `dummyindex/cli/common.py:121-172`).

## Dependencies and ownership

- **Upstream:** `dummyindex.__main__.main` is the process entry and owns aliases;
  `cli.dispatch` owns only the context namespace
  (`dummyindex/__main__.py:259-315`).
- **Command identity:** `ContextSubcommand` is imported by dispatcher and help.
  Handler registration and help blocks must remain complete for the same enum
  (`dummyindex/cli/__init__.py:19-20`,
  `dummyindex/cli/help.py:14-17`).
- **Init downstream:** build runner owns deterministic output; config owns
  schema/migration/intent reconciliation; `default_plugins` owns trust registry,
  settings declaration, materialisation, and pure renderers; hook/output modules
  own host integrations (`dummyindex/cli/init.py:29-44`,
  `dummyindex/cli/init.py:180-229`).
- **Wire downstream:** config owns the persisted ledger; the shared plugin
  classifier defines satisfied/acted/needs-user; declaration/materialisation
  operate on the one approved entry (`dummyindex/cli/wire.py:88-115`,
  `dummyindex/cli/wire.py:221-244`).
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
(`dummyindex/cli/__init__.py:88-154`, `dummyindex/cli/help.py:17-42`).

`init` carries one local default-plugin state tuple: `(wired,
default_plugins_enabled)`. The tuple comes from reread config or
`default_wired()` only when config is absent, then the same `wired` selection
feeds both domain passes (`dummyindex/cli/init.py:51-78`). `wire` carries
classified `(WiredEntry, WiredClass)` pairs and transient `wired_now`, `skipped`,
and `remaining` output buckets; it never rewrites the config ledger
(`dummyindex/cli/wire.py:88-173`).

Exit semantics are command-specific within a shared convention: 0 for success or
best-effort completion, 2 for usage/config validation at the boundary, and other
runtime codes where a handler explicitly defines them. The dispatcher forwards
handler codes unchanged (`dummyindex/cli/__init__.py:136-154`).

## Key decisions

- **Help wins before all handlers.** A literal help flag used as a value is an
  accepted sacrificed edge case; preventing accidental mutating probes is the
  stronger invariant (`dummyindex/cli/__init__.py:62-85`,
  `dummyindex/cli/__init__.py:147-153`).
- **Enum construction is command validation.** One alphabet drives routing and
  help identity; no duplicate string validator can drift
  (`dummyindex/cli/__init__.py:136-146`,
  `dummyindex/context/enums.py:41-91`).
- **The plugin opt-out gates plugin work, not indexing.** Init still builds and
  writes selected host guidance before the default step; the canonical help text
  correctly promises only to skip default Claude plugins
  (`dummyindex/cli/help.py:21-42`, `dummyindex/cli/init.py:180-229`).
- **Disclosure precedes mutation.** Reviewed third-party provenance appears before
  config healing, settings writes, or runner probes
  (`dummyindex/cli/init.py:46-60`).
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
  (`dummyindex/cli/init.py:180-231`).
- **Canonical help leads with the canonical flag.** The legacy
  `--no-superpowers` spelling remains visible only as a compatibility alias
  (`dummyindex/cli/help.py:21-36`, `dummyindex/__main__.py:141-173`).

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
