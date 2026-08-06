# Context-hygiene GC — plan

confidence: INFERRED

## Where it lives

| Concern | Path |
|---|---|
| CLI wire (verb dispatch, flag alphabet, rendering) | `dummyindex/cli/gc.py:32-345` |
| Subcommand registration | `dummyindex/context/enums.py:154`, `dummyindex/cli/__init__.py:36,130` |
| Public domain surface | `dummyindex/context/domains/gc/__init__.py:25-74` |
| Data (frozen) | `dummyindex/context/domains/gc/models.py:17-59` |
| Closed alphabets / typed errors / tunables | `.../gc/enums.py:8-29`, `.../gc/errors.py:6-33`, `.../gc/constants.py:13-42` |
| Read path — discovery | `.../gc/enumerate.py:36-233` |
| Read path — signal tags | `.../gc/signals.py:38-136` |
| Read path — composer | `.../gc/scan.py:35-67` |
| Write path — commit anchor + fire-once memo | `.../gc/anchor.py:36-183` |
| Write path — the only `rmtree` in the repo | `.../gc/delete.py:60-284` |
| Shared git primitives (reused, not owned) | `dummyindex/context/build/git_delta.py:56-183` |
| SessionStart hook wiring | `dummyindex/context/hooks.py:170-184` |
| The reasoning half (LLM) | `dummyindex/skills/gc/SKILL.md:1-149` |
| Generated agent-facing docs | `dummyindex/context/output/instructions.py:46,100,109-120` |
| Tests | `tests/context/domains/gc/test_{enumerate,signals,anchor,delete}.py`, `tests/cli/test_gc_cli.py` |

Cross-domain reuse (imported, never re-declared): `proposals/store.py`
(`proposals_root`, `proposal_dir`, `validate_slug`, `PROPOSALS_REL`,
`_plan_template`, `_checklist_template`), `audit/workspace.py` (`audits_root`,
`validate_slug`, `report_written`, `AUDITS_REL`), `buildloop/checklist.py`
(`parse_checklist`, `counts`), `context/domains/atomic_io.py`
(`write_text_atomic`),
`memory/transcript.py` (`resolve_session_id`, at `cli/gc.py:182`).

## Architecture in three sentences

`cli/gc.py` is a **wire-only dispatcher** (`run` at `cli/gc.py:38-54`) that
sub-dispatches four verbs — `status|delete|stamp|signal` — into
`context/domains/gc/`, lazy-importing the domain inside each handler so the
`cli → domain` layering (`conventions/folder-organization.md`, "The CLI / domain
split") is never inverted. The domain splits along a **read path** and a **write
path**: the read path is a two-stage pure **pipeline over a frozen `Candidate`**
— `enumerate.py` supplies structure + git facts, `signals.py:classify` supplies
deterministic tags, and neither module imports the other (`enumerate.py:6-7`,
`signals.py:4-7`), with `scan.py:51-54` the sole composer joining them via
`dataclasses.replace`; the write path is `anchor.py` (two-file throttle state)
and `delete.py`. The dominant pattern in `delete.py:77-137` is an ordered
**guard ladder** (chain of responsibility) fronting the codebase's only
`shutil.rmtree` — slug-validate → sentinel-reject → realpath-containment →
liveness → recoverability — and the dominant pattern of the *feature* is a
**deterministic-plumbing / LLM-judgment port**: the CLI is the port, and
`skills/gc/SKILL.md` is the only client that supplies verdicts and the user
confirm.

## Data model

No database, no ORM, no transactions. Two flat JSON state files plus git-as-a-query-engine.

**Persisted state** (both written through `atomic_io.write_text_atomic`,
tmp+rename, so a crash cannot leave a half-file):

| File | Git state | Shape | Written by |
|---|---|---|---|
| `.context/gc/state.json` (`GC_STATE_REL`) | **committed** | `{"anchor": "<sha>"}` | `anchor.py:57-65` |
| `.context/cache/gc-nudge-state.json` (`GC_MEMO_REL`) | **gitignored** (`.gitignore:19`, `.context/.gitignore:3`) | `{"<session_id>": {"signalled_at": iso}}`, pruned to 100 entries | `anchor.py:170-183` |

Both readers are corrupt-tolerant by construction — missing file /
`JSONDecodeError` / non-dict / wrong-typed key all collapse to `None` or `{}`
(`anchor.py:44-54`, `anchor.py:151-160`), mirroring `memory/nudge.py:_load_state`.
A garbage sha is never returned upward.

**Queries** are git subprocesses, not SQL:

- `git ls-files --error-unmatch <path>` → `tracked` (`enumerate.py:173-189`, `delete.py:224-255`).
- `git log -1 --format=%ct -- <path>` → `age_days` (`enumerate.py:192-210`).
- `git rev-list --count <anchor>..HEAD` → `commits_since`, guarded by
  `commit_exists` (`build/git_delta.py:158-183`).

**In-memory model** is three frozen dataclasses (`models.py:17-59`) —
`Candidate`, `SweepReport`, `DeleteResult`. Enrichment is `replace`, never
mutation (`scan.py:51-54`).

**Write atomicity**: `delete_workspace` performs one `shutil.rmtree` of one
directory (`delete.py:136`). There is no cross-file transaction and none is
needed — a re-run against an already-removed target is an idempotent no-op
(`delete.py:110-113`), which is the recovery story for a partial `rmtree`.

## Key decisions

**decided the deterministic layer emits tags and never a verdict** —
`classify` returns `tuple[str, ...]` (`signals.py:38-80`) and `Disposition`
(`enums.py:8-20`) is exported but *never constructed anywhere in Python*. It
exists only as the skill's controlled vocabulary. Rejected: a `verdict` field on
`Candidate`. Load-bearing: it is what makes the CLI safe to run unattended and
forces every deletion through `SKILL.md`'s step-4 confirm gate.

**decided `enumerate` and `signals` may not import each other** (stated at
`enumerate.py:6-7` and `signals.py:4-7`). Trade-off taken: git-derived facts
(`tracked`, `age_days`) travel *as data on the `Candidate`* rather than being
re-probed, so `classify` is a pure workspace probe testable against a hand-built
`Candidate` — at the cost that `classify` can never refresh a stale git fact.

**decided `gc status` recomputes the threshold predicate instead of calling
`anchor.should_signal`** (`scan.py:16-20,58`). Because `anchor.should_signal`
has a side effect — it marks the fire-once memo (`anchor.py:122`) — a read-only
report calling it would silently consume a session's nudge. Cost accepted: the
same predicate is expressed in two places and can drift.

**decided the anchor and the memo are two files in two git states**
(`constants.py:34-42`). The anchor is shared team state that must survive a
clone and be reviewable in a diff; the memo is per-machine, per-session noise
that must never be committed. Rejected: one state file with a `sessions` key —
it would drag session ids into version control.

**decided sentinel-reject is a distinct guard placed *before* realpath
containment** (`delete.py:85-89`, rationale at `delete.py:16-18`). `_archive` is
charset-valid *and* resolves inside the kind-root, so containment provably
cannot catch it. The **ordering** is the load-bearing part, not the individual
predicates; `tests/context/domains/gc/test_delete.py:135-150` pins exactly this.

**decided off-git degrades to `tracked=True`** (`delete.py:224-255`,
`enumerate.py:173-189`). Refusing an off-git workspace as "unrecoverable" would
block every deletion in a non-git checkout while protecting nothing — git never
made a recoverability promise there. The subtlety: `ls-files --error-unmatch`
exits non-zero for *both* "untracked" and "not a repo", so both call sites
re-probe `rev-parse --git-dir` to disambiguate.

**decided `orphan-empty` compares only `plan.md` + `checklist.md`, never
`spec.md`** (`signals.py:11-18,101-116`). `proposals/store.py:apply_consistency`
rewrites `spec.md` immediately after scaffolding, so a byte-compare there is
always false and would make the tag unreachable.

**decided `--kind` accepts only `proposal|audit`** (`cli/gc.py:261-273`).
`ARCHIVED` / `ORPHAN_SCAFFOLD` are *report* kinds, not delete targets; an
`_archive/<slug>` child is reachable for deletion only through `--path`, which
the realpath guard contains (`delete.py:100-107`). This keeps the sentinel
guard's rejection of `--slug _archive` from being trivially bypassable via a
kind flag.

**decided age is derived from commit date, never filesystem mtime**
(`enumerate.py:192-198`). A fresh clone resets mtime to checkout time, which
would make every doc in the repo look brand new and permanently suppress the
age signal.

**decided a *commit-count* throttle rather than a clock** (`constants.py:25-27`,
`DEFAULT_COMMIT_THRESHOLD = 10`). Hygiene debt accrues with landed work, not
with elapsed time; an idle repo should never nag. The counter is reset by
`gc stamp` (`anchor.py:126-143`), which mirrors `reconcile.stamp_reconciled`'s
off-git no-op rather than raising.

**decided the CLI renderers are typed `report: object` with per-attribute
`type: ignore`** (`cli/gc.py:212-255`). This is the *cost* of the lazy-import
layering rule — the domain type cannot be named at module scope. A
`TYPE_CHECKING`-guarded import would recover static typing without violating the
runtime layering and was not taken; the trade-off is currently paid in twelve
`type: ignore[attr-defined]` comments in one file.

**decided `gc signal` always exits 0 and is silent on a missing `.context/`**
(`cli/gc.py:174-206`). It runs on every SessionStart under `|| true`
(`hooks.py:176-183`); a probe that can fail is a probe that pollutes session
startup. Missing session id degrades to *emit-when-over-threshold*
(`anchor.py:163-172`) — never silent-forever.

## Open questions

1. **`classify` resolves ARCHIVED candidates to the wrong directory.**
   `signals.py:63-64` builds the workspace with `proposal_dir(context_dir, slug)`
   = `proposals/<slug>`, but `enumerate.py:98` places archived children at
   `proposals/_archive/<slug>`. Archived candidates therefore probe a
   non-existent path and silently emit no `orphan-empty` / `checklist-*` tags.
   `Candidate.rel_path` already carries the correct location and is unused here.
   No test covers it — `tests/cli/test_gc_cli.py:104-119` builds an archived dir
   with neither `plan.md` nor `checklist.md`, which masks the defect. Is the
   archived branch intended to be live, or is `ARCHIVED` meant to be
   signals-exempt?

2. **`CandidateKind.ORPHAN_SCAFFOLD` is never produced.** Declared at
   `enums.py:28`, referenced only inside `delete.py:55-57`'s `_PROPOSAL_KINDS`;
   no code path constructs it (`enumerate.py` emits only `PROPOSAL`, `ARCHIVED`,
   `AUDIT`). Orphan-ness is modelled as a *signal* (`orphan-empty`), not a kind.
   Reserved for a future walk, or vestigial?

3. **`signals.py` is the only cross-domain private import in `dummyindex/`.**
   `signals.py:29-33` imports `_plan_template` / `_checklist_template` from
   `proposals/store.py` (verified: no other importer outside `proposals/`).
   Unresolved: promote the templates to the `proposals` public surface, or move
   the comparison behind a `scaffold_unmodified(workspace) -> bool` predicate
   owned by `proposals` so GC stops reaching across the boundary?

4. **`root` is accepted but never read** by `classify` (`signals.py:52-53`
   calls it "signature symmetry") and is passed through by `scan.py:52`.
   Reserved seam, or a parameter to drop?

5. **`feature.json` lists no `entry_points` and no `flow_ids`** despite
   `cli/gc.py:run` being a real entry point and the SessionStart nudge
   (`hooks.py:170-184` → `gc signal` → `anchor.should_signal`) being a real
   cross-module flow. Extraction gap or deliberate?

6. **The threshold is a module constant** (`constants.py:27`), never read from
   repo config. Nothing in the code answers whether per-repo tuning is intended;
   `scan` and `should_signal` both accept a `threshold=` keyword, but no caller
   ever passes one.
