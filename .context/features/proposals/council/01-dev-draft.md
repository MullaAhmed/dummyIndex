# Proposal store — plan

confidence: INFERRED

## Where it lives

- Domain: `dummyindex/context/domains/proposals/` — `__init__.py` (public surface),
  `enums.py` (`ProposalStatus`), `constants.py` (`SCHEMA_VERSION`), `errors.py`
  (typed exception tree), `models.py` (`Proposal`, `ConsistencyHits`), `scan.py`
  (`scan_consistency`), `store.py` (read/write + templates + consistency injection).
- CLI: `dummyindex/cli/propose.py` — wire-only argument parsing + orchestration.
- Tests: `tests/context/domains/test_propose.py`.
- On-disk artifacts: `.context/proposals/<slug>/` (`PROPOSALS_REL = "proposals"`,
  `store.py:23`).

## Architecture in three sentences

`cli/propose.py` parses its own value flags (`--slug` / `--title` / `--root` /
`--force`) because they fall outside the shared flag alphabet, resolves the `.context/`
root, then orchestrates the domain pipeline `ensure_proposal → scan_consistency →
apply_consistency` and prints the result. The domain is strictly layered: `models.py`
holds frozen dataclasses, `store.py` owns every filesystem write (atomic tmp+replace via
`atomic_io.write_text_atomic`, `store.py:18,86`), and `scan.py` reuses the existing
`query` retrieval domain so the consistency scan is deterministic with no LLM
(`scan.py:11`). All mutation is copy-on-write — `apply_consistency` builds a new
`Proposal` with `dataclasses.replace` rather than mutating the loaded one
(`store.py:124-128`).

## Data model

`proposal.json` schema (`Proposal.to_dict`, `models.py:29-38`):

- `schema_version: int` — sourced from `constants.SCHEMA_VERSION` (= 1).
- `slug: str`, `title: str`.
- `status: str` — one of `ProposalStatus` (`planned` / `in_progress` / `done`,
  `enums.py:10-12`); str-Enum, so JSON serializes the value. Defaults `planned`
  (`models.py:23`).
- `related_features: list[str]` — feature ids ranked by token overlap with the title.
- `conventions: list[str]` — repo-relative POSIX `conventions/*.md` paths that exist.
- `reused_symbols: list[str]` — forward-schema field, empty at scaffold, filled by
  `/dummyindex-plan` (`models.py:26-27`).

`ConsistencyHits` (`models.py:56-67`): `related_features` + `conventions` tuples — the
scan's output, folded into the `Proposal` by `apply_consistency`.

Checklist waves: the scaffolded `checklist.md` is a **flat** `- [ ]` list
(`_checklist_template`, `store.py:170-176`) — no `## Wave N` headings at scaffold time.
Wave grouping is a downstream concern owned by the `/dummyindex-plan` skill and consumed
by `/dummyindex-build`; a flat checklist degrades to one item per wave. The three
template bodies (`_spec_template` `store.py:145-157`, `_plan_template` `store.py:160-167`,
`_checklist_template`) are placeholders the human/skill fleshes out; `spec.md` ships with
`## Intent` / `## Contracts` / `## Acceptance` plus an empty `## Consistency` sentinel
block.

## Key decisions

- **Deterministic scan, no LLM.** `scan_consistency` reuses `query` so it is the same
  machinery an agent could walk by hand (`scan.py:1-6`).
- **Graceful degradation.** Missing features index → `FileNotFoundError` swallowed,
  empty related features, conventions still listed (`scan.py:36-43`).
- **Slug as a security boundary.** `validate_slug` is the single chokepoint guarding the
  `proposals/<slug>/` path against traversal; every path helper routes through it
  (`store.py:59-61`).
- **Idempotent consistency injection.** A sentinel-delimited block
  (`<!-- dummyindex:consistency:begin/end -->`, `store.py:27-28`) lets a re-scan rewrite
  in place instead of appending duplicates (`store.py:206-215`).
- **Atomic writes, CLI-only I/O.** `store.py` never prints; the CLI owns stdout/stderr
  and exit codes (`cli/propose.py`). All writes are tmp+replace (`store.py` module docstring).
- **Self-parsing CLI.** `propose` parses `--slug` / `--title` rather than the shared
  helpers, which only know the older subcommands' flag alphabet (`cli/propose.py:8-12`).

## Open questions

- `proposals_root` is exported as an entry point in `feature.json` but is not in the
  package `__all__`; confirm whether it is intended public surface or internal-only.
- `read_proposal` raises bare `FileNotFoundError` rather than a `ProposalError`
  subclass — intentional, or a gap in the typed-exception tree?
- `status` has values `in_progress` / `done` but nothing in this domain writes them; the
  lifecycle transition owner is presumably the build loop, outside this feature.
