# Audit — two-reconciliation-onboarding-bugs-1-an-old-claude-md-file-o

> Scaffolded by `dummyindex context audit start`. The `/dummyindex-audit` skill drives the argue-and-audit panel from here.

## Request

Two reconciliation/onboarding bugs: (1) an old CLAUDE.md file or pre-existing .claude folder is not reconciled into the new dummyindex setup correctly — it's left dangling instead of being folded in or migrated; (2) no recouncil/reconcile is triggered or checked-for after the Stop hook fires — the index can silently drift because nothing prompts a reconcile when a session ends.

## Scope

_Whole repository (no --scope given)._

## Settings

- mode: `standard`
- model: `opus-4.7`
- max rebuttal rounds: 3
