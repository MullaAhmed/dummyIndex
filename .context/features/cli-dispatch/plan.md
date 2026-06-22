# CLI command dispatch — plan

confidence: INFERRED

## Where it lives

`dummyindex/cli/` — one wire-only dispatcher module per subcommand
(`.context/conventions/folder-organization.md:22,30-37`). The dispatcher, the
help short-circuit, and the enum→handler table live in `cli/__init__.py`
(`dispatch` at `cli/__init__.py:127-145`, `_wants_help` at `:57-82`, `_HANDLERS`
at `:83-126`). Shared parsing/resolution helpers are in `cli/common.py`; the
hand-maintained help reference and its slicer are in `cli/help.py` (`usage_for`
at `cli/help.py:427-447`). The closed dispatch alphabet (`ContextSubcommand`)
lives in `context/enums.py:40-86`; the per-area equip alphabet lives in
`context/domains/equip/enums.py`. Tests are under `tests/cli/`
(`test_cli_doc_sync.py`, `test_debt_statusline_dispatch.py`,
`test_scope_vs_root.py`; feature.json:161-163). A subcommand that needs private
siblings becomes a package (`cli/equip/`, `cli/build_loop/`) per
`folder-organization.md:52`.

## Bounded context

This feature owns the *wire* between `argv` and the domains — nothing else. Its
boundary is exactly: the closed subcommand alphabet, the help surface, the
exit-code contract, and the shared flag/scope parsing seam. It explicitly does
**not** own any behaviour the verbs perform — every handler reaches across the
boundary by lazy-importing from `context/domains/<x>/`, and the convention grep
confirms the reverse arrow never exists (`context/domains/*` never imports
`cli`; `folder-organization.md:27-28`). So the cluster is one-directional sink:
`cli/` depends on the world, the world does not depend on `cli/`.

## Patterns named

- **Thin adapter (wire-only handler).** Every `cli/<sub>.py` is a port adapter:
  parse `argv` → lazy-import a domain function inside the `run` body → print →
  return an `int`. Canonical instances: `cli/query.py:7-15`, `cli/debt.py:34-68`,
  `cli/features.py:243-297`. No business logic crosses back into `cli/`
  (`folder-organization.md:30-37`).
- **Enum-driven dispatch (closed-alphabet table).** `dispatch` parses the first
  token into a `ContextSubcommand`, applies the help short-circuit, and routes
  through the `_HANDLERS` enum→handler map as its final statement
  (`cli/__init__.py:127-145`, table at `:83-126`). The alphabet is a closed
  `(str, Enum)` of 40 members, `INIT` through `STATUSLINE` (`WIRE = "wire"` is
  the interactive `config.wired` escalation verb, `context/enums.py:85`)
  (`context/enums.py:47-87`); an unknown token is rejected via the `ValueError`
  from `ContextSubcommand(subcmd)` (`cli/__init__.py:131-137`).
- **Shared-helper seam (extracted cross-cutting parse).** Scope/root resolution
  and flag parsing are factored into `cli/common.py` so no handler reimplements
  them: `resolve_context_root` at `cli/common.py:13-45`, `parse_path_and_root`
  at `:103-148`, `pull_repeatable_flag` at `:77-100`, `parse_kv_flags` at
  `:182-203`, and the `usage_error` exit-2 helper at `:47-61`.

## Data model

None. This is a routing layer, not a data layer — it owns no frozen dataclasses
or persisted records. The only state-shaped artefacts are the closed string
enum `ContextSubcommand` (`context/enums.py:40-86`) and two in-module tables:
the `_HANDLERS` map (`cli/__init__.py:83-126`) and the `_FLAGS_TAKING_VALUE`
frozenset (`cli/common.py:64-74`). All real models live in the
`context/domains/<x>/` modules the handlers lazy-import. The coding-practices
note confirms there is no validation surface here — invariants live in
`__post_init__` / `pipeline/validate.py`, never in the CLI consumer
(`.context/conventions/coding-practices.md:93-95`).

## Dependencies

- **Routes to every domain it dispatches.** Each handler depends on its target
  domain (`query.run` → `context.domains.query`; `debt.run` → `harvest_debt`;
  `features.run_section_write` → `write_section`). These are the only outward
  arrows, and by design they are *lazy* — taken inside the `run` body, not at
  module top (see Decisions).
- **The documented narrow sibling-import exception.** The stated rule is
  "`cli.<sub>` cannot import another `cli.<sub>`"
  (`folder-organization.md:77-83`), but four modules reuse exactly one sibling
  entrypoint: `cli/check.py:19` (`from .rebuild import run as run_rebuild`),
  `cli/refresh.py:5` (`from .migrate import migrate_legacy_layout`),
  `cli/reconcile_gate.py:12` (`from .memory import _read_hook_stdin,
  _resolve_transcript`), `cli/statusline.py:28` (`from .plan_update import
  badge_cache_path`). The shared-helper *spirit* holds (each reuses a single
  entrypoint, not a tangle), but the literal invariant does not — treat
  sibling-import as a real, if narrow, exception.
- **Eager imports are kept light.** Only `cli/common.py` helpers, the enums, and
  `cli/help.py` (`USAGE`, `usage_for`) are imported at module top
  (`cli/__init__.py:18,52`); everything domain-heavy is deferred.

## Decisions

- **Lazy import to keep CLI startup cheap.** Domain functions are imported
  *inside* each `run` body, so dispatching one subcommand never pays the import
  cost of the other 38 (`cli/query.py:7-15`, `cli/debt.py:36`,
  `cli/features.py:34`). This is the single decision that makes a 39-verb CLI
  start fast.
- **I/O confined to the boundary.** `print` lives only in `cli/*`; domain
  modules return and raise, and the dispatcher maps typed exceptions to exit
  codes `0/1/2` catching specific-before-base
  (`.context/conventions/coding-practices.md:55-62`). This is what makes the
  layer mechanically wire-only and keeps the domains pure/testable.
- **Help is read-only and runs before any side effect.** The `_wants_help`
  short-circuit fires before mandatory-flag parsing — closing the historical
  "bare `equip` mutates the repo" hazard — and biases to help even when
  `--help` appears in a value position, so `build --status --help` still shows
  help (`cli/__init__.py:57-82,142-144`). `usage_for` slices help out of the one
  `USAGE` block so it can never drift (`cli/help.py:427-447`).
- **Closed alphabet over bare strings.** Subcommand names are
  `ContextSubcommand` members, not string literals in the dispatcher
  (`coding-practices.md:38-39`); a test asserts every enum member has a handler
  (`test_debt_statusline_dispatch::test_every_enum_member_has_a_handler`,
  feature.json:120), so the table can never silently drop a verb.

## Open questions

- Should the four sibling-import sites be lifted into `cli/common.py` (or a
  shared helper module) to restore the literal "no `cli.<sub>` → `cli.<sub>`"
  invariant, or is the narrow reuse-one-entrypoint exception the intended
  steady state?
- `_FLAGS_TAKING_VALUE` is a single global frozenset shared by both parsing and
  `_wants_help`, so it can't know `--status` is council-log's value-flag yet
  build's boolean verb (`cli/__init__.py:63-67`, `cli/common.py:64-74`). Is the
  help-biasing workaround the long-term answer, or should value-flag alphabets
  become per-subcommand?
