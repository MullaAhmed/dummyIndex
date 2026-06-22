# Proposal store — plan

confidence: INFERRED

## Bounded context

This feature owns exactly one thing: **scaffolding and consistency-stamping the
on-disk `.context/proposals/<slug>/` artifact**. It scans, models, and persists;
it does not plan, does not dispatch, does not advance lifecycle. The four files it
writes (`proposal.json` + `spec.md` / `plan.md` / `checklist.md`) are *seeds* — the
`/dummyindex-plan` skill and the build loop enrich them later. The boundary is the
filesystem write plus a deterministic, no-LLM consistency scan; everything past the
seed (prose, `reused_symbols`, `## Wave N` grouping, status transitions) is out of
context and owned downstream.

## Where it lives

- Domain: `dummyindex/context/domains/proposals/` — `__init__.py` (public surface,
  re-exports at `__init__.py:21-49`), `enums.py` (`ProposalStatus`), `constants.py`
  (`SCHEMA_VERSION = 1`), `errors.py` (typed exception tree, `errors.py:5-26`),
  `models.py` (`Proposal`, `ConsistencyHits`), `scan.py` (`scan_consistency`),
  `store.py` (all filesystem I/O + templates + consistency injection).
- CLI: `dummyindex/cli/propose.py` — wire-only parse + orchestration. Routed from
  `cli/__init__.py:116` (`ContextSubcommand.PROPOSE → propose.run`).
- Tests: `tests/context/domains/test_propose.py`.
- On-disk artifacts: `.context/proposals/<slug>/` (`PROPOSALS_REL = "proposals"`,
  `store.py:23`).

## Architecture in three sentences

`cli/propose.py` parses its own value flags (`--slug` / `--title` / `--root` /
`--force`, `_VALUE_FLAGS` `propose.py:23`) because they fall outside the shared
flag alphabet, resolves the `.context/` root via `resolve_context_root`
(`propose.py:19`), then orchestrates the domain pipeline `ensure_proposal →
scan_consistency → apply_consistency` and prints the result. The domain is strictly
layered: `models.py` holds frozen dataclasses, `store.py` owns every filesystem write
(atomic tmp+replace via `write_text_atomic`, `store.py:18`), and `scan.py` reuses the
existing `query` retrieval domain (`scan.py:11`) so the consistency scan is
deterministic with no LLM. All mutation is copy-on-write — `apply_consistency` builds
a new `Proposal` with `dataclasses.replace` rather than touching the loaded one
(`store.py:111-139`).

## Patterns named at path:range

- **Strict-layering / CLI-boundary I/O** — `store.py` never `print`s (module docstring
  `store.py:11`); `cli/propose.py` owns stdout/stderr and all exit codes. The domain
  raises typed errors, the CLI maps them to exit codes.
- **Copy-on-write update** — `apply_consistency` (`store.py:111-139`) returns a fresh
  frozen `Proposal` via `dataclasses.replace`; input proposal is never mutated. Mirrors
  the repo-wide immutability convention (`conventions/coding-practices.md`).
- **Single-chokepoint validation (security boundary)** — `validate_slug`
  (`store.py:36-51`) is the one guard against `../` traversal; `proposals_root`
  (`store.py:54-56`) and `proposal_dir` (`store.py:59-61`) both route through it before
  any path is touched. Validate-at-boundary, fail-fast.
- **Idempotent sentinel-delimited block** — `_inject_consistency` (`store.py:206-215`)
  rewrites the `<!-- dummyindex:consistency:begin/end -->` block (`store.py:27-28`)
  in place, so a re-scan replaces rather than appends. The same shape the build loop
  relies on for repeatable runs.
- **Tolerant deserialization** — `Proposal.from_dict` (`models.py:39-53`) defaults
  missing keys and coerces `status` through `ProposalStatus`, so an older or
  hand-edited `proposal.json` still loads. `to_dict` at `models.py:29-38`.
- **Graceful degradation** — `_related_features` (`scan.py:35-43`) swallows
  `FileNotFoundError` from `query` (no `features/INDEX.json` yet) and returns empty;
  the conventions glob still runs. A proposal is scaffoldable before full indexing.

## Data model

`proposal.json` schema (`Proposal.to_dict`, `models.py:29-38`):

- `schema_version: int` — from `constants.SCHEMA_VERSION` (= 1).
- `slug: str`, `title: str`.
- `status: str` — one of `ProposalStatus` (`planned` / `in_progress` / `done`,
  `enums.py:10-12`); str-Enum, so JSON serializes the value. Defaults `planned`
  (`models.py:23`).
- `related_features: list[str]` — feature ids ranked by `query` token overlap with
  the title (top 5).
- `conventions: list[str]` — repo-relative POSIX `conventions/*.md` paths that exist.
- `reused_symbols: list[str]` — forward-schema field, empty at scaffold, filled by
  `/dummyindex-plan` (`models.py:26-27`). This feature seeds it `[]` and never writes it.

`ConsistencyHits` (`models.py:56-67`): `related_features` + `conventions` tuples — the
scan's output, folded into the `Proposal` by `apply_consistency`.

Checklist waves: the scaffolded `checklist.md` is a **flat** `- [ ]` list
(`_checklist_template`, `store.py:170-176`) — no `## Wave N` headings at scaffold time.
Wave grouping is a downstream concern: the `/dummyindex-plan` skill writes the headings,
and `build_loop/waves.py` parses them into opaque 0-based group ids (`waves.py:14`); a
flat checklist degrades to one item per wave. The three prose template bodies
(`_spec_template` `store.py:145-157`, `_plan_template` `store.py:160-167`,
`_checklist_template`) are placeholders the human/skill fleshes out; `spec.md` ships with
`## Intent` / `## Contracts` / `## Acceptance` plus an empty `## Consistency` sentinel block.

## Dependencies — upstream, downstream, cycles

**Upstream (this feature depends on):**
- `query` retrieval domain — `scan.py:11`, the sole engine behind related-feature
  ranking. If `query`'s index contract changes, the scan changes.
- `atomic_io.write_text_atomic` — `store.py:18`, every write goes through it.
- `cli/common.resolve_context_root` — `propose.py:19`, root resolution.
- `constants.SCHEMA_VERSION`, `enums.ProposalStatus`, `errors.*` — internal to the domain.

**Downstream (consumes this feature's artifacts — feeds the build loop):**
- `cli/build_loop/waves.py` — parses `checklist.md` into wave groups (`waves.py:14`,
  `parse_checklist`); `_grounding_paths` (`waves.py:132-138`) reads the proposal's
  `spec.md` + `plan.md` as the fixed grounding set for dispatch. **The plan/spec prose
  this feature only *seeds* becomes build's ground truth — the seed contract matters.**
- `cli/status.py` — `_proposals` (`status.py:143-153`) lists proposals and reads
  `proposal.json` for the read-only overview.
- `/dummyindex-plan` skill — writes the prose, `reused_symbols`, and `## Wave N` headings.
- `/dummyindex-build` skill — drives `checklist.md` wave-by-wave.

**Cycles:** none. Clean one-directional fan-out: `query`/`atomic_io` → this feature →
build loop. The feature never reads back from its downstream consumers.

## Decisions

- **Deterministic scan, no LLM.** `scan_consistency` reuses `query` (`scan.py:1-6,11`)
  so the consistency hint is reproducible and is the same machinery an agent could walk
  by hand. No model call in the scaffold path.
- **Slug is the security boundary.** All path construction routes through `validate_slug`
  (`store.py:36-51`); traversal is rejected before any directory is created.
- **Idempotent consistency injection.** Sentinel-delimited block (`store.py:27-28,206-215`)
  makes re-scan safe — rewrite in place, never duplicate.
- **Atomic, CLI-only I/O.** Domain writes are tmp+replace and silent; the CLI is the
  single owner of stdout/stderr and exit codes (`propose.py`).
- **Self-parsing CLI.** `propose` parses `--slug` / `--title` itself (`propose.py:8-12,23`)
  because the shared `parse_*` helpers only know the older subcommands' flag alphabet.
- **Seed, don't own.** Templates are placeholders; `reused_symbols` and wave grouping are
  forward-schema seams this feature deliberately leaves empty for `/dummyindex-plan`.

## Open questions

- `proposals_root` is exported as an entry point in `feature.json` but is not in the
  package `__all__` (`__init__.py:21-49`) — intended public surface, or internal-only?
- `read_proposal` raises bare `FileNotFoundError` (`store.py:104-108`) rather than a
  `ProposalError` subclass — intentional asymmetry, or a gap in the typed-exception tree?
- `status` carries `in_progress` / `done` (`enums.py:10-12`) but nothing in this domain
  writes them; the lifecycle-transition owner is the build loop, outside this bounded
  context. Confirm no in-domain writer is expected.
