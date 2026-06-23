# 02 — Architect notes (stage 2, cli-dispatch)

## What I changed

- Added a **Bounded context** section up front naming the layer as a *one-directional sink* (`cli -> domains`, never reverse) and stating its upstream (`__main__`/`ingest`->`init` alias) and downstream (every `context/domains/...`) explicitly.
- Lifted the four implicit patterns into a named **Patterns named** section (was buried in the dev's prose "Architecture in three sentences").
- Replaced the prose dependency description with a **Dependencies surfaced** table including a cycle check and the `domains -> cli: none` non-edge.
- Reframed **Key decisions** as **Decisions (decided X because Y)** — every bullet now states the rationale, not just the choice.
- Cut the "Architecture in three sentences" filler block (its content was redistributed into Bounded context + Patterns).
- **Corrected a line-range error:** the dev cited `usage_for` at `help.py:434-444`. Source shows `usage_for` is at `:447-467`; `:434-444` is `_line_starts_subcommand` (the word-boundary helper). Fixed both citations.
- Left `spec.md` untouched.

## Patterns named (with their home)

- **Command-enum -> handler-table dispatch** — `ContextSubcommand` (`enums.py:40-87`) + `_HANDLERS` (`__init__.py:84-126`); `ValueError` from the enum constructor *is* the unknown-subcommand branch (`__init__.py:134-139`).
- **Central help interceptor** — `_wants_help` + guard at `__init__.py:144-146`, runs before `_HANDLERS[sub](rest)`.
- **Wire-only handler / lazy-domain-import** — cli submodules eager at `__init__.py` top; domain import deferred inside `run()` (verified `query.py:9-15`).
- **Single source of truth for value-flags** — `_FLAGS_TAKING_VALUE` (`common.py:64-75`), read by both `_wants_help` and `parse_path_and_root`.

## Dependencies surfaced

- Direction made explicit: `cli -> domains` only; the `domains -> cli` non-edge is listed as such. Cycle check stated (none, by lazy-import construction).
- Intra-layer edges surfaced: `__init__ -> common`/`help` (eager); `reconcile_gate -> memory` (shared hook-stdin helpers, reused not duplicated).
- Upstream alias edge surfaced: `ingest` is resolved in `__main__`, not an enum member (`enums.py:43-44`).

## Decisions promoted

- Help-bias -> "because bare-probe verbs can mutate (bare-equip-mutates hazard)".
- Closed enum -> "because validation/dispatch/doc-sync must key off one source"; ValueError-as-validator named as deliberate.
- Lazy domain import -> "because the sink must stay acyclic with a cheap `import cli`".
- `usage_for` word-bounding -> "because help must not drift and prefix collisions must be excluded by construction".
- Hook-fed handlers return-0 -> "because a failing Stop/SessionStart hook breaks the turn".

## Verification (code wins)

- Enum: **41 members** confirmed by direct count (`INIT`...`STATUSLINE`, `enums.py:47-87`). Did not reintroduce the stale "39 members" claim.
- `council.run` wired at `__init__.py:103` (COUNCIL_LOG); `dev_pick.run` at `:111`. Both **live** — did not reintroduce the "council removed" claim.
- `--status` present in `_FLAGS_TAKING_VALUE` (`common.py:68`), confirming the global-set ambiguity the open question describes.
