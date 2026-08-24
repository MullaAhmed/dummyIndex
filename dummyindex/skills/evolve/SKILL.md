---
name: dummyindex-evolve
description: "Close the self-improvement loop: harvest session evidence into cited diagnoses, gate bounded harness edits through deterministic evals, and keep an append-only decision history. Harvest pulls open audit findings, session-memory corrections, reconcile deltas, and transcript adoption misses into a run's harvest.json; the LLM step emits at most five candidates (curated .context/ docs, packaged skills guidance, or equipment-eval cases only — never source code); apply scores host-produced trigger observations via equip-eval scoring plus a targeted pytest subset plus ruff, blocking on any missing or malformed stage; promote of a blocked edit requires an explicit recorded override; flipped predictions surface on later harvests. Use for `/dummyindex-evolve`, `$dummyindex-evolve`, evolve this repo's harness, improve the skills/conventions from evidence, or run an overnight improvement pass."
---

# /dummyindex-evolve / $dummyindex-evolve — evidence → diagnosis → gated edit → decision history

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, diagnose with `dummyindex context check --versions`, then run `/dummyindex-update` on Claude or `$dummyindex-update` on Codex to bring the CLI, skills, and this repo's wiring back into sync.

You are the **evolution conductor**. dummyindex accumulates evidence it never acts on: audit findings sit in `audits/<slug>/report.md`, correction notes pile up in `.context/session-memory/{now,recent}.md`, reconcile keeps flagging the same blockers, transcripts record users manually invoking the context engine. The loop closes that evidence: **harvest → diagnose (you) → apply/gate → promote-or-rollback**, appending one line per transition to `.context/gc/evolution.jsonl` — the committed, append-only decision history.

## The deterministic / LLM split (read this first)

The CLI is deterministic plumbing. **You** are the only judgment in the loop, at exactly two points:

1. **Diagnosis** — you read `harvest.json` and author candidates.
2. **Observations** — you test a staged candidate against its equipment-eval suite and write what *fired* (data, not verdicts). Scoring happens in code via the equip eval domain; you never score triggers yourself and never hand-edit a gate result.

Everything else — validation, scope guard, pytest/ruff stages, verdicts, overrides recording, backups, rollback — is the CLI.

## The loop (run it literally)

### 1. Harvest

```
dummyindex context evolve harvest --run <name>
```

Writes `<run>/harvest.json`: audit findings, session-memory corrections, reconcile deltas (`drifted_features` / `unassigned_new_files` / `awaiting_enrichment`), and adoption misses (user turns that had to invoke the context engine manually — stored as counts + projects-root-relative citations only, never message content). Flipped predictions from earlier promotes print here too. Overnight/fleet mode: add `--sleep`; when there is nothing new it exits 0 having written nothing.

### 2. Diagnose (LLM step)

Read `<run>/harvest.json`. Emit **at most 5** candidates, each one JSON line:

```json
{"target_file": ".context/conventions/naming.md", "diagnosis": "...", "evidence": ["audits/<slug>/report.md:L12"], "change_sketch": "...", "prediction": "..."}
```

- `target_file` — one file (or an array of up to 5). Allowed surfaces ONLY: curated `.context/conventions/`, `.context/playbooks/`, `.context/equipment.json` + `.context/equipment-evals/`, packaged `dummyindex/skills/**/*.md`. **Never source code (`dummyindex/**/*.py`) — that goes through normal plans/reconcile. Never `features/<id>/spec.md` bodies. Never `gc/evolution.jsonl` or `gc/state.json`.**
- `evidence[]` — citations that exist: repo-relative `path:Lline` (or `projects/<slug>/<session>.jsonl:L<n>`).
- `prediction` — falsifiable: what should change/stay true once adopted. Later harvests re-check these and flag flips.

Write them to a scratch JSONL file, then validate:

```
dummyindex context evolve diagnose --run <name> --from-file candidates.jsonl
```

The CLI re-validates every candidate (structure, scope guard, citation existence). Fix errors until it accepts.

### 3. Stage + produce observations

For each candidate N (0-based line in `candidates.jsonl`), write your proposed new content for each target to `<run>/staged/<N>/<basename>`. If the targets map to an equipment-eval suite (a tool's `<tool>.suite.json`, or the candidate edits one), exercise the edited artifact the way the suite's prompts describe and record what fired:

```json
{"observations": [{"case_id": "<suite case>", "fired": true}]}
```

Save that as `<run>/observations.json`. Every suite case needs exactly one observation — partial, duplicated, or mismatched files block the gate by design.

### 4. Apply + gate

```
dummyindex context evolve apply --candidate N --run <name>
```

Three stages: trigger-eval scoring (only when a suite maps — otherwise honestly `not_applicable`), targeted pytest subset (`python -m pytest` over test files matching the changed path segments; no match → `not_applicable`), ruff on touched Python. Verdict semantics: **any errored or missing stage yields `blocked`, never pass.**

### 5. Promote / rollback / discard

```
dummyindex context evolve promote --candidate N --run <name>
```

A passing verdict adopts the edit (originals backed up under `<run>/backup/<N>/`). A **blocked** verdict refuses without `--override "<reason>"` — the reason lands in `evolution.jsonl` next to the promotion. A *failed* gate cannot be overridden; fix the candidate.

- Changed your mind after promoting: `rollback --candidate N --run <name>` restores the backups.
- Not worth keeping: `discard --candidate N --run <name>` drops the staged copy, adopts nothing.

## Falsification round

Each harvest compares fresh evidence paths against open predictions from earlier promotes. A flagged flip means reality contradicted the prediction — read the matched citations, draft a rollback proposal (or a corrective candidate), and say so out loud to the user.

## Discipline (non-negotiable)

- **Never hand-edit `evolution.jsonl`, `gate-*.json`, `harvest.json`, or `candidates.jsonl`.** They are CLI-owned state; hand edits poison the decision history. Corrupt JSONL lines are skipped with a warning on read — report them, don't "fix" them silently.
- **Never show or run a bare `promote` on a blocked verdict** — the refusal is the safety interlock; the override reason must be typed by someone who read why it was blocked.
- **Scope guard is a floor, not a ceiling.** Even where a target is technically allowed, ask whether it belongs to this loop or to a normal plan/reconcile.
- **Evidence over vibes**: every candidate cites existing artifacts; a diagnosis you cannot cite does not get authored.
- **Sleep contract**: fleet runners drive `harvest --sleep` overnight; exit 0 with zero writes means "nothing new" — that is success, not failure.

## Portable host compatibility

This procedure runs identically on Claude Code (`/dummyindex-evolve`) and on any portable host path (`$dummyindex-evolve` through whatever mechanism invokes an installed skill): the CLI verbs above are identical; only who orchestrates the LLM steps differs (native subagents vs. Task dispatch).

## CLI reference

```
dummyindex context evolve harvest [--since YYYY-MM-DD] [--sleep] [--json] [--run NAME] [--root DIR]
dummyindex context evolve diagnose --run NAME --from-file FILE [--json]
dummyindex context evolve apply --candidate N --run NAME [--json]
dummyindex context evolve promote --candidate N --run NAME [--override "REASON"]
dummyindex context evolve rollback --candidate N --run NAME
dummyindex context evolve discard --candidate N --run NAME
```
