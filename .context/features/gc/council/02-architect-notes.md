# Architect notes — Context-hygiene GC

## What I changed

Authored `plan.md` from scratch (no prior plan existed). `spec.md` untouched, no
source touched.

- **Where it lives** — grounded in `feature.json:files` plus a live grep for
  consumers `feature.json` omits: the SessionStart wiring at
  `dummyindex/context/hooks.py:170-184`, the subcommand registration at
  `dummyindex/context/enums.py:154` + `dummyindex/cli/__init__.py:36,130`, and
  the generated agent-facing docs at
  `dummyindex/context/output/instructions.py:46,100,109-120`. Also corrected the
  spec's `build/git_delta.py` reference to the real path
  `dummyindex/context/build/git_delta.py`.
- **Architecture in three sentences** — grounded in the module docstrings that
  *state* the constraints (`enumerate.py:6-7`, `signals.py:4-7`, `scan.py:16-20`,
  `delete.py:10-32`) cross-checked against the actual import lines, not the prose.
- **Data model** — grounded in `constants.py:34-42` (the two rel-paths),
  `anchor.py:44-65,151-183` (the readers/writers), `.gitignore:19` +
  `.context/.gitignore:3` (proving the memo is gitignored on disk), and the three
  git invocations in `enumerate.py:181,199` / `build/git_delta.py:158-183`.
- **Key decisions** — every one promoted from a code site or an inline comment
  that explained *what* but never recorded *why it beat the alternative*. No
  rationale invented: where the code gives a reason (e.g. `delete.py:16-18`,
  `signals.py:11-18`) I sharpened it into decided/because form; where it gives
  none I filed an open question instead.
- **Open questions** — six, five of which are findings from reading the code
  against the spec rather than gaps in my reading.

## Patterns named

- **Wire-only CLI / domain split** at `dummyindex/cli/gc.py:38-54` (dispatch) with
  lazy domain imports inside each handler (`cli/gc.py:59,87-94,156,181-182`) — the
  layering rule from `conventions/folder-organization.md` is enforced by import
  *placement*, not by a linter.
- **Two-stage pure pipeline over a frozen record** at `enumerate.py:36-60` →
  `signals.py:38-80`, joined only at `scan.py:51-54` via `dataclasses.replace` —
  no mutation, and the two stages are mutually non-importing by design.
- **Guard ladder / chain of responsibility** at `delete.py:77-137` — five ordered
  guards, each strictly tighter than the last, fronting the codebase's only
  `shutil.rmtree` (`delete.py:136`).
- **Two-file state split (committed fact vs local memo)** at `constants.py:34-42`
  with readers at `anchor.py:36-54` and `anchor.py:151-160` — the same shape as
  `memory/nudge.py`, deliberately copied.
- **Deterministic-plumbing / LLM-judgment port** — `enums.py:8-20` defines
  `Disposition` as an exported vocabulary that no Python constructs;
  `skills/gc/SKILL.md:12-18` is the only consumer. The port is the CLI; the
  adapter is the skill.
- **Corrupt-tolerant reader** at `anchor.py:44-54`, `anchor.py:151-160`,
  `delete.py:189-201`, `enumerate.py:160-170`, `signals.py:83-98` — five separate
  JSON readers, all degrading to `None`/`{}`/`""` and never raising. Consistent
  enough to be a house idiom, duplicated enough to be a candidate for one helper.

## Dependencies surfaced

- **Upstream (gc imports):** `proposals/store.py` (`proposals_root`,
  `proposal_dir`, `validate_slug`, `PROPOSALS_REL`, **and the privates**
  `_plan_template` / `_checklist_template`), `audit/workspace.py` (`audits_root`,
  `validate_slug`, `report_written`, `AUDITS_REL`), `buildloop/checklist.py`
  (`parse_checklist`, `counts`), `buildloop/errors.py` (`BuildLoopError`),
  `context/build/git_delta.py` (`commits_since`, `head_commit`),
  `context/domains/atomic_io.py` (`write_text_atomic`), and — from the CLI layer
  only — `memory/transcript.py:resolve_session_id` (`cli/gc.py:182`).
- **Downstream (imports gc):** `dummyindex/cli/gc.py` (all four verbs);
  `dummyindex/cli/__init__.py:36,130` via `ContextSubcommand.GC`
  (`context/enums.py:154`); `dummyindex/context/hooks.py:176-183`, which shells
  `dummyindex context gc signal` as a SessionStart hook rather than importing;
  `dummyindex/skills/gc/SKILL.md`, which consumes the CLI as its contract.
- **Cycles:** none. `context/domains/gc/` never imports `cli`, and no upstream
  domain imports `gc` — the dependency arrows are strictly one-way. `enumerate`
  and `signals` are deliberately acyclic siblings (each docstring names the other
  as forbidden), joined only downward by `scan`.
- **Boundary violation worth naming:** `signals.py:29-33` is the only
  cross-domain import of another domain's private symbols in `dummyindex/`
  (verified by grep — no other importer of `_plan_template` /
  `_checklist_template` outside `proposals/`). It is a real coupling, not a style
  nit: any change to the scaffold templates silently changes GC's `orphan-empty`
  verdict.

## Decisions promoted

- decided **the deterministic layer emits tags, never verdicts**, because that is
  what makes `gc status` safe to run unattended and forces every deletion through
  the skill's confirm gate (was implicit at `signals.py:38-80` returning
  `tuple[str, ...]` while `enums.py:8-20` defines a `Disposition` nothing builds).
- decided **`scan` recomputes the threshold predicate instead of calling
  `anchor.should_signal`**, because the latter marks the fire-once memo and a
  read-only report must not consume a session's nudge (was implicit at
  `scan.py:16-20,58` vs the side effect at `anchor.py:122`).
- decided **sentinel-reject precedes realpath-containment**, because `_archive` is
  charset-valid *and* resolves inside the root, so containment provably cannot
  catch it — the ordering is the invariant (was a comment at `delete.py:16-18`,
  now stated as a decision and pinned by
  `tests/context/domains/gc/test_delete.py:135-150`).
- decided **off-git means `tracked=True`**, because refusing an off-git workspace
  as "unrecoverable" blocks every deletion while protecting nothing (was implicit
  at `delete.py:224-255` and `enumerate.py:173-189`, including the
  `rev-parse --git-dir` re-probe that disambiguates "untracked" from "no repo").
- decided **the anchor is committed and the memo is gitignored**, because the
  anchor is shared team state and the memo is per-machine session noise (was
  implicit at `constants.py:34-42`).
- decided **`--kind` accepts only `proposal|audit`**, because otherwise a kind
  flag would route around the sentinel guard; archived children remain reachable
  only via `--path`, which the realpath guard contains (was implicit at
  `cli/gc.py:261-273`).
- decided **age comes from commit date, never mtime**, because a fresh clone
  resets mtime and would zero every doc's age (was a comment at
  `enumerate.py:195-197`).
- decided **the CLI pays static typing for layering purity** — `report: object`
  plus twelve `type: ignore[attr-defined]` in `cli/gc.py:212-255` — and that a
  `TYPE_CHECKING`-guarded import would recover both without breaking the runtime
  rule (was unstated; the trade-off had never been written down).

## Conflicts flagged (code wins)

- `spec.md:54-60` says `classify` covers proposals *and* archived candidates.
  The code disagrees: `signals.py:63-64` resolves an ARCHIVED candidate to
  `proposals/<slug>` while `enumerate.py:98` places it at
  `proposals/_archive/<slug>`, so archived candidates probe a non-existent path
  and emit no `orphan-empty` / `checklist-*` tag. Untested —
  `tests/cli/test_gc_cli.py:104-119` uses an archived dir with no `plan.md` /
  `checklist.md`, masking it. Filed as open question 1; not fixed (documentation
  pass, no source edits).
- `spec.md:93` lists `CandidateKind` as a live alphabet, but `ORPHAN_SCAFFOLD`
  (`enums.py:28`) is constructed nowhere; it survives only inside
  `delete.py:55-57`. Filed as open question 2.
- `spec.md:86` cites `build/git_delta.py`; the file is at
  `dummyindex/context/build/git_delta.py`. Corrected in `plan.md`, spec left
  untouched.
- **Doc evidence:** `.context/features/gc/docs.md` lists eleven `medium`-confidence
  prose docs, but every match is on a generic symbol (`__init__`, `run`,
  `classify`, `Candidate`) and every entry carries broken refs. None describes
  this feature; all are pre-GC equip / session-memory / build-loop plans. Nothing
  was quoted from them. All symbol citations in `plan.md` were instead
  spot-checked against `map/symbols.json` (`delete_workspace`, `classify`, `scan`,
  `should_signal`, `enumerate_candidates`, `stamp_gc` — all resolve to the
  expected `domains/gc/*.py` paths).
