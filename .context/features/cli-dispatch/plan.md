# CLI command dispatch — plan

confidence: INFERRED

## Bounded context

CLI dispatch owns token-to-command resolution, mutation-free help interception,
command-specific argument parsing, human-readable output, and process exit codes.
It does not own indexing, config persistence, plugin policy, settings mutation,
or subprocess execution. Handlers coordinate those downstream domains and map their
results to the process boundary (`dummyindex/cli/__init__.py:64-166`,
`dummyindex/cli/init.py:87-231`).

Default-plugin responsibility is split across two CLI surfaces. `context init` is
headless post-build orchestration for reviewed defaults. `context wire` is interactive
escalation for declared entries that stay unsatisfied. Both reuse domain
classifiers, declaration, and materialisation. The CLI alone owns gates, prompts,
ordering, and stdout/stderr policy (`dummyindex/cli/init.py:17-84`,
`dummyindex/cli/wire.py:46-244`).

## Where it lives

- `dummyindex/__main__.py` owns top-level verbs and aliases. `ingest` rewrites to
  `context init`. `status` rewrites to `context status`. Neither alias enlarges the
  context dispatch alphabet (`dummyindex/__main__.py:333-343`).
- `dummyindex/cli/__init__.py` owns context dispatch: help interception, enum
  validation, and the complete handler table (`dummyindex/cli/__init__.py:64-166`).
- `dummyindex/context/enums.py` owns `ContextSubcommand`, the closed command alphabet
  (`dummyindex/context/enums.py:108-164`). That includes `MAINTAIN`, `FLEET`,
  `DRIFT_ACK`, and `EVOLVE`. It also holds the scan wire-format enums `ScanEvidence`
  and `ScanViolationSeverity` that `scan-check` consumes
  (`dummyindex/context/enums.py:74-105`).
- `dummyindex/cli/common.py` owns cross-handler parsing primitives and the shared
  value-taking flag set (`dummyindex/cli/common.py:50-172`).
- `dummyindex/cli/help.py` owns the canonical context usage template and derives
  exact subcommand slices from it (`dummyindex/cli/help.py:1-42`,
  `dummyindex/cli/help.py:789-797`). The `graph` help block is in that template
  (`dummyindex/cli/help.py:267-293`). So are the `maintain`, `fleet`, and `evolve`
  blocks (`dummyindex/cli/help.py:559-692`).
- `dummyindex/cli/graph.py` owns the wire-only symbol-graph query surface: seven-verb
  parsing, per-verb arity and flag scoping, and exit mapping over
  `context.domains.graph_query`. It registers as `ContextSubcommand.GRAPH` in
  `_HANDLERS` (`dummyindex/cli/graph.py:23-184`, `dummyindex/cli/__init__.py:119`).
  The maintenance family follows the same one-row pattern. `maintain`, `fleet`,
  `drift_ack`, and `evolve` register through `_HANDLERS` rows only
  (`dummyindex/cli/__init__.py:135-144`).
- `dummyindex/cli/init.py` owns build and init parsing. It also owns the ordered
  reviewed-default post-build boundary. `dummyindex/cli/wire.py` owns nonblocking
  interactive resolution of `config.wired` (`dummyindex/cli/init.py:17-231`,
  `dummyindex/cli/wire.py:46-244`).
- `dummyindex/cli/check.py` owns `--budget`, `--style`, `--refs`, and
  `--update-ratchet`. Budget and style share `_run_ratchet_check`
  (`dummyindex/cli/check.py:196-260`).
- `dummyindex/cli/memory.py` prints the SessionStart probation block after the memory
  block (`dummyindex/cli/memory.py:59-70`, `:169`). Semantics live in `probation`.

## Architecture in three sentences

Top-level aliases feed a context dispatcher. It validates one enum-backed command,
intercepts help, and invokes one registered function. Each handler parses its own syntax.
`init` builds first, then runs reviewed defaults in fixed order: gate, disclose,
validate, reconcile, declare, materialise, render. `wire` keeps prompts out of headless
init, classifying the ledger read-only and passing one approved entry through the same seams.

## Dispatch flow

1. `__main__.main` resolves top-level commands. `context` forwards argv unchanged.
   `ingest` prepends `init`. `status` prepends `status`
   (`dummyindex/__main__.py:333-343`).
2. `dispatch` prints full context help for empty or bare-help input. It constructs
   `ContextSubcommand` to reject unknown verbs. Failure returns exit 2 with canonical
   usage (`dummyindex/cli/__init__.py:148-158`).
3. `_wants_help` scans the remaining tokens with the same value-taking flag set used by
   path parsing. Any help token short-circuits to `usage_for` before mandatory flags,
   prompts, or side effects (`dummyindex/cli/__init__.py:64-91`,
   `dummyindex/cli/__init__.py:163-165`).
4. `_HANDLERS` maps every enum member to one `run(list[str]) -> int` function. The table
   is the only execution edge after validation (`dummyindex/cli/__init__.py:94-145`,
   `dummyindex/cli/__init__.py:166`).
5. `usage_for` slices one canonical template by word-bounded top-level command tokens.
   So `reconcile` cannot capture `reconcile-stamp` or `reconcile-gate`
   (`dummyindex/cli/help.py:789-797`).

## Default-plugin orchestration flow

1. `init.run` removes one-run boolean gates before shared path parsing. The canonical
   `--no-default-plugins` and legacy `--no-superpowers` spellings collapse into one
   non-persisted boolean (`dummyindex/cli/init.py:90-107`).
2. Init validates platform and depth. It rejects a destructive rebuild of an enriched
   index unless `--force` is set. Then it completes the deterministic build and selected
   host guidance (`dummyindex/cli/init.py:109-208`).
3. Claude hooks install as a best-effort integration. Codex-only returns immediately
   afterward. It never imports or executes Claude default-plugin orchestration
   (`dummyindex/cli/init.py:210-229`).
4. `_wire_default_plugins_step` returns on the one-run opt-out. That happens before any
   default-specific import, disclosure, config read or migration, settings action, or
   runner probe (`dummyindex/cli/init.py:17-27`).
5. Active runs print the third-party trust disclosure. They strictly validate config and
   migrate stale schema. They fold equipment plugins into `wired`, reconcile missing
   reviewed defaults, and reread config. Malformed config prints one warning and stops
   defaults (`dummyindex/cli/init.py:29-68`).
6. The exact selected `wired` tuple and resolved applicability feed both
   `wire_default_plugins` and `install_default_plugins`. Declaration completes before
   materialisation. This prevents an unrelated all-default second pass
   (`dummyindex/cli/init.py:70-78`).
7. Pure domain renderers split informational and warning lines. The CLI sends them to
   stdout and stderr. Target failures do not become init failures after the index build
   (`dummyindex/cli/init.py:79-84`).

## Source-evidenced patterns

- **Closed-alphabet handler table.** `ContextSubcommand` is both validator and key type
  for `_HANDLERS`. Routing cannot reach an unregistered string command
  (`dummyindex/context/enums.py:108-164`, `dummyindex/cli/__init__.py:94-166`). A new
  command costs one enum member, one import, one table row, and one help block. The
  `maintain`, `fleet`, `drift-ack`, and `evolve` additions changed no dispatcher logic.
- **Help-before-handler guard.** Central interception makes every context help path
  read-only, whatever the handler does (`dummyindex/cli/__init__.py:64-91`,
  `dummyindex/cli/__init__.py:163-165`).
- **Command-scoped application boundary.** `init.run` owns parse, build, and integration
  order. Domains own the effects (`dummyindex/cli/init.py:87-231`).
- **Ordered post-build saga.** Default-plugin steps can recover independently after the
  build. Their order is strict, and selected state flows forward through every stage
  (`dummyindex/cli/init.py:17-84`).
- **Fail-closed validation before tolerant healing.** Strict `read_config` runs before
  migration and reconciliation helpers. Corrupt config cannot seed reviewed defaults
  (`dummyindex/cli/init.py:51-68`).
- **Selected-state continuity.** One `wired` tuple feeds declaration and materialisation.
  Interactive wire narrows that invariant to a one-entry tuple
  (`dummyindex/cli/init.py:70-78`, `dummyindex/cli/wire.py:221-244`).
- **Dual-stream result rendering.** Domain functions render `(info, warn)`. The CLI
  assigns stdout or stderr. Domain code does not print (`dummyindex/cli/init.py:79-84`).
- **Prompt adapter with non-TTY guard.** `_PROMPT` is injectable. `--yes` bypasses it.
  Non-TTY input reports planned prompts without blocking
  (`dummyindex/cli/wire.py:41-43`, `dummyindex/cli/wire.py:125-173`).
- **Doc-as-data slicing.** One help template serves full and per-command usage.
  Word-bounded extraction supports verb families without prefix collisions
  (`dummyindex/cli/help.py:762-797`).
- **Shared parse alphabet.** `_FLAGS_TAKING_VALUE` drives both help scanning and
  path/root forwarding. The two token walkers cannot disagree about which token is a
  value (`dummyindex/cli/common.py:66-91`, `dummyindex/cli/common.py:121-172`).

## Dependencies and ownership

- **Upstream:** `dummyindex.__main__.main` is the process entry and owns aliases.
  `cli.dispatch` owns only the context namespace (`dummyindex/__main__.py:281-343`).
- **Command identity:** `ContextSubcommand` is imported by dispatcher and help. Handler
  registration and help blocks must stay complete for the same enum
  (`dummyindex/cli/__init__.py:19-44`, `dummyindex/cli/help.py:14-17`).
- **Init downstream:** the build runner owns deterministic output. Config owns schema,
  migration, and intent reconciliation. `default_plugins` owns the trust registry,
  settings declaration, materialisation, and pure renderers. Hook and output modules own
  host integrations (`dummyindex/cli/init.py:29-44`, `dummyindex/cli/init.py:180-229`).
- **Wire downstream:** config owns the persisted ledger. The shared plugin classifier
  defines satisfied, acted, and needs-user. Declaration and materialisation operate on
  the one approved entry (`dummyindex/cli/wire.py:88-115`,
  `dummyindex/cli/wire.py:221-244`).
- **Persistent state:** the CLI owns no stored model. It reads `.context/config.json`
  and writes only through domain services.
- **Output contract:** handlers return integers and print only boundary text. Target
  failures and declines are output states, not dispatcher exceptions
  (`dummyindex/cli/init.py:63-84`, `dummyindex/cli/wire.py:137-173`).

## Data model

The dispatcher carries `list[str]`, `ContextSubcommand`, handler callables, and integer
exit codes. It persists nothing. `_HANDLERS` is the runtime routing table. `USAGE` is
the canonical human contract (`dummyindex/cli/__init__.py:94-166`,
`dummyindex/cli/help.py:17-42`).

`init` carries one local default-plugin state tuple: `(wired, default_plugins_enabled)`.
The tuple comes from reread config, or from `default_wired()` only when config is absent.
The same `wired` selection feeds both domain passes (`dummyindex/cli/init.py:51-78`).
`wire` carries classified `(WiredEntry, WiredClass)` pairs. It also carries transient
`wired_now`, `skipped`, and `remaining` buckets. It never rewrites the config ledger
(`dummyindex/cli/wire.py:88-173`).

Exit semantics are command-specific within a shared convention. Exit 0 means success or
best-effort completion. Exit 2 means usage or config validation failed at the boundary.
Handlers define other codes. The dispatcher forwards codes unchanged (`dummyindex/cli/__init__.py:136-154`).

## Key decisions

- **Help wins before all handlers.** A literal help flag used as a value is an accepted
  edge case. Preventing accidental mutating probes is the stronger invariant
  (`dummyindex/cli/__init__.py:64-91`, `dummyindex/cli/__init__.py:163-165`).
- **Enum construction is command validation.** One alphabet drives routing and help
  identity. No duplicate string validator can drift (`dummyindex/cli/__init__.py:148-158`,
  `dummyindex/context/enums.py:108-164`).
- **The plugin opt-out gates plugin work, not indexing.** Init still builds and writes
  selected host guidance before the default step. The canonical help text promises only
  to skip default Claude plugins (`dummyindex/cli/help.py:21-42`,
  `dummyindex/cli/init.py:180-229`).
- **Disclosure precedes mutation.** Third-party provenance prints before config
  healing, settings writes, or runner probes (`dummyindex/cli/init.py:46-60`).
- **Corruption is not absence.** Strict config validation stops defaults. It does not
  fall back to `default_wired()` on malformed state (`dummyindex/cli/init.py:51-70`).
- **Reconciliation is visible in the same run.** Config is reread after migration,
  equipment folding, and reviewed-default backfill. That exact ledger drives both
  downstream stages (`dummyindex/cli/init.py:51-78`).
- **Headless init never prompts.** Classification and effects stay non-interactive.
  `context wire` owns explicit confirmation and non-TTY behavior
  (`dummyindex/cli/wire.py:1-26`, `dummyindex/cli/wire.py:125-173`).
- **Interactive approval is target-scoped.** The one selected entry goes to both
  declaration and materialisation. Approving a custom target cannot install unrelated
  reviewed defaults (`dummyindex/cli/wire.py:221-244`).
- **Per-target failure is reported, not escalated.** The index is already complete when
  defaults run. Init returns 0 after warning output (`dummyindex/cli/init.py:180-231`).
- **Canonical help leads with the canonical flag.** The legacy `--no-superpowers`
  spelling stays visible only as a compatibility alias
  (`dummyindex/cli/help.py:21-36`, `dummyindex/__main__.py:141-173`).

## Open questions

- Should init return or emit a structured aggregate that separates build, guidance,
  hooks, declaration, and materialisation outcomes? Automation must parse stdout and
  stderr to detect partial readiness.
- Should `context wire` recognize a reviewed built-in and render its pinned trust
  disclosure? It currently labels every absent valid plugin "untrusted"
  (`dummyindex/cli/wire.py:193-200`).
- Should an interactive declaration or materialisation failure return nonzero, or offer
  JSON output? The command reports needs-user and exits 0 (`dummyindex/cli/wire.py:156-173`).
- Should `usage_for` and handler completeness come from one declarative command registry?
  Enum, handler table, and help template remain three authored
  structures.
- Should `_FLAGS_TAKING_VALUE` become command-aware? Its global view favors help over
  ambiguity. A token such as `--status` can be a value flag for one command and a boolean
  mode for another.
