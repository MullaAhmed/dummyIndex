# Spec — Context-hygiene GC: detect & delete stale / superseded / dead generated docs (and trivially-dead code) via a commit-throttled council sweep

> Scaffolded by `dummyindex context propose`, then fleshed out by `/dummyindex-plan`
> and revised once after a critique panel (reuse/arch, risk/edge, testability).
> Source of truth for **what** and **why**. The plan serves this spec; the
> checklist serves both.

## Intent

**Problem.** dummyindex generates per-task workspaces under `.context/` —
`proposals/<slug>/` (plan artifacts) and `audits/<slug>/` (argue-and-audit
panels) — but nothing ever *retires* them. They accumulate:

- **Orphan scaffolds** — proposals created by `context propose` then abandoned,
  left as nothing but the four unmodified template files.
- **Superseded plans** — a later proposal/feature replaces an earlier one, but
  the earlier `spec.md`/`plan.md`/`checklist.md` still sits on disk describing
  intent that no longer matches the code.
- **Done / dead audits** — a finished `audits/<slug>/report.md` whose findings
  were long since fixed, plus its `_debate-log.json` / `findings/` scratch.
- A stale `_archive/` convention (today `proposals/_archive/ponytail-improvements/`)
  that was a manual park-it-here workaround and just defers the growth.

**Who it hurts.** AI coding agents. They navigate `.context/` as canonical
context. A superseded `plan.md` or a done audit's findings read as *current
intent*, so an agent can plan against a retired design, "resume" a dead
checklist, or treat fixed findings as open. The folders also grow unbounded,
adding navigation noise and token cost to every `propose`/`build`/grounding pass.

**Solution — distill nothing, delete decisively.** A **context-hygiene GC**:

1. **Deterministic plumbing** (`context/domains/gc/` + `cli/gc.py`, no LLM):
   enumerate candidate generated docs (skipping sentinels), gather objective
   signals (status, age, checklist completion, report-written, orphan/empty,
   git-tracked), compute commits-since-last-sweep, execute *bounded, guarded*
   deletions of whole doc workspaces, and stamp a GC commit anchor.
2. **An LLM council sweep** (`/dummyindex-gc` skill — the multi-agent step):
   fan out subagents that walk the docs **PageIndex-style** (`context query`)
   and judge each candidate **stale / superseded / dead / no-longer-useful**,
   *grounded in the current session's work* — then **confirm with the user**
   and delete. Dead **docs** are deleted directly; **trivially-dead code**
   (an unreferenced private symbol, 0 callers, passing every exclusion guard)
   is removed through the normal implementer+tester path after confirmation and
   only when the full suite stays green; broader/riskier dead code is **routed
   to a new proposal**, never auto-removed.
3. **A commit-throttled SessionStart signal**: when ≥ N commits (default 10)
   have landed since the last GC anchor, the existing SessionStart hook emits a
   one-line nudge — "N commits since last hygiene sweep — run `/dummyindex-gc`".
   No clock, no cron: the throttle is commit-count, mirroring how reconcile
   already anchors on `meta.indexed_commit`.

This mirrors the repo's own idiom: **deterministic CLI + LLM skill**, exactly
how `audit-panel` (plumbing) + `/dummyindex-audit` (council) and `build-loop`
(plumbing) + `/dummyindex-build` (dispatch) are split. Detection is reasoning;
the destructive act is bounded Python gated behind explicit confirmation.

## Resolved design decisions (locked with the user — do not relitigate)

1. **Disposition is DELETE, not archive/summarize.** No digest/ledger; no
   `_archive/`. The existing `_archive/` becomes a delete-candidate too. The goal
   is to *shrink* the footprint and *remove* misleading docs.
2. **Determination is agent/council-driven and session-contextual.** "Stale /
   superseded" is an LLM judgment about whether an old artifact still matches
   the code and the work in flight — **not** a blind age rule. The deterministic
   layer only supplies *signals*; the council decides; the user confirms.
3. **Delete only the genuinely dead.** Stale / superseded / dead / no-longer-
   useful — **not** every `done` proposal. A `done`-but-still-relevant plan stays
   until it's actually superseded.
4. **Dead code: delete trivially-dead with confirm, route the rest.** A 0-caller
   unreferenced *private* symbol that passes every exclusion guard (below) may be
   removed — but only via implementer+tester, after confirm, and only if the full
   suite stays green. Anything broader → a new proposal through `build` + review.
   *(Panel dissent on record: the architecture critic recommended cutting code
   disposition from this proposal entirely and routing ALL code to a follow-up,
   to keep "GC never touches source" absolute. The user explicitly chose to keep
   trivially-dead-code deletion in scope, so it stays — hardened with the
   exclusion guards in Contracts. Per the repo rule, the user's explicit
   instruction wins over the spec/panel.)*
5. **Trigger = commit-count throttle (default 10), not cron.** SessionStart
   nudge when `commits_since(gc_anchor) >= threshold`; the sweep stamps a new
   anchor to reset the counter. Plus on-demand `/dummyindex-gc` anytime.
6. **Confirmation always gates deletion.** No artifact (doc or code) is removed
   without explicit user confirmation surfaced by the skill; the CLI delete verb
   refuses to act without an explicit target + `--yes`, and needs a *second*
   explicit flag (`--allow-untracked`) to remove a git-untracked workspace.

## Contracts

### CLI surface — `dummyindex context gc <verb>` (`cli/gc.py`, wire-only)

A single `gc` subcommand (registered as `ContextSubcommand.GC` in
`context/enums.py` + dispatched in `cli/__init__.py`) that parses its own flag
alphabet and sub-dispatches on the first positional verb — the same shape as
`cli/audit.py` (`audit start|show`) rather than four top-level enum entries.

- **`gc status [--json] [--root DIR]`** — enumerate every candidate generated
  doc with its signals + the commit-throttle state (`commits_since`, anchor,
  threshold, `should_signal`, and an `anchor_orphaned` flag when an anchor is
  recorded but unknown to the repo after a history rewrite). Read-only, exit 0.
  This is the report the skill and the SessionStart hook consume.
- **`gc delete --kind proposal|audit (--slug S | --path P) --yes [--allow-untracked] [--force-partial] [--root DIR]`**
  — delete **one** generated-doc workspace dir, atomically. Guards, in order:
  1. `validate_slug` rejects an out-of-charset slug (`ProposalSlugError` /
     `AuditSlugError`, exit 2) — this catches `../../x` before any path work.
  2. **Sentinel reject**: a slug that is `_archive`, begins with `_`, is `.`/`..`,
     or is empty → `GcTargetError` (exit 2). (`_archive` is charset-valid and
     resolves *inside* the root, so the traversal guard below does NOT catch it —
     this guard does.)
  3. **Realpath containment**: re-resolve the target (and, for `--path`, follow
     symlinks) and assert it is inside `.context/{proposals,audits}/`; an escape
     raises `GcPathError` (exit 2). Reachable only via `--path`/a symlinked
     workspace, never via `--slug`.
  4. **Liveness**: refuse a proposal whose `status == in_progress` or whose
     checklist is `checklist-partial` unless `--force-partial` is given
     (`GcTargetError`, exit 2) — a structural backstop against deleting a plan a
     `/dummyindex-build` is mid-flight on.
  5. **Recoverability**: a git-untracked target is refused unless
     `--allow-untracked` is *also* present (deletion is then permanent); the
     refusal/warning is explicit.
  Without `--yes` it prints the dry-run target and deletes nothing (exit 0).
  Deleting an already-absent in-root target is an idempotent no-op: exit 0 with a
  `nothing to delete` note (NOT `GcTargetError`). Never deletes source code.
- **`gc stamp [--to <sha>] [--root DIR]`** — advance the GC commit anchor to HEAD
  (or `--to`), mirroring `build/reconcile.py:stamp_reconciled`. Off-git = no-op.
- **`gc signal [--json] [--root DIR]`** — the SessionStart throttle probe: prints
  the one-line nudge **iff** `commits_since(anchor) >= threshold` and it has not
  already signalled this session. Resolves the session id from
  `CLAUDE_CODE_SESSION_ID` (via `memory.transcript.resolve_session_id`); with no
  session id it degrades to "emit when over threshold" (never silent-forever).
  Always exit 0; silent under threshold / off-git / already-signalled.

### Domain — `context/domains/gc/` (frozen dataclasses, typed errors, no `print`)

- `enumerate_candidates(context_dir) -> tuple[Candidate, ...]` — walk
  `proposals_root` + `audits_root` children only; **skip every `_`-prefixed entry
  as a sentinel container** (covers `_archive`, and any future `_doc_backups`-style
  scratch) but surface `_archive/*` *children* as `ARCHIVED` candidates; never
  enumerate `session-memory`.
- `classify(candidate, context_dir, root) -> tuple[str, ...]` — deterministic
  signal tags only (no verdict):
  - `orphan-empty` — **precise definition**: the workspace contains only the
    unmodified scaffold templates. Keyed on `plan.md` byte-equals
    `proposals/store.py:_plan_template(title)` AND `checklist.md` byte-equals
    `_checklist_template(title)`. **`spec.md` is deliberately excluded** from the
    comparison: `cli/propose.py` runs `apply_consistency` immediately after
    scaffolding, which injects a `## Consistency` block into `spec.md`, so a real
    scaffold's `spec.md` is *never* byte-equal to `_spec_template` — comparing it
    would make `orphan-empty` permanently unreachable. `apply_consistency` never
    touches `plan.md`/`checklist.md`, so those two precisely capture "scaffolded
    but never authored". (A committed but never-fleshed-out scaffold *is*
    orphan-empty even though its dir has tracked files — "empty" means "empty of
    authored content", not "empty directory".)
  - proposals: `status:<value>` from `proposal.json`, and checklist completion via
    `domains/buildloop/checklist.py:parse_checklist` + `counts`
    (`checklist-complete` / `checklist-partial`).
  - audits: `report-written` — computed as `audit_dir(ctx, slug)/"report.md"`
    exists. (`audit_dir`/`audits_root` are real domain symbols; the existence
    probe itself is **not** a shared symbol today — it lives at `cli/audit.py:157`.
    Extract a tiny `report_written(context_dir, slug) -> bool` into
    `domains/audit/workspace.py` and call it from both the CLI and gc, rather than
    copying the one-liner.)
  - cross-cutting: `untracked` (git ls-files miss → unrecoverable on delete);
    `age-<n>d` from the git last-commit date only (`git log -1 --format=%ct`),
    `None`/omitted off-git or for an untracked path (mtime is NOT used — a fresh
    clone resets mtime to checkout time, so it would read 0d for everything).
- `commits_since(root, anchor) -> int | None` — **new git helper in
  `build/git_delta.py`** (`git rev-list --count <anchor>..HEAD` via `_run_git`);
  `None` off-git, on unborn HEAD, when `anchor` is `None`, or when `anchor` is
  unknown to the repo (validate via `commit_exists`). The `None`-on-orphaned-anchor
  case is *safe* (signal goes dark) but `gc status` surfaces it as `anchor_orphaned`
  with a "re-baseline with `gc stamp --to HEAD`" hint (mirrors reconcile's
  `anchor_broken`).
- `read_gc_anchor(context_dir) -> str | None` / `write_gc_anchor(context_dir, sha)`
  — the **committed** GC anchor, in `.context/gc/state.json` (`{"anchor": sha}`),
  written atomically via `context/domains/atomic_io.py:write_text_atomic`. Reader
  tolerates a corrupt/partial file the way `memory/nudge.py:_load_state` does:
  missing file / `JSONDecodeError` / non-dict / missing-or-non-string `anchor`
  → `None` (never a garbage sha).
- `should_signal(context_dir, root, session_id, *, threshold=DEFAULT_COMMIT_THRESHOLD) -> bool`
  — `commits_since >= threshold` AND not-already-signalled-this-session. The
  fire-once memo reuses the **pattern** of `memory/nudge.py:already_nudged` /
  `mark_nudged`, but lives in **gitignored** `.context/cache/gc-nudge-state.json`
  (NOT the committed `gc/state.json`), keyed by session id, pruned to a 100-entry
  cap. Best-effort, last-writer-wins: two concurrent SessionStart hooks may both
  emit (an idempotent reminder) — acceptable.
- `delete_workspace(context_dir, *, kind, slug=None, path=None, allow_untracked=False, force_partial=False) -> DeleteResult`
  — the bounded destructive op implementing guards 1–5 above; returns what was
  removed + any refusal reason. Atomic-ish: validate → sentinel-reject → resolve →
  contain → liveness → recoverability → `shutil.rmtree`.

### Reuse (cite before writing new — corrected against real source)

| Need | Reuse | From |
|---|---|---|
| Slug validation + traversal-charset guard | `validate_slug`, `proposal_dir`, `proposals_root` | `domains/proposals/store.py:37,59,54` |
| Audit enumeration + dirs + slug | `audits_root`, `audit_dir`, `read_audit`, `validate_slug` | `domains/audit/workspace.py:75,83,204,56` |
| `report.md` written probe | **extract** `report_written(ctx, slug)` from the inline check | currently `cli/audit.py:157` → move into `domains/audit/workspace.py` |
| Checklist completion % | `parse_checklist`, `counts` | `domains/buildloop/checklist.py` |
| Commit anchor advance/refusal pattern | `stamp_reconciled`, `_read_indexed_commit`, `head_commit`, `is_ancestor_of_head`, `commit_exists` | `build/reconcile.py`, `build/git_delta.py` |
| Per-session fire-once memo (pattern, gitignored cache) | `already_nudged`, `mark_nudged`, `_state_path` shape | `domains/memory/nudge.py:33-67` |
| Corrupt-state tolerance | `_load_state` | `domains/memory/nudge.py:38-46` |
| Session id resolution | `resolve_session_id` | `domains/memory/transcript.py:43` |
| Atomic writes | `write_text_atomic` | `context/domains/atomic_io.py:12` |
| PageIndex retrieval (council walk) | `query` | `domains/query.py:220` (module, not a package) |
| Dead-code evidence (0 callers) | `calls` edges + the exclusion-guard inputs below | `.context/features/symbol-graph.json` |
| Tech-debt sibling pattern (markers) | `harvest_debt` | `domains/debt/harvest.py` (sibling; do not duplicate) |
| Council scaffold + persona→agent resolve | **pattern reference only — no shared code** | `domains/audit/` (the gc skill is a one-shot fan-out; it ships no persona catalog/debate) |
| `ProposalStatus.SUPERSEDED` intermediate marker | extend the closed enum | `domains/proposals/enums.py:8` |

### Trivially-dead-code exclusion guards (the council MUST apply all before proposing a code deletion)

A symbol is **never** "trivially dead" — route it to a proposal instead — if it
is: (a) a CLI verb handler / `run(args)` reachable from `cli/__init__.py`'s
dispatch table; (b) a hook entry point in the `hooks.py` / `claude_settings.py`
command set (e.g. `signal`, `decide_nudge`); (c) named in any `__all__` /
re-exported public surface; (d) a serialization round-trip member
(`to_dict`/`from_dict`/`__init__`); (e) referenced anywhere under `tests/`
(confirm whether `symbol-graph.json` even includes `tests/` — if not, "0 callers"
is blind to all test usage, which by itself bars relying on the graph alone); or
(f) reachable by dynamic dispatch. Only a leading-`_` private symbol with 0
callers that passes ALL of (a)–(f) is eligible, and removal must be **proven** by
implementer+tester (full suite green after deletion), not by the graph signal.

### Invariants

- **Never delete outside `.context/{proposals,audits}/`** — realpath-contained.
- **Sentinel slugs (`_archive`, leading-`_`, `.`/`..`, empty) are never deletable.**
- **An `in_progress` / `checklist-partial` proposal is delete-blocked** without
  `--force-partial` (structural guard, independent of council judgment).
- **Deletion is confirmation-gated** (`--yes`), and **untracked deletion needs a
  second flag** (`--allow-untracked`).
- **GC never edits/removes source code directly** — code goes through
  implementer+tester (trivially-dead) or a proposal (broader).
- **Off-git / orphaned-anchor is a graceful no-op** for throttle/anchor.
- **Idempotent**: `status`/`signal` read-only; re-`delete` of a gone dir = no-op;
  `stamp` idempotent at a HEAD.
- **session-memory is out of scope** — it self-rolls; GC never touches it.
- **Storage split**: the committed `.context/gc/state.json` holds ONLY the anchor;
  the per-session memo lives in gitignored `.context/cache/`. `.context/gc/` is a
  new committed `.context/` artifact and is registered in the canonical layout.

### Non-goals

- No archival tier, no summary/digest file, no `_archive/` (explicitly dropped).
- No time/cron scheduling (commit-count throttle only).
- No automatic, unconfirmed deletion of anything.
- No bulk source dead-code purge (only guard-passing trivially-dead symbols).

## Acceptance

Criteria assert the *capability* against synthetic fixtures, never this repo's
mutable contents (dogfood is a soft, non-asserting GATE).

- [ ] Against a constructed fixture `.context/` (a never-fleshed scaffold proposal,
      a populated `done` proposal, a `checklist-partial` proposal, a finished audit
      with `report.md`, an `_archive/<slug>` child), `gc status` tags the scaffold
      `orphan-empty`, the finished audit `report-written`, the archive child
      `ARCHIVED`, the partial proposal `checklist-partial`, and prints
      `commits_since` + `threshold`; `--json` emits the same payload. *(test:
      `tests/context/domains/gc/test_enumerate.py`, `tests/cli/test_gc_cli.py`.)*
- [ ] `orphan-empty` is true iff the workspace's `plan.md` AND `checklist.md`
      byte-equal the scaffold templates (`spec.md` excluded — `apply_consistency`
      rewrites it); a proposal with an authored `plan.md` is NOT orphan-empty.
- [ ] `commits_since(root, anchor)` equals `git rev-list --count anchor..HEAD`;
      returns `None` off-git, on **unborn HEAD**, and for an **unknown sha**;
      git-fixture test (`tests/context/build/test_git_delta.py`).
- [ ] `gc delete --slug X --kind proposal` without `--yes` deletes nothing and
      prints the dry-run target (exit 0); with `--yes` removes exactly that dir.
- [ ] A malformed slug (`../../etc`) raises `ProposalSlugError`/`AuditSlugError`
      (exit 2, nothing deleted); **`--slug _archive` and `--slug _` raise
      `GcTargetError`** (exit 2, nothing deleted); a `--path` whose realpath escapes
      the root (symlinked workspace) raises `GcPathError` (exit 2).
- [ ] `gc delete` on a `checklist-partial`/`in_progress` proposal is refused
      without `--force-partial`; on a git-untracked workspace it is refused without
      `--allow-untracked` and prints an explicit "unrecoverable (not in git)"
      warning; an already-absent in-root target is exit 0 `nothing to delete`.
- [ ] `gc stamp` writes the anchor to `.context/gc/state.json`; a later `gc status`
      reports `commits_since == 0`; off-git `stamp` is a no-op; a corrupt
      `gc/state.json` makes `read_gc_anchor` return `None` (not a garbage sha).
- [ ] `gc status` flags `anchor_orphaned` (with the re-baseline hint) when an
      anchor is recorded but unknown to the repo.
- [ ] `gc signal` with `CLAUDE_CODE_SESSION_ID=S` prints the nudge on the first
      over-threshold call and is silent on the second call with the same `S`; with
      the env var unset it still emits when over threshold; silent under threshold
      / off-git. The memo lives under `.context/cache/` (gitignored), the anchor
      under `.context/gc/` (committed) — distinct paths asserted.
- [ ] The SessionStart hook command set still contains **both** `plan-update` and
      `memory session-start` AND the new gc-signal; combined over-threshold stdout
      contains the drift report AND the gc nudge line (extend
      `tests/context/test_hooks.py`).
- [ ] `/dummyindex-gc` skill exists; `tests/test_skills_doc_hygiene.py` gains
      gc-skill cases asserting it (a) marks the user-confirm step + the dogfood
      GATE as non-dispatchable; (b) documents the ordered contract `gc status →
      PageIndex walk → user-confirm → gc delete (docs) / implementer+tester
      (trivial code) / new proposal (broad code) → gc stamp → reconcile-if-code`;
      (c) never shows `gc delete` without `--yes` + a confirm gate.
- [ ] `dummyindex-gc` is added to the install tuple (`installer/install.py`), the
      uninstall sibling list (`installer/uninstall.py`), and the
      `test_install_copies_sibling_skills` parametrize roster
      (`tests/test_install.py`); install-then-uninstall leaves no `dummyindex-gc/`.
- [ ] `ProposalStatus.SUPERSEDED` round-trips through `Proposal.to_dict/from_dict`;
      existing `planned`/`in_progress`/`done` `proposal.json` still load.
- [ ] `cli/help.py` `context gc` text lists all four verbs; `HOW_TO_USE.md` has a
      hygiene-lifecycle section stating generated docs are GC'd (deleted), not
      archived; `playbooks/gc-context.md` names the `gc status → confirm →
      gc delete → gc stamp` order (grep-asserted in the doc-hygiene test);
      `.context/gc/` is named in the canonical layout.
- [ ] Full suite green via `python -m pytest tests/ -q` (3.10 + 3.12); no `print`
      in `domains/gc/`; gc dataclasses `frozen=True`; gc errors subclass `GcError`
      (grep/AST-assertable, extending the existing convention-lint test pattern).

## Open questions

- **None blocking.** Two implementation choices are taken with rationale (panel
  may refine in build, not relitigate): (a) the GC anchor lives in a dedicated
  committed `.context/gc/state.json` rather than `meta.indexed_commit` (reconcile
  owns that field) or `meta.config` (viable but couples to the meta schema);
  (b) the council ships a thin one-shot fan-out skill rather than overloading the
  `audit` panel, keeping "delete" disposition out of the audit domain.
- **Deferred to build time (GATE):** actually deleting *this* repo's current
  orphans/superseded docs is a user-confirmed dogfood step that reads its targets
  from a live `gc status` run — never a hard-coded slug list.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `equip`
- `tree-enrich`
- `build-loop`
- `session-memory`
- `preflight`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
