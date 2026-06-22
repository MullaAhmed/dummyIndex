# CLI command dispatch — plan

<!-- reconcile 2026-06-22: this is the stage-1 dev draft, kept verbatim. The
"other 38" figure below was the stage-1 snapshot (39-member enum); the alphabet
has since grown to 41 members, so a single dispatch now skips the other 40. The
live counts are carried in spec.md / plan.md / concerns.md. -->

confidence: INFERRED

## Where it lives

`dummyindex/cli/` — one wire-only dispatcher module per subcommand
(`.context/conventions/folder-organization.md:22,30-37`). The dispatcher and
handler table are in `cli/__init__.py` (`dispatch` + `_HANDLERS`). Shared
parsing/resolution helpers are in `cli/common.py`; the hand-maintained help
reference and its slicer are in `cli/help.py`. The closed dispatch alphabet
(`ContextSubcommand`) lives in `context/enums.py`; the per-area equip alphabet
lives in `context/domains/equip/enums.py`. Tests are under `tests/cli/`
(`test_cli_doc_sync.py`, `test_debt_statusline_dispatch.py`,
`test_scope_vs_root.py`; feature.json:161-163). A subcommand that needs private
siblings becomes a package (`cli/equip/`, `cli/build_loop/`) per
`folder-organization.md:52`.

## Architecture in three sentences

The layer is wire-only — every `cli/<sub>.py` parses `argv`, lazy-imports a
domain function inside its `run` body, prints, and returns an `int`
(`cli/query.py:7-15`, `cli/debt.py:34-68`), so no business logic lives in `cli/`.
Cross-cutting argument work (scope/root resolution, repeatable and key/value
flag parsing, the value-flag alphabet, the `usage_error` exit-2 helper) is
factored into the shared `cli/common.py` seam that every subcommand imports
(`cli/common.py:13-203`). Dispatch is enum-driven: `dispatch` parses the first
token into a `ContextSubcommand`, applies the "help wins everywhere" short-circuit,
and routes through the `_HANDLERS` enum→handler map (`cli/__init__.py:83-145`).

## Data model

None. This is a routing layer, not a data layer — it owns no frozen dataclasses
or persisted records. The only state-shaped artefacts are the closed string
enum `ContextSubcommand` (`context/enums.py:40-87`) and the in-module
`_HANDLERS` dict + `_FLAGS_TAKING_VALUE` frozenset
(`cli/__init__.py:83-124`, `cli/common.py:64-74`). All real models live in the
`context/domains/<x>/` modules the handlers lazy-import. The coding-practices
note confirms there is no validation surface here — invariants live in
`__post_init__` / `pipeline/validate.py`, never in the CLI consumer
(`.context/conventions/coding-practices.md:93-95`).

## Key decisions

- **Lazy import to keep CLI startup cheap.** Domain functions are imported
  *inside* each `run` body rather than at module top, so dispatching one
  subcommand never pays the import cost of the other 38
  (`cli/query.py:7-15`, `cli/features.py:34`, `cli/debt.py:36`). Only the light
  `cli/common.py` helpers and the enums are imported eagerly.
- **I/O confined to the boundary.** `print` lives only in `cli/*`; domain
  modules return and raise, and the dispatcher maps typed exceptions to exit
  codes `0/1/2` catching specific-before-base
  (`.context/conventions/coding-practices.md:55-62`). This is what makes the
  layer mechanically wire-only.
- **Help is read-only and runs before any side effect.** The `_wants_help`
  short-circuit fires before mandatory-flag parsing — closing the historical
  "bare `equip` mutates the repo" hazard — and `usage_for` slices help out of
  the one `USAGE` block so it can never drift (`cli/__init__.py:138-144`,
  `cli/help.py:1-9,427-447`).
- **The documented narrow sibling-import exception.** The stated rule is
  "`cli.<sub>` cannot import another `cli.<sub>`", but a few modules reuse one
  sibling entrypoint: `cli/check.py:19` (`from .rebuild import run`),
  `cli/refresh.py:5` (`from .migrate import ...`), `cli/reconcile_gate.py:12`
  (`from .memory import ...`), `cli/statusline.py:28` (`from .plan_update import
  badge_cache_path`). Treat sibling-import as a real, if narrow, exception — the
  shared-helper spirit holds, the literal invariant does not
  (`.context/conventions/folder-organization.md:76-83`).

## Open questions

- Should the four sibling-import sites be lifted into `cli/common.py` (or a
  shared helper module) to restore the literal "no `cli.<sub>` → `cli.<sub>`"
  invariant, or is the narrow reuse-one-entrypoint exception the intended
  steady state?
- `_FLAGS_TAKING_VALUE` is a single global frozenset shared by both parsing and
  `_wants_help`, so it can't know `--status` is council-log's value-flag yet
  build's boolean verb (`cli/__init__.py:64-67`). Is the help-biasing workaround
  the long-term answer, or should value-flag alphabets become per-subcommand?
