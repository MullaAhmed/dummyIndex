# Design — Industry-standard generated agent-doc suite

**Date:** 2026-06-26
**Status:** Design (awaiting review)
**Scope:** Redesign the entire doc suite dummyindex generates for an indexed repo — the
always-loaded `.claude/CLAUDE.md` managed block, the on-demand `.context/HOW_TO_USE.md`
navigation hub, the task playbooks, and the supporting leaf docs (`PROJECT.md`, `INDEX.md`,
`architecture/overview.md`) — so they match how Claude Code is actually meant to be set up.

---

## 1. Problem

dummyindex injects a managed block into every indexed repo's `CLAUDE.md`. Today that block
(`_V0_BLOCK_BODY` in `dummyindex/context/output/bootstrap.py:25`) is a single ~147-word
wall-of-text paragraph that is **100% meta-instruction about dummyindex's own refresh
machinery** and **0% project onboarding**. A fresh agent reading it cannot name the project's
stack, its test command, its lint command, or one repo-specific gotcha — it fails the
community-standard "fresh-session summary" test.

The deeper issue is the same across the suite: the *load-tier architecture is correct*
(tiny always-loaded `CLAUDE.md` → on-demand `HOW_TO_USE.md` hub → leaf docs), and the
`conventions/*.md` docs are genuinely excellent. The failure is **information routing** —
the always-loaded tier and the top of the hub spend their whole budget on tool-meta, while
the project facts a cold agent needs (commands, architecture, gotchas) sit one or two
navigation hops away or are missing entirely. The data to fix this **already exists** in the
index; it just never reaches the surfaces that need it.

### Evidence base

This design is grounded in a research + fact-check + audit pass (workflow `wg7wycujv`,
2026-06-26): 6 research lenses, 31 adversarially fact-checked claims, 4 per-artifact audits.
Key *verified* facts (several correcting widespread myths):

- CLAUDE.md (user + project) **auto-loads into context every session** — a fixed token cost
  on every exchange. Source: code.claude.com/docs/en/memory.
- Official target **< 200 lines**; "longer files consume more context and reduce adherence";
  "bloated CLAUDE.md files cause Claude to ignore your actual instructions."
- Official **Include/Exclude** table: *include* non-guessable commands, project-specific
  style overrides, test runner, repo etiquette, architecture decisions, gotchas; *exclude*
  standard language conventions, anything inferable from code, "write clean code." The current
  block is entirely the Exclude column.
- Lead with a **Commands** block (test/lint/run) — the highest-value non-inferable fact.
  Confirmed by exemplars getzep/graphiti and sst/opencode and by `/init` output.
- Use deterministic **hooks** for what a linter enforces, not CLAUDE.md prose ("CLAUDE.md is
  advisory; hooks are deterministic").
- **"Context rot" is measured** (Chroma 2025, 18 models): irrelevant context *degrades*
  output, not just wastes tokens. A tight file beats a comprehensive one.
- Anthropic-internal: *"the better you document workflows, tools, and expectations in
  CLAUDE.md files, the better Claude Code performs."*
- **@imports** exist (max **four** hops; they expand at launch and do **not** save context);
  `CLAUDE.local.md` is **not** deprecated; memory loads **user → project** order.
- **Claude Code does not natively read `AGENTS.md`** (issue #6235, open, ~5.5k 👍). The
  official bridge is a `CLAUDE.md` that imports it via `@AGENTS.md`, or a symlink. Codex,
  Cursor, Gemini CLI, and Copilot-adjacent tools read `AGENTS.md` natively.

---

## 2. Goals / Non-goals

**Goals**

1. The generated `.claude/CLAUDE.md` passes the fresh-session test: a cold agent can name the
   stack, the test/lint/run commands, and the architecture-at-a-glance from it alone.
2. Every always-loaded surface stays lean and scannable (headers + bullets, most load-bearing
   line first), well under the 200-line official ceiling.
3. The "serves Claude Code, Cursor, Codex, Aider" claim becomes **true** via an emitted
   `AGENTS.md` single source + a `CLAUDE.md` `@AGENTS.md` bridge.
4. Tool-maintenance internals (reconcile mechanics, GC lifecycle, gitattributes,
   secret-scanner notes) move off the per-task surfaces into a maintainer-facing doc.
5. Fix the concrete defects the audit found (Section 6).
6. The project-onboarding content is **council/LLM-authored** at build time, **grounded in
   already-extracted facts**, and **preserved + fingerprinted** so it never silently drifts.

**Non-goals**

- No change to the deterministic backbone extraction (map/tree/symbols/AST). Untouched.
- No re-clustering of features or changes to `conventions/*.md` content (they are the model
  the rest should shrink toward — keep them).
- Not adding per-tool files beyond `AGENTS.md` in this pass (no GEMINI.md, no
  `.cursor/rules`, no Aider config). `AGENTS.md` covers the read-natively tools; deeper
  per-tool wiring is a follow-up.

---

## 3. Architecture (load tiers) — preserved

The audits validate the existing tiering. Keep it; only change *what content sits in each*.

| Tier | Surface | Load behavior | Rule |
|---|---|---|---|
| 0 | root `AGENTS.md` (new single source) + `.claude/CLAUDE.md` (`@AGENTS.md` bridge) | eager, every session + every subagent | tiny, high-signal, project-specific |
| 1 | `.context/HOW_TO_USE.md` | on demand, per task | navigation hub: routing table + project signal at top |
| 2 | `playbooks/*.md`, `conventions/*.md`, `features/`, `PROJECT.md`, `architecture/` | on demand | reference depth; triggered from the hub |
| M | `playbooks/maintain-context.md` (new) | on demand, only when maintaining the index | reconcile/GC/CI internals evicted here |

---

## 4. Decisions

- **D1 — Council-authored onboarding content.** The project-specific block (identity,
  commands, 2-sentence architecture, gotchas) is authored by the `/dummyindex` council during
  build/enrichment, like `/init` would — not a static string. (User decision.)
- **D2 — Grounded authoring (drift safeguard).** The council authoring step is fed the
  already-extracted facts: `PROJECT.md` one-liner, detected commands from
  `conventions/testing.md` + `conventions/coding-practices.md` + `pyproject [project.scripts]`
  / `.pre-commit-config.yaml` / CI yaml, and `architecture/overview.md` +
  `folder-organization.md`. The council *curates/phrases*; it does not invent commands.
- **D3 — Preserve + fingerprint (drift safeguard).** The authored content is stored as a
  managed artifact. `rebuild --changed` **preserves** it (same contract as curated feature
  docs — never clobbers). A content fingerprint is recorded so the SessionStart drift hook can
  flag a stale managed block, closing the exact staleness hole found on-disk today.
- **D4 — `AGENTS.md` single source + `CLAUDE.md` bridge.** Onboarding content is emitted as a
  managed block in root `AGENTS.md`. `.claude/CLAUDE.md`'s managed block becomes a thin
  `@AGENTS.md` import plus Claude-Code-specific lines (the `/dummyindex` reconcile pointer,
  skill triggers). One source of truth; serves all named tools. (User decision.)

---

## 5. Per-artifact redesign

### 5.1 `AGENTS.md` (new single source) + `.claude/CLAUDE.md` bridge

`AGENTS.md` managed block (council-authored, grounded), target ≈ 30–45 lines:

```markdown
<!-- dummyindex:begin (managed — regenerate with `dummyindex context bootstrap`) -->
# <Project Name>

<One sentence: what it is + why. Council-authored from PROJECT.md's opening line.>

## Commands
```bash
<test>          # detected, e.g. python -m pytest tests/ -q --tb=short
<lint>          # detected, e.g. ruff check .
<format-check>  # detected, e.g. ruff format --check .
<run>           # detected, e.g. dummyindex <subcommand>
```

## Architecture
<Two sentences, council-authored. Names the top-level layers + the entry point.>
Full map and per-feature docs: see `.context/HOW_TO_USE.md`.

## Working here
- **Read `.context/HOW_TO_USE.md` before any non-trivial task** — it routes you to the right
  doc instead of grepping.
- The index can be stale: **when it disagrees with the code, the code wins.**
- Conventions live in `.context/conventions/` — check `naming.md` before naming anything new.
- <0–3 council-authored repo gotchas, only if genuinely non-inferable.>
<!-- dummyindex:end -->
```

`.claude/CLAUDE.md` managed block becomes:

```markdown
<!-- dummyindex:begin (managed — regenerate with `dummyindex context bootstrap`) -->
@AGENTS.md

## For Claude Code
- When your explicit instruction contradicts a `.context/` spec/plan, **you win** — note the
  divergence and proceed.
- Refresh the index: backbone → `dummyindex context rebuild --changed`; content → the
  `/dummyindex` reconcile procedure.
<!-- dummyindex:end -->
```

Notes: the literal `@AGENTS.md` must be on its own line and **not** inside backticks (imports
skip code spans). The import expands at launch — that is expected; the win is single-sourcing,
not token saving. Both files keep the existing begin/end marker machinery; the reconcile seam
(`claude_md.py`) is generalized to manage a block in `AGENTS.md` as well as `.claude/CLAUDE.md`.

### 5.2 `HOW_TO_USE.md` (navigation hub)

- **Lead with project signal + Commands.** Inject (from D2 data) a one-line "what this is" and
  a **"How do I build / run / test / lint?"** row at the top of the routing table — the
  CRITICAL gap today (no command surface anywhere a cold agent is told to look).
- **Add a playbook trigger table** (replace the single bare `playbooks/` row): each playbook
  with its WHEN ("adding a capability → add-feature.md", "fixing a defect → fix-bug.md", …) so
  lazy-loading actually fires.
- **Evict tool-internals** to `playbooks/maintain-context.md`: the GC lifecycle + 4-verb CLI
  table, the gitattributes/linguist/`gc/state.json` internals, and the detect-secrets guidance.
  Keep only the one-line staleness policy in the hub.
- **One source of truth:** keep rows to trigger + destination; push the `features/INDEX.json`
  key-schema detail down into `features/HOW_TO_NAVIGATE.md` (which the row already links).
- Reserve bold for the two rules that change behavior (check `naming.md`; code wins).
- Target: roughly half current length.

### 5.3 Playbooks

- **Fix the dead link (CRITICAL):** all six playbooks cite `council/65-reconcile.md`, which
  does not resolve under `.context/`. Repoint to the in-tree authority a cold agent *can* open
  — `HOW_TO_USE.md` → "When the index is wrong". Drop the non-existent `update.md` reference
  from add-feature.md. Add a build-time check that every inter-doc link in a generated playbook
  resolves under `.context/`.
- **Unify provenance:** fold `gc-context.md` into the single generation path (register it in
  `_PLAYBOOK_BODIES` / `PLAYBOOK_IDS`, or import its body from the GC domain) so one `rebuild`
  regenerates all playbooks. Trim it to its peers' altitude.
- **Cut platitudes:** remove restated general SWE procedure (~70% today); keep only the
  non-inferable repo-specific payload (which `.context/` file for which task, the exact
  re-index/reconcile sequence, true gotchas). Target ~12–18 lines each.
- **Inject real commands:** replace "look for pytest/jest/vitest" hedges with the detected
  command (or a pointer to `conventions/testing.md`).
- **Align retrieval doctrine:** lead "find existing symbols" steps with
  `dummyindex context query "<task>"`; frame grepping `map/symbols.json` as fallback (today the
  playbooks contradict the hub's "walk the tree, don't grep" headline).
- **Per-playbook freshness line:** one shared appended sentence — "If a cited `.context/`
  artifact disagrees with the source you open, trust the source and run
  `dummyindex context rebuild --changed`" — so each is safe read in isolation by a fresh subagent.

### 5.4 Supporting suite

- **`PROJECT.md`:** add a **Commands** section (install / run / test / lint / format-check),
  single-sourced from the detected commands; cite CI as source of truth; link
  `testing.md`/`coding-practices.md` rather than duplicating. Trim the "Existing documentation"
  catalog to a one-line pointer to `source-docs/INDEX.md`.
- **Version stamp:** eliminate the contradiction (PROJECT.md says 0.28.0 *and* 0.27.0;
  `meta.json` 0.29.3; code 0.29.4). Single-source the version from `meta.json` and have
  `rebuild --changed` re-stamp it atomically — never a hand-maintained constant.
- **`INDEX.md`:** replace the 339-line flat `ls -R` enumeration with a one-level-deep map of
  the top-level `.context/` structure (≈10 dirs + key root files, each with a one-line
  "what/when"). ~90% smaller; stop duplicating HOW_TO_USE's tables. Keep any full manifest as
  JSON, not Markdown.
- **`architecture/overview.md`:** replace the "unknown"-role row for the core `dummyindex/`
  package with the real layer breakdown (share or link `folder-organization.md`) so the file an
  agent opens for "what's the layout?" actually names the layers + entry points.

---

## 6. In-flight bug fixes (independent of the redesign)

1. **Stale on-disk managed block** — `.claude/CLAUDE.md` is missing the GC sentence its own
   generator emits (never regenerated after the GC feature shipped). Re-bootstrap, and add the
   fingerprint drift check (D3) so this class of drift is caught.
2. **Dead `council/65-reconcile.md` link** in all six playbooks (Section 5.3).
3. **Three contradictory version stamps** (Section 5.4).
4. **`gc-context.md` provenance split** — generated outside the playbook loop (Section 5.3).

---

## 7. Generation mechanics

- **Authoring step (council):** during `/dummyindex` build/enrichment, a council step authors
  the onboarding content from the D2 inputs and writes it to a stored managed artifact (e.g.
  `.context/_managed/onboarding.md`, or a structured field consumed by the emitters). Reconcile
  refreshes it.
- **Command detection (deterministic helper):** a pure function resolves test/lint/format/run
  from `pyproject [project.scripts]`, `conventions/testing.md`, `.pre-commit-config.yaml`, and
  CI yaml. Feeds both the council prompt (D2) and a deterministic fallback.
- **Emitters:** `generate_managed_block()` (bootstrap.py) and a new `AGENTS.md` emitter read
  the stored onboarding artifact when present, else a minimal deterministic skeleton
  (identity + detected commands + the read-HOW_TO_USE pointer) so a never-enriched repo still
  gets a useful, honest block.
- **Preservation:** `rebuild --changed` preserves the authored artifact (curated-layer
  contract). Fingerprint stored alongside; SessionStart drift hook compares and flags.
- **Reconcile seam:** `claude_md.py` generalized to fold/manage `AGENTS.md` + `.claude/CLAUDE.md`
  consistently (markers, idempotency, atomic write, inode-safety all reused).

Likely touch points (exact paths confirmed at plan time via `.context/`): `bootstrap.py`,
`claude_md.py`, `instructions.py` (`_HOW_TO_USE`, `_PLAYBOOK_BODIES`, architecture overview),
`docs.py` (PROJECT.md / INDEX.md), the playbook write loop (`context/build/runner.py:508`), the
PROJECT.md/version emitter, the council step (skill + `dummyindex/skills/.../council/`), and the
SessionStart drift hook.

---

## 8. Testing strategy (TDD)

- **Unit:** command-detection helper (fixtures: uv/pytest/ruff repo, npm/jest repo, bare repo);
  `AGENTS.md` emitter and the `@AGENTS.md` bridge content; emitter fallback when no authored
  artifact; fingerprint compute/compare.
- **Generalized reconcile seam:** managing a block in both `AGENTS.md` and `.claude/CLAUDE.md`
  (idempotency, preserve surrounding content, unbalanced-marker degradation, inode-safety) —
  extend the existing `claude_md.py` test suite.
- **Link integrity:** build-time check that every generated inter-doc link resolves under
  `.context/` (would have caught the `council/65-reconcile.md` and `update.md` bugs).
- **Doc-shape assertions:** generated `CLAUDE.md`/`AGENTS.md` contain a Commands fence and the
  read-HOW_TO_USE pointer; HOW_TO_USE has a build/test/lint routing row and a playbook trigger
  table; each playbook ≤ target line count; no tool-internals sections remain in the hub.
- **Fresh-session regression (the real bar):** a test that the emitted block names stack +
  test command + architecture pointer (string assertions over the generated output).
- Run the project's real suite: `python -m pytest tests/ -q --tb=short`; `ruff check .`;
  `ruff format --check .`.

---

## 9. Rollout & impact

- dummyindex ships to PyPI and this changes output for **every** repo it indexes. Bump minor
  version. The managed-block change is non-destructive (markers preserve surrounding user
  content; `AGENTS.md` is additive). Existing repos pick it up on the next
  `bootstrap`/`rebuild`/`update`.
- `/dummyindex-update` re-runs `dummyindex install` with a deterministic backbone rebuild — it
  must regenerate the managed blocks so existing repos heal the stale-block drift.
- Document the new `AGENTS.md` emission + bridge in CHANGELOG and the skill docs.

---

## 10. Open questions

1. Storage location for the authored onboarding artifact — a dedicated
   `.context/_managed/onboarding.md`, or a structured field in `meta.json` / `PROJECT.md`
   front-matter? (Leaning dedicated file: easy to preserve + fingerprint.)
2. Should the deterministic fallback block ship *commands-only* (safest, never wrong) and let
   the council add prose later, or attempt a minimal council pass even on first `bootstrap`?
3. `AGENTS.md` already present in a target repo (hand-written or from another tool): fold our
   managed block in (like the CLAUDE.md fold) vs. leave it and only write `.claude/CLAUDE.md`?
   (Leaning: fold a managed block in, preserving their content — consistent with the existing
   CLAUDE.md reconcile behavior.)
