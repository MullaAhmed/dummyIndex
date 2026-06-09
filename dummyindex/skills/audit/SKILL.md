---
name: dummyindex-audit
description: On-demand argue-and-audit panel. Give it a free-text description ("audit the auth flow for security holes", "is this cache layer correct?") and it scaffolds a `.context/audits/<slug>/` workspace, picks a TASK-DEPENDENT panel of auditors from a catalog (the personas depend on what you asked — not a fixed roster), then runs an adversarial debate: each auditor files independent findings, then they ARGUE — reading each other's findings and conceding, disputing, or defending across up to 3 rebuttal rounds, stopping early the moment they agree. A synthesis pass resolves verdicts, dedupes, and ranks by severity into `report.md`. Auditors read the REAL source (not plan.md). The CLI is deterministic plumbing (scaffold + persona catalog + resumption log); YOU orchestrate the panel via the Task tool. Triggers — "audit X", "/dummyindex-audit", "argue and audit", "have agents review/critique X and report findings". Does NOT require a full `.context/` index — it grounds in `.context/conventions/` + feature docs only if they exist.
allowed-tools: Read, Write, Bash, Task
---

# /dummyindex-audit — argue-and-audit panel

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, re-run `dummyindex install --scope user`.

You are the **audit conductor**. The user hands you a free-text description of what to audit. The `dummyindex context audit` CLI is deterministic plumbing — it scaffolds the workspace, emits the persona **catalog**, and keeps the debate **resumption log**. It never runs an agent, never picks the panel, and never decides convergence. **That judgment is yours.**

The point of this skill is *adversarial* review: not one pass of parallel opinions, but a panel that **argues** — auditors read each other's findings and concede, dispute, or defend until they reach agreement (or the round cap). What survives the debate is what you report.

## Inputs

- A **description** of what to audit (required). If the user didn't give one, ask for it in one line.
- An optional **scope** — paths to focus on (`--scope dummyindex/cli --scope dummyindex/context/domains/audit`). Without it the audit considers the whole repo; always prefer a scope when the description implies one.
- A **model** — never silently defaulted. If `.context/config.json` exists, the CLI reuses its model; otherwise you must pass `--model opus-4.7|sonnet-4.6|haiku-4.5` (offer the user the choice, Opus included).

## The loop (run it literally)

### 0. Scaffold the workspace + read the catalog

```bash
dummyindex context audit start --describe "<the user's request>" \
  [--scope <path>]... [--mode light|standard|deep] [--model opus-4.7|sonnet-4.6|haiku-4.5] --json
```

This creates `.context/audits/<slug>/` (`audit.json`, `description.md`, `catalog.json`, `findings/`) and prints a JSON object: `{slug, dir, mode, model, max_rounds, scope, catalog:[...]}`. Read it. The **`catalog`** is your menu of available auditors — each entry has `persona_id`, `role`, `subagent_type` (the real Task-tool agent to launch), `triggers`, and `description`.

If the CLI exits with a "model is required" error, ask the user which model to run on (Opus included) and re-run with `--model`.

### 1. Pick the panel — task-dependent

**This is the step that makes the audit fit the task.** Read the description and the catalog, then choose the auditors whose `role`/`triggers`/`description` actually bear on what was asked. Examples:

- "audit the auth flow for security holes" → `security`, `correctness`, maybe `tests`.
- "is this cache layer correct and fast?" → `correctness`, `performance`, `architecture`.
- "review this migration" → `data-integrity`, `correctness`, `security`.

Pick **2–5** auditors. State your panel and a one-line rationale to the user before dispatching. Don't run the whole catalog by reflex — an irrelevant auditor adds noise, not signal. If the description is broad ("audit this module"), a wider panel is fine.

### 2. Round 0 — independent findings (parallel)

Dispatch the chosen panel as **parallel `Task` subagents** — one message, multiple Task calls. For each auditor:

- Set `subagent_type` to the persona card's `subagent_type`. If that agent type isn't available in this repo, fall back to `general-purpose` (the inlined mandate still steers it).
- **Inline the persona's mandate into the prompt — don't hand the subagent a path.** Each auditor's real instructions live in its markdown *body* at `agents/<persona_id>.md` (a companion file next to this SKILL.md), **not** in `catalog.json` (which carries only the one-line description, for your selection). You — the conductor — are running from the skill directory, so **read `agents/<persona_id>.md` yourself with the Read tool and paste its body into the Task prompt verbatim.** A fresh subagent cannot resolve the skill path, so "tell it to read its persona file" will silently fail — inline it.
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
- Re-dispatch the **same panel** as parallel Task subagents — again **inlining each persona's body** (from `agents/<persona_id>.md`) plus the consolidated findings into the prompt. Each auditor re-reads the *consolidated* findings — its own and its peers' — and, for each finding it has a view on, marks one of: **concur** (agree), **dispute** (challenge with a counter-argument grounded in the code), **defend** (answer a dispute against its own finding), or **concede** (withdraw its finding). It updates the finding's **status** (`open → confirmed | disputed | refuted | withdrawn`) and appends its rebuttal note inline. Log each persona for round `r`.
- **Check convergence.** Compare this round's finding statuses to the previous round's. **If no status changed — the panel agrees — STOP.** Do not run further rounds. Early agreement is the goal, not a full three rounds.
- Never exceed `max_rounds`. If you reach the cap with findings still `disputed`, that's fine — carry the open disagreement into synthesis and report it as unresolved.

`deep` mode only: before synthesis, run one **adversarial refutation** pass — for each still-`confirmed` finding, dispatch a skeptic (prompted to *refute* it) and downgrade any finding a majority of skeptics refute. Keep this lean; don't turn it into another full debate.

### 4. Synthesis — resolve, dedupe, rank → `report.md`

Write `.context/audits/<slug>/report.md` yourself (or via a single `Software Architect` Task subagent). It must:

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
- **Read-only by default.** An audit reports findings; it does not fix them. If the user wants fixes, that's a separate `/dummyindex-plan` → `/dummyindex-build` cycle seeded from the report.

## CLI reference (deterministic state only)

```
dummyindex context audit start --describe "<text>" [--scope PATH]... \
    [--mode light|standard|deep] [--model opus-4.7|sonnet-4.6|haiku-4.5] \
    [--slug S] [--force] [--root DIR] [--json]
    → scaffold .context/audits/<slug>/ (audit.json, description.md, catalog.json,
      findings/) and emit {slug, dir, mode, model, max_rounds, scope, catalog:[...]}.
      Model is REQUIRED unless .context/config.json provides one (never defaulted).
dummyindex context audit show --slug S [--root DIR] [--json]
    → current state: config + which rounds are complete + report path (if written).
dummyindex context audit-log --slug S --round N --persona P --status STATE [--note "..."] [--root DIR]
    → append a debate-log row. STATE: started|complete|failed|skipped. Drives resumption.
```
