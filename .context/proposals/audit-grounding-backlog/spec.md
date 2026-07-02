# Audit grounding pack + backlog awareness — design

**Date:** 2026-06-17
**Status:** approved (brainstorm) — pending spec review
**Touches feature(s):** the `dummyindex context audit` domain + `skills/audit/SKILL.md`

## Problem

The `/dummyindex-audit` panel is supposed to ground its auditors in the
project's existing knowledge. Today that grounding is **only a soft sentence**
in `SKILL.md` step 2 — *"instruct the subagent to ground in
`.context/conventions/*` and any relevant feature docs if they exist."* Nothing
deterministic gathers or surfaces those docs, so in practice the panel skips
them: it audits the raw source blind to documented conventions, prior
decisions, and — critically — **already-known issues**. The result is audits
that re-discover accepted risks as "new" findings and ignore the backlog of
deferred work.

The user wants the audit to **take existing docs and conventions into account**
and to **include any backlogged stuff** — where "backlog" spans prior audit
findings, per-feature `concerns.md`, deferred-TODO docs, session-memory
deferrals, and decision/convention records under `docs/`.

## Goals

1. Deterministically assemble a **grounding pack** when an audit is scaffolded,
   covering conventions, scope-relevant feature docs, and a **known-backlog**
   section.
2. Harden `SKILL.md` so the conductor **must** read the pack, feed it to every
   auditor, and **cross-check findings against the backlog** (dedupe known
   issues; mark each backlog item still-open / fixed / regressed).
3. Degrade gracefully on a repo with no `.context/` index (the audit skill
   already promises to run without one).

## Non-goals

- No LLM in the gathering step — it stays deterministic plumbing, like
  `proposals/scan.py`.
- No deep whole-repo glob. Discovery is bounded; unusual doc locations are the
  user's responsibility via `--backlog <path>`.
- No fragile semantic parsing of arbitrary report/doc formats. The pack stores
  **pointers + short excerpts**; the auditors open the real files (they already
  read real source).
- The audit stays **read-only** — it reports backlog status, it does not fix.

## Approach (decisions locked in brainstorm)

- **Mechanism: hybrid.** CLI gathers + writes the pack; SKILL is hardened to
  require reading it and to add a backlog cross-check discipline.
- **Discovery: bounded-auto + explicit `--backlog`.** Always auto-gather the
  predictable, fast sources; require `--backlog <path>` for arbitrary external
  docs; plus a shallow allowlisted scan of repo-root + `docs/` for conventional
  names.
- **Pack is a manifest of pointers + excerpts**, not a full content dump.
- **Flag name: `--backlog <path>`** (repeatable).

## Architecture & components

The split is preserved: **CLI = deterministic plumbing, SKILL = LLM judgment.**

### 1. New module `dummyindex/context/domains/audit/grounding.py`

- `gather_grounding(context_dir, *, description, scope, backlog_paths) -> Grounding`
  — pure, no LLM. Reuses `query()` (same as `proposals/scan.py`) and the
  conventions glob, then adds backlog discovery (below).
- `render_grounding_md(grounding) -> str` — renders the agent-facing brief.
  Sections present only when non-empty.

Target file size: well under the 400-line guideline; split a `_discovery.py`
helper out only if it crosses ~300 lines.

### 2. New frozen dataclass `Grounding` (in `models.py`)

Immutable, categorized **path tuples** (repo-root- or `.context/`-relative
strings, never absolute, for cross-machine stability) plus light excerpt
metadata:

```
@dataclass(frozen=True)
class GroundingItem:
    path: str            # relative path the auditor opens
    note: str = ""       # one-line excerpt/title/summary (may be empty)

@dataclass(frozen=True)
class Grounding:
    conventions: tuple[GroundingItem, ...] = ()
    feature_docs: tuple[GroundingItem, ...] = ()   # spec/plan/concerns of related features
    prior_reports: tuple[GroundingItem, ...] = ()  # sibling audits' report.md
    concerns: tuple[GroundingItem, ...] = ()       # related features' concerns.md
    session_memory: tuple[GroundingItem, ...] = ()
    backlog_extra: tuple[GroundingItem, ...] = ()  # --backlog + allowlisted external scan
    def to_dict(self) -> dict: ...
    @property
    def is_empty(self) -> bool: ...
```

(`concerns` is split out from `feature_docs` because it is *backlog input*, not
just context — synthesis reports its status separately.)

### 3. `workspace.ensure_audit`

- New parameter `backlog_paths: Sequence[str] = ()`.
- Calls `gather_grounding(...)` and writes two new scaffolded artifacts via
  `write_text_atomic`:
  - `grounding.md` — the brief (`render_grounding_md`).
  - `grounding.json` — `Grounding.to_dict()` (machine companion for tests +
    resumption).
- Both appended to `written`.

### 4. `AuditStart` (models.py)

- Carries the `Grounding`.
- `to_dict()` / `start --json` emit a new `grounding` key:
  `{path: ".context/audits/<slug>/grounding.md", counts: {conventions: N, prior_reports: M, ...}}`
  so the conductor sees the pack exists and how much is in it.

### 5. CLI `dummyindex/cli/audit.py`

- Add `backlog` to `repeatable_keys` in `_audit_start`'s `_parse_flags` call.
- Pass `backlog_paths=tuple(repeated.get("backlog", ()))` into `ensure_audit`.
- Human output: one extra line summarizing the grounding pack
  (`grounding: 3 conventions, 2 prior reports, 1 backlog doc`).
- `start --json` includes the `grounding` key.

### 6. `skills/audit/SKILL.md` (repo source)

- **Step 0**: document that `audit start` now writes `grounding.md`; the JSON
  gains a `grounding` key.
- **Step 1/2**: the conductor **must read `grounding.md`** and **inline its
  backlog + doc pointers into every auditor's Task prompt** — same hard
  inlining discipline already used for persona bodies (a fresh subagent can't
  resolve paths, and a soft "if it exists" is the exact failure mode being
  fixed). Replace the soft step-2 sentence.
- **New discipline bullet — Backlog cross-check.** Each auditor must:
  (a) judge code against the documented conventions/decisions in the pack;
  (b) for each known-backlog item, mark it **still-open / fixed / regressed**
  with a `path:range`; (c) **dedupe against already-known** so the report does
  not re-raise an accepted/known risk as a new finding.
- **Synthesis (step 4)**: add a **"Backlog status"** subsection to `report.md`
  alongside the findings — the disposition of each known-backlog item.
- Update the **CLI reference** block: `--backlog PATH` (repeatable) on
  `audit start`, and the new `grounding.md` artifact + `grounding` JSON key.

## Discovery rules (bounded-auto + explicit)

Always auto-gathered (predictable, fast, mostly inside `.context/`):

| Source | Where | Category |
|---|---|---|
| Conventions | `.context/conventions/*.md` | `conventions` |
| Related feature docs | `query(description + " " + scope, top_k=5)` → each `feature_id`'s `spec.md`/`plan.md` that exist | `feature_docs` |
| Feature concerns | the same related features' `concerns.md` (if present) | `concerns` |
| Prior audit reports | `.context/audits/*/report.md`, excluding the current slug; note = its executive-summary line | `prior_reports` |
| Session-memory deferrals | `.context/session-memory/*` (if the dir exists) | `session_memory` |

Conventional external docs — **shallow, allowlisted** (no `**` deep walk):

- Repo root + `docs/` walked to a bounded depth (e.g. ≤ 3 levels under `docs/`).
- Allowlist of conventional names (case-insensitive): `DECISIONS.md`,
  `BACKLOG.md`, `TODO.md`, `deferred*.md`, and files inside `adr/` or
  `decisions/` directories.
- Ignore the usual noise dirs (`.git`, `node_modules`, `.venv`/`venv`,
  `__pycache__`, `.context/cache`).
- → `backlog_extra`.

Explicit:

- Every `--backlog <path>` (file or directory) the user passes, verified to
  exist; a directory contributes its `*.md` children. → `backlog_extra`.

### Excerpt rule

`note` is a single trimmed line: for an audit `report.md`, the executive-summary
line; for `concerns.md`/feature docs, the first heading or first non-empty line;
for external docs, the first non-empty line. Bounded length (~120 chars). No
multi-line content — the auditor opens the file for the rest.

## Error handling

- `query()` raising `FileNotFoundError` (no features index) → empty
  `feature_docs`/`concerns`, pack still written. (Same degradation as
  `proposals/scan._related_features`.)
- A `--backlog` path that does not exist → **hard usage error** (exit 2) with a
  clear message — an explicitly-named missing doc is a user mistake, fail fast.
- A doc that can't be read (permissions/encoding) → skip with its `note` set to
  an empty string; never abort the scaffold over one unreadable doc.
- All writes atomic (tmp + `replace`), consistent with `ensure_audit` today.

## Data flow

```
audit start --describe "…" [--scope P]… [--backlog D]…
  └─ ensure_audit(…, backlog_paths)
       └─ gather_grounding(context_dir, description, scope, backlog_paths)
            ├─ query()                → feature_docs, concerns
            ├─ conventions glob       → conventions
            ├─ sibling audits walk    → prior_reports
            ├─ session-memory glob    → session_memory
            └─ allowlist scan + --backlog → backlog_extra
       └─ write grounding.md + grounding.json
  └─ print summary  /  --json emits {…, grounding:{path,counts}}

/dummyindex-audit conductor
  └─ reads grounding.md → inlines backlog + pointers into EVERY auditor prompt
  └─ auditors: judge vs conventions; mark each backlog item open/fixed/regressed; dedupe known
  └─ synthesis: report.md gains a "Backlog status" subsection
```

## Testing (TDD, pytest, mirrors `tests/context/domains/audit/`)

`grounding.py`:
- related-feature selection from `query` (with a built fixture index);
- conventions glob;
- prior-report discovery excludes the current slug; picks up siblings;
- concerns gathered for related features only;
- session-memory gathered when dir present, skipped when absent;
- allowlisted external scan finds `DECISIONS.md`/`adr/*` and ignores noise dirs;
- explicit `--backlog` file and directory;
- graceful degradation: no `.context/` index → empty feature/concerns, pack
  still produced;
- excerpt rule: executive-summary line pulled from a report fixture.

`workspace`:
- `grounding.md` + `grounding.json` written and present in `written`;
- `--force` re-scaffolds the pack.

CLI (`test_audit_cli.py`):
- `--backlog` parses (repeatable);
- `--backlog` with a non-existent path → exit 2;
- `start --json` includes the `grounding` key with counts;
- human output prints the grounding summary line.

Rendering:
- `render_grounding_md` includes a section per non-empty category and omits
  empty ones.

Target: keep the domain's existing coverage bar (≥ 80%); new module fully
covered.

## Out of scope / follow-ups

- Extracting *individual* open findings out of prior `report.md` files (vs.
  pointing at the report + its summary line) — left to the LLM conductor for
  now; revisit if pointer-level proves too coarse.
- A `--no-backlog` opt-out flag — add only if audits in backlog-heavy repos get
  noisy.
