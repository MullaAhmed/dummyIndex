---
name: dummyindex-plan
description: Grounded planning for a new feature in a repo that already has a `.context/` index. Turns a natural-language feature request into a consistency-checked `.context/proposals/<slug>/` artifact — `proposal.json`, `spec.md` (intent + contracts + Acceptance), `plan.md` (ordered, file-path-naming tasks that cite reused symbols), and a flat `checklist.md`. Reuses the deterministic `query` retrieval to ground the plan in existing features + conventions; no guessing about what already exists. Triggers — `/dummyindex-plan`, "plan a feature", "plan this feature", "draft a spec and plan", "scaffold a proposal".
allowed-tools: Read, Write, Bash
---

# /dummyindex-plan — Grounded planning

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, re-run `dummyindex install --scope user`.

You turn a natural-language feature request into a **consistency-checked proposal** under `.context/proposals/<slug>/`. The deterministic CLI scaffolds the artifact and grounds it against the existing index; **you** flesh out the prose. Python is the toolbox.

## What you produce

A `.context/proposals/<slug>/` folder with four files:

| File | Owner | Contents |
|---|---|---|
| `proposal.json` | CLI | Structured head: `slug`, `title`, `status`, `related_features`, `conventions`, `reused_symbols`. |
| `spec.md` | You | Intent, contracts, and an `## Acceptance` checklist of `- [ ]` items. The CLI seeds a `## Consistency` block. |
| `plan.md` | You | Ordered tasks, each naming the file path(s) it touches, citing reused symbols. |
| `checklist.md` | You | A flat `- [ ]` list derived from the plan tasks **plus** the spec's Acceptance items. |

## The flow

1. **Resolve scope + slug.** Take the feature request as the `--title`. Derive a short `--slug` (lowercase, digits, `-`/`_` only — no spaces, no `/`). Confirm the repo has a `.context/` (run `dummyindex ingest <path>` first if not).

2. **Scaffold + ground (the CLI does this in one call):**

   ```bash
   dummyindex context propose --slug <slug> --title "<request>" [--root <repo>] [--force]
   ```

   This creates the four template files, runs the deterministic consistency scan (reusing `query` — **no LLM**), and writes the hits into `proposal.json` (`related_features` + `conventions`) and a `## Consistency` block in `spec.md`. It prints the proposal path + related features.

3. **Read the consistency hits first.** Open `proposal.json` and the `## Consistency` block in `spec.md`. For each related feature, read `.context/features/<id>/spec.md` to learn what already exists — so the new plan **reuses** rather than reinvents. Skim the listed `conventions/*.md`.

4. **Flesh out `spec.md`** — intent (problem + who), contracts (inputs/outputs/invariants/seams), and a real `## Acceptance` section: concrete, testable `- [ ]` criteria. Keep the CLI-seeded `## Consistency` block.

5. **Flesh out `plan.md`** — ordered tasks, each naming the exact file path(s) it touches. Where a task can reuse an existing symbol, cite it by name from `.context/map/symbols.json` (and the feature it lives in). Prefer reuse over net-new code.

6. **Derive `checklist.md`** — flatten the plan tasks and the spec's Acceptance items into one top-to-bottom `- [ ]` list. This is the execution surface a later step works through.

## Checklist + spec-led discipline (embed this in how you work)

- **Read `spec.md` first.** It is the source of truth for *what* and *why*. The plan serves the spec; the checklist serves both.
- **Work `checklist.md` top-to-bottom.** One item at a time, in order.
- **Tick only after verifying.** Flip `- [ ]` → `- [x]` for an item *only* once you've confirmed it (its test passes / the behavior is observed). Never tick on intent.
- **Stop and report if blocked.** If an item can't be completed (missing dependency, contradictory requirement, ambiguous scope), stop, leave it unticked, and report the blocker with a concrete next step — don't paper over it or skip ahead.

## Done

Report: the proposal path, the related features the scan surfaced, and a one-line summary of the plan's shape (how many tasks, which existing symbols it reuses).
