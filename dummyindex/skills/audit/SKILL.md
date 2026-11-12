---
name: dummyindex-audit
description: Run a task-specific adversarial code audit, synthesize evidence-backed findings, and transfer confirmed new reusable lessons into existing canonical conventions before reporting.
---

# Dummyindex audit

You conduct the audit. The `dummyindex context audit` CLI only scaffolds and tracks its workspace. Read the real source. Conventions and feature docs guide the review, but the source is authoritative when they disagree. Audits leave the source unchanged. The closeout may update a canonical convention with a verified lesson.

## 1. Start and scope

The user must describe what to audit. If the user omits the description, ask one concise question. Pass any requested paths as `--scope`. Otherwise, choose a narrow scope when the request implies one.

Pick a model that is valid for the host. On Claude, reuse the configured selection or ask among `opus|sonnet|haiku|fable`. Never choose one silently. On Codex, always pass `--model current`. Other portable hosts should use their current-model selector. Do not offer Claude labels on the portable host path.

Start with `dummyindex context audit start --describe "..." [--scope PATH]... [--mode light|standard|deep] [--model ...] --json`. Read the returned slug, scope, mode, model, and persona catalog. Before dispatch, capture the hashes of in-scope source and test files. Also capture the hashes of any other file that you audit, before you read it. If you consider a convention update, capture its original hash too.

The CLI needs a model unless the configuration supplies one. Do not invent CLI verbs or claim that the CLI runs auditors. The host orchestration is yours.

## 2. Choose and run the panel

Select 2–5 catalog personas whose roles fit the task. Give the user a one-line panel rationale. For independent round-zero work, dispatch the personas in parallel. On Claude, use each persona's `subagent_type`, with `general-purpose` as the fallback. On the portable host path (Codex), use the built-in `worker`, with `default` as the fallback.

Read the body of each selected `agents/<persona_id>.md` and include the mandate in the prompt. Do not send a path and assume that a worker can read it. Ask the auditors to read the real source, the relevant existing conventions, and the feature docs. Also ask them to write their findings to `.context/audits/<slug>/findings/<persona_id>.md`.

Every finding cites the exact `path:Lstart-Lend` and states its severity (`critical|high|medium|low|info`). Every finding also has a one-sentence claim, the source evidence, and a suggested fix or `none`. Log the start and completion of each persona with `dummyindex context audit-log --slug S --round N --persona P --status started|complete`.

In `light` mode, skip the debate and synthesize. In `standard` and `deep`, run the same panel for rebuttal rounds, up to the CLI's `max_rounds` (never more than 3). Include the other findings and require each auditor to concur, dispute, defend, or concede with cited evidence. Update the statuses (`open|confirmed|disputed|refuted|withdrawn`).

Stop immediately when a round changes no statuses. Preserve unresolved disputes. In `deep` only, dispatch skeptics to refute each remaining confirmed finding before synthesis. Downgrade a finding only when a majority of the skeptics refute it.

## 3. Synthesize findings

Read all findings and rebuttals. Deduplicate claims about the same issue. Keep only supported outcomes: `confirmed`, `disputed` with both sides, or `refuted`/`withdrawn` with a brief note. Rank the findings by severity, then put the confirmed findings ahead of the disputed ones. The source decides if it conflicts with a convention or feature document.

## 4. Finalize the report

Write `.context/audits/<slug>/report.md` with a 3–5 line executive summary, the findings by severity and verdict, and the unresolved disagreements. Also include any lesson that you deferred or found already covered. Finish the report before the closeout inventory. Do not edit the report afterward.

When you write `.context/` documents, follow the Writing standard in `../council/00-overview.md` (ASD-STE100). After you write, run `dummyindex context check --style`.

## 5. Close out one reusable lesson

For confirmed findings, consider at most one concise, new, reusable rule. The rule is a contract that audited source and independently verified behavior support. The rule is not a suggested fix. A confirmed helper contract may be reusable while the caller bug is open. Do not imply that the caller bug is fixed.

Skip covered lessons, update an ID, or supersede an obsolete managed rule. Preserve the owner text. Include only the meaningful existing tests.

If no supported novel rule exists, omit `learning_reflection`. If no test applies, submit with no tests. The gate then records `evaluated/blocked` without promotion.

`learning_reflection` is one lesson object: `cue`, `lesson`, `evidence`, and `confidence` (`low|medium|high`). All of these fields are required and nonempty. The optional `edits` rows use the form `{component, change, verdict}`. The verdict is one of `helped|hurt|no_observed_effect|confounded`. A list is rejected.

The delivery fields (`verified`, `target`, `rule_id`, start-captured `expected_sha256`, repo-relative `sources`, `tests`, optional `supersedes`) follow `closeout.md`. `body` is ignored for a lesson-shaped reflection. The rule text becomes `When {cue}: {lesson}`. Cite `sources` or `evidence`, not `body`. Never cite the temporary audit workspace.

Read the sibling `closeout.md` and give every workspace file a specific reason. Recheck every captured source/test and convention hash before closeout. On a mismatch, stop and report it.

Finalize the report first. The `closeout.md` recipe writes it outside the workspace with `transfers: []`. Run:

`dummyindex context gc closeout --kind audit --slug <slug> --manifest <manifest.json> --json`

The learning status is `applied|evaluated|blocked|no_entry|pending|ignored|failed`. Only `failed` exits non-zero. The `blocked` status prints with exit 0. Do not override or claim adoption.

If the closeout rejects the manifest, stop. Do not refresh the hashes or rerun the recipe automatically. Re-review the changed inventory or evidence. Prepare a new manifest only after you recheck the report and every disposition. Once the closeout accepts a receipt, never mutate the report.

Report the returned `learning` state accurately. An applied rule qualifies only its checked project behavior. It does not establish model improvement.

Tell the user the panel, the rounds to convergence (or the cap), and the confirmed findings by severity. Also tell the user the unresolved disputes, the learning state, and the report path.
## CLI reference

- `dummyindex context audit start --describe TEXT [--scope PATH]... [--mode light|standard|deep] [--model current|opus|sonnet|haiku|fable] [--slug S] [--force] [--root DIR] [--json]` creates the audit head, brief, catalog, and findings directory.
- `dummyindex context audit show --slug S [--root DIR] [--json]` shows current state and report path.
- `dummyindex context audit-log --slug S --round N --persona P --status started|complete|failed|skipped [--note TEXT] [--root DIR]` appends debate progress.

To implement findings, use the separate plan/build workflow, not an audit.
