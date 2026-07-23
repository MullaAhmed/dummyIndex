---
name: dummyindex-audit
description: "Run an on-demand adversarial audit over real source from a free-text request. Scaffolds `.context/audits/{slug}/`, selects a task-dependent panel from the persona catalog rather than a fixed roster, collects independent evidence, then makes auditors read and challenge one another through up to three rebuttal rounds with early convergence. Synthesis resolves verdicts, preserves unresolved disputes, deduplicates findings, and ranks them by severity in `report.md`. The CLI only manages deterministic workspace and resumption state; the active host orchestrates judgment. A full context index is optional. Use for `/dummyindex-audit`, `$dummyindex-audit`, audit X, argue and audit, security or correctness review, or have agents critique X and report findings."
---

# /dummyindex-audit / $dummyindex-audit — argue-and-audit panel

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, diagnose with `dummyindex context check --versions` (it reports which layer is stale), then run `/dummyindex-update` on Claude or `$dummyindex-update` on Codex to bring the CLI, skills, and this repo's wiring back into sync — the update skill is non-destructive on a curated `.context/`. Don't reach for a blunt `dummyindex install` to "fix" a version skew.

You are the **audit conductor**. The user hands you a free-text description of what to audit. The `dummyindex context audit` CLI is deterministic plumbing — it scaffolds the workspace, emits the persona **catalog**, and keeps the debate **resumption log**. It never runs an agent, never picks the panel, and never decides convergence. **That judgment is yours.**

The point of this skill is *adversarial* review: not one pass of parallel opinions, but a panel that **argues** — auditors read each other's findings and concede, dispute, or defend until they reach agreement (or the round cap). What survives the debate is what you report.

## Inputs

- A **description** of what to audit (required). If the user didn't give one, ask for it in one line.
- An optional **scope** — paths to focus on (`--scope dummyindex/cli --scope dummyindex/context/domains/audit`). Without it the audit considers the whole repo; always prefer a scope when the description implies one.
- A **host-valid model selection**. On Claude, reuse the configured Claude model
  or ask for `opus-4.8|sonnet-4.6|haiku-4.5`; never silently choose one. On
  Codex, always pass `--model current` so the audit uses the running Codex model.
  Do not offer Claude labels, and do not inherit one from a shared repo config.

## The loop (run it literally)

### 0. Scaffold the workspace + read the catalog

Claude Code:

```bash
dummyindex context audit start --describe "<the user's request>" \
  [--scope <path>]... [--mode light|standard|deep] \
  [--model opus-4.8|sonnet-4.6|haiku-4.5] --json
```

Codex:

```bash
dummyindex context audit start --describe "<the user's request>" \
  [--scope <path>]... [--mode light|standard|deep] --model current --json
```

This creates `.context/audits/<slug>/` (`audit.json`, `description.md`, `catalog.json`, `findings/`) and prints a JSON object: `{slug, dir, mode, model, max_rounds, scope, catalog:[...]}`. Read it. The **`catalog`** is your menu of available auditors — each entry has `persona_id`, `role`, `subagent_type` (the real Task-tool agent to launch), `triggers`, and `description`.

If the CLI exits with a "model is required" error, ask for a Claude model on
Claude Code. On Codex, re-run with `--model current`; do not turn it into a model
choice question.

### 1. Pick the panel — task-dependent

**This is the step that makes the audit fit the task.** Read the description and the catalog, then choose the auditors whose `role`/`triggers`/`description` actually bear on what was asked. Examples:

- "audit the auth flow for security holes" → `security`, `correctness`, maybe `tests`.
- "is this cache layer correct and fast?" → `correctness`, `performance`, `architecture`.
- "review this migration" → `data-integrity`, `correctness`, `security`.

Pick **2–5** auditors. State your panel and a one-line rationale to the user before dispatching. Don't run the whole catalog by reflex — an irrelevant auditor adds noise, not signal. If the description is broad ("audit this module"), a wider panel is fine.

### 2. Round 0 — independent findings (parallel)

Dispatch the chosen panel as **parallel subagents** through the active host. For
each auditor:

- On Claude, set `subagent_type` from the persona card and fall back to
  `general-purpose` if unavailable. On the portable host path (e.g. Codex),
  use built-in `worker` because each auditor must persist a findings artifact,
  falling back to `default`. The audit remains read-only with respect to
  source code; writing its report workspace is expected. Never try to dispatch
  the Claude type name from the portable host path.
- **Inline the persona's mandate into the prompt — don't hand the subagent a path.** Each auditor's real instructions live in its markdown *body* at `agents/<persona_id>.md` (a companion file next to this SKILL.md), **not** in `catalog.json` (which carries only the one-line description, for your selection). You — the conductor — are running from the skill directory, so **read `agents/<persona_id>.md` yourself and paste its body into the delegated prompt verbatim.** A fresh subagent cannot resolve the skill path, so "tell it to read its persona file" will silently fail — inline it.
- Then add to the prompt: the **description**, the **scope** paths, an instruction to ground in `.context/conventions/*` and any relevant feature docs **if they exist**, to read the **real source** (not docs), and to write its findings to `.context/audits/<slug>/findings/<persona_id>.md` using the finding contract below.
- Log start/finish:
  ```bash
  dummyindex context audit-log --slug <slug> --round 0 --persona <persona_id> --status started
  dummyindex context audit-log --slug <slug> --round 0 --persona <persona_id> --status complete
  ```

**Finding contract** (every auditor writes bullets, no essays):

```markdown
## <persona_id> findings

- `path:Lstart-Lend` — **severity** (critical|high|medium|low|info) — claim in one sentence — evidence (what in the code shows it) — suggested fix (or "none").
```

### 3. Rebuttal rounds 1..N — argue to agreement (`max_rounds`, default 3)

`light` mode skips this step entirely — go to synthesis. For `standard`/`deep`, loop:

For round `r` (starting at 1, up to `max_rounds` from the JSON):

- Consolidate the current findings (all `findings/*.md`).
- Re-dispatch the **same panel** as parallel host-native subagents — again
  **inlining each persona's body** (from `agents/<persona_id>.md`) plus the
  consolidated findings into the prompt. Each auditor re-reads the
  *consolidated* findings — its own and its peers' — and, for each finding it has
  a view on, marks one of: **concur**, **dispute**, **defend**, or **concede**. It
  updates the finding's **status** (`open → confirmed | disputed | refuted |
  withdrawn`) and appends its rebuttal note inline. Log each persona for round
  `r`.
- **Check convergence.** Compare this round's finding statuses to the previous round's. **If no status changed — the panel agrees — STOP.** Do not run further rounds. Early agreement is the goal, not a full three rounds.
- Never exceed `max_rounds`. If you reach the cap with findings still `disputed`, that's fine — carry the open disagreement into synthesis and report it as unresolved.

`deep` mode only: before synthesis, run one **adversarial refutation** pass — for each still-`confirmed` finding, dispatch a skeptic (prompted to *refute* it) and downgrade any finding a majority of skeptics refute. Keep this lean; don't turn it into another full debate.

### 4. Synthesis — resolve, dedupe, rank → `report.md`

Write `.context/audits/<slug>/report.md` yourself (or via one Claude
`Software Architect` / Codex `default` subagent with the synthesis mandate
inlined). It must:

- Assign each surviving finding a **verdict**: `confirmed` (survived the debate), `disputed` (unresolved disagreement — show both sides), or `refuted`/`withdrawn` (dropped, listed briefly so the reader knows it was considered).
- **Dedupe** findings different auditors raised about the same `path:range`.
- **Rank** by severity (critical → info), then by verdict (confirmed first).
- Open with a 3–5 line executive summary: how many confirmed, the headline risks, and whether anything stayed unresolved.

### 5. Report to the user

Summarize in chat: the panel you ran, how many rounds it took to converge (or that it hit the cap), the confirmed findings by severity, any unresolved disputes, and the path to `report.md`.

## Discipline (non-negotiable)

- **Task-dependent panel.** Pick auditors that fit the description. Justify the panel in one line. Don't run the whole catalog by default.
- **They must actually argue.** Round 0 is opinions; the value is in the rebuttals. An auditor that only re-states its finding in round 1 hasn't engaged — prompt it to *read peers and take a position*.
- **Evidence over assertion.** Every finding and every rebuttal cites a `path:range`. "Could be vulnerable" without an attack path, or "this is slow" without a hot path, is noise — drop it.
- **Stop on agreement.** The cap is 3; the target is consensus. The moment a round changes no status, you're done debating.
- **The code wins.** Conventions and feature docs are context, not authority — when a doc and the code disagree, cite the code.
- **Read-only by default.** An audit reports findings; it does not fix them. If
  the user wants fixes, that is a separate `/dummyindex-plan` →
  `/dummyindex-build` cycle on Claude or `$dummyindex-plan` →
  `$dummyindex-build` on Codex, seeded from the report.

## CLI reference (deterministic state only)

```
dummyindex context audit start --describe "<text>" [--scope PATH]... \
    [--mode light|standard|deep] [--model current|opus-4.8|sonnet-4.6|haiku-4.5] \
    [--slug S] [--force] [--root DIR] [--json]
    → scaffold .context/audits/<slug>/ (audit.json, description.md, catalog.json,
      findings/) and emit {slug, dir, mode, model, max_rounds, scope, catalog:[...]}.
      Model is REQUIRED unless .context/config.json provides one. Codex passes
      current explicitly; Claude uses a configured or user-selected Claude model.
dummyindex context audit show --slug S [--root DIR] [--json]
    → current state: config + which rounds are complete + report path (if written).
dummyindex context audit-log --slug S --round N --persona P --status STATE [--note "..."] [--root DIR]
    → append a debate-log row. STATE: started|complete|failed|skipped. Drives resumption.
```
