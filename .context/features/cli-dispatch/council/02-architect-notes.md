# Architect notes — cli-dispatch (stage 2)

## What I changed

- Split the bounded context into central dispatch and command-specific application
  boundaries. Dispatcher owns validation/help/routing; `init` and `wire` own
  orchestration and output, never plugin/config mechanics.
- Added the complete alias → enum → help gate → handler flow with current source
  anchors.
- Reframed init defaults as an ordered post-build saga: opt-out, disclosure,
  strict validation, migration, equipment/default reconciliation, config reread,
  declaration, materialisation, dual-stream rendering.
- Made selected-state continuity explicit: one `wired` tuple crosses both init
  domain passes, and one approved entry crosses both interactive wire passes.
- Clarified opt-out scope: it suppresses default-plugin work only; indexing and
  selected host guidance still run.
- Consolidated output/exit semantics and cut repeated handler descriptions.
- Corrected stale help/symbol ranges against the current map and source.

## Patterns named

- **Closed-alphabet handler table** — enum-backed validation and O(1) routing
  (`dummyindex/context/enums.py:41-91`,
  `dummyindex/cli/__init__.py:88-154`).
- **Help-before-handler guard** — centralized mutation-free interception
  (`dummyindex/cli/__init__.py:62-85`,
  `dummyindex/cli/__init__.py:147-153`).
- **Command-scoped application boundary** — handlers coordinate domains and own
  boundary output (`dummyindex/cli/init.py:87-231`).
- **Ordered post-build saga** — recoverable default stages with strict ordering
  (`dummyindex/cli/init.py:17-84`).
- **Fail-closed validation before tolerant healing** — strict config read precedes
  migrations/reconciliation (`dummyindex/cli/init.py:51-68`).
- **Selected-state continuity** — same tuple/entry feeds declaration and
  materialisation (`dummyindex/cli/init.py:70-78`,
  `dummyindex/cli/wire.py:221-244`).
- **Dual-stream result rendering** — info to stdout, warnings to stderr
  (`dummyindex/cli/init.py:79-84`).
- **Prompt adapter with non-TTY guard** — injectable prompt, `--yes`, and
  never-blocking pipes (`dummyindex/cli/wire.py:41-43`,
  `dummyindex/cli/wire.py:125-173`).
- **Doc-as-data slicing** — per-command help derives from one canonical template
  (`dummyindex/cli/help.py:504-557`).

## Dependencies surfaced

- `__main__.main` owns top-level aliases; `cli.dispatch` owns the context command
  namespace (`dummyindex/__main__.py:259-315`).
- `ContextSubcommand` is shared by dispatcher and help. `_HANDLERS` and `USAGE`
  must remain complete against that same alphabet.
- `common._FLAGS_TAKING_VALUE` is shared by help scanning and path/root parsing
  (`dummyindex/cli/common.py:66-91`,
  `dummyindex/cli/common.py:121-172`).
- Init depends on build, config, guidance, hooks, and default-plugin domains but
  owns only their order and result rendering (`dummyindex/cli/init.py:17-84`,
  `dummyindex/cli/init.py:180-229`).
- Wire depends on config for the ledger and on default-plugin classification,
  declaration, and materialisation for one approved entry
  (`dummyindex/cli/wire.py:88-115`,
  `dummyindex/cli/wire.py:221-244`).
- CLI stores no persistent model and writes state only through downstream domain
  services.

## Decisions promoted

- Help always short-circuits before mutation.
- Enum construction is the command validator.
- The one-run plugin opt-out does not suppress indexing or guidance.
- Trust disclosure precedes default-specific mutation.
- Malformed config is not treated as absent config.
- Config is reread after healing, and one exact selection flows through both
  default-plugin stages.
- Codex-only init never enters Claude plugin orchestration.
- Headless init never prompts; interactive escalation is isolated in `wire`.
- Approval is target-scoped and cannot trigger an unrelated all-default install.
- Per-target default failures remain warnings after a successful build.
- Canonical help leads with `--no-default-plugins`; `--no-superpowers` remains a
  compatibility alias.
