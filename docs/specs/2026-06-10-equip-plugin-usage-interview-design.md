# Equip plugin usage interview — design

**Date:** 2026-06-10
**Status:** approved (brainstorming) → ready for implementation plan
**Component:** `equip` plugin manager (CLI + council skill)

## Problem

`equip install` wires a marketplace/vendored plugin into `.claude/settings.json`
with zero capture of *how the plugin is meant to be used in this repo*. A plugin
gets enabled on autopilot; future Claude sessions have no project-specific
guidance on when to invoke it, when not to, or what to watch for. The concrete
trigger: canvas-to-code was equipped with assumptions and the user could not tell
whether/how it was wired or how it should fire.

The fix: before a plugin is considered equipped, the **council interviews the
user** about its intended use and records the answers as a **usage playbook**
that future sessions read. This is consistent with dummyindex's standing rule —
**never silently default** (cf. the model chooser).

## Decisions (from brainstorming)

1. **Locus — both.** The CLI is the mechanism (captures the playbook pointer); the
   council (skill) is the conversation (asks the user). The CLI stays
   non-interactive.
2. **Artifact — a usage playbook doc.** Markdown under `.context/`, its path
   recorded in the manifest item's existing `grounded_in` field. Markdown-first;
   reuses the grounding mechanism rather than adding schema.
3. **Enforcement — mandatory, with a non-interactive escape.** A plugin install is
   not "done" without a usage playbook. The CLI provides `--usage-doc PATH` (the
   answer) and `--skip-usage-doc` (explicit opt-out for automation/tests). A
   plugin with no playbook reports **incomplete** in `equip status`.

## Scope

**In scope:** native + vendored *plugin* installs (opaque third-party code).
**Out of scope:** generated specialists and the core four — their `grounded_in`
flow is untouched. No manifest schema bump (reuses `grounded_in`). Deep
`.context`-index integration of the playbook is a fast-follow, not MVP.

## Design

### 1. Council interview — `dummyindex/skills/equip/SKILL.md`

A documented step inserted into the plugin-manager flow, **after `discover`
shows blast radius and before `install`**. The council asks the user, one
question at a time:

- **Purpose in this repo** — what is this plugin for, *here* specifically.
- **When to invoke / when NOT to** — the tasks or signals that should activate
  its skills/agents/commands, and cases where it should stay out of the way.
- **Constraints / guardrails** — anything to be careful about (scopes, side
  effects, data it touches).
- **Scope confirmation** — `project` (default, committed) / `local` / `user`.

The council writes the answers to `.context/equipment/<plugin>.md` using a fixed
section template (below), then runs:

```
dummyindex context equip install <plugin>@<marketplace> [--repo …] [--yes] \
  --scope <scope> --usage-doc .context/equipment/<plugin>.md
```

The SKILL.md checklist gains: "a plugin install captured a usage playbook (or was
explicitly `--skip-usage-doc`)." The plugin-manager section also documents the
`--repo` flag (added in the prior slice) for completeness.

### 2. CLI capture + gate — `dummyindex/cli/equip/discover.py`

`run_install` gains two flags via the existing `pull_flag_value` / `pull_bool_flag`
helpers:

- `--usage-doc PATH` — a repo-relative or absolute path to an **existing**
  markdown file.
- `--skip-usage-doc` — explicit opt-out.

Gate logic. **`run_install` is exclusively the plugin-manager verb** (`equip
install <plugin>@<marketplace>`); generated specialists and the core four go
through different handlers (`equip` / `add-specialist`) and never reach this
code. So the gate applies to **every `equip install`** unconditionally — no
mechanism branch needed, and specialists are inherently unaffected. (`install`
currently wires NATIVE only; when the VENDOR install branch lands it inherits the
same gate for free.)

- Neither flag → `rc 2`, message:
  `error: a plugin install needs a usage playbook — the /dummyindex-equip council
  writes one, or pass --usage-doc <path> (or --skip-usage-doc to opt out).`
- Both flags → `rc 2` (contradiction).
- `--usage-doc` given but file missing → `rc 1`:
  `error: --usage-doc <path>: file not found.`
- `--usage-doc` valid → record its **repo-relative POSIX** path in the recorded
  item's `grounded_in` (via `_record_native`). `--skip-usage-doc` → `grounded_in`
  stays empty (the incomplete state).

The gate runs after the approval (`--yes`) check and before settings are written,
so a refused install writes nothing. Path is made repo-relative against
`project_root` when it resolves under it; an absolute path outside the repo is
recorded as-is (with a warning, since it won't travel with the committed repo).

### 3. Status surfacing — `equip status`

`status` already classifies items as pristine / user-modified / missing. Add: a
marketplace/vendored item (`mechanism in {native, vendor}`) whose `grounded_in`
is empty is reported as **`incomplete: no usage playbook`**. This is a reportable
state, not an error — `status` still exits 0. Generated items are unaffected
(their grounding is the template's, recorded at generate time).

### 4. Playbook doc — `.context/equipment/<plugin>.md`

Sibling of `.context/equipment.json`. Fixed template the council fills:

```markdown
# <plugin> — usage in this repo

**Source:** <plugin>@<marketplace> (<owner/repo>)
**Scope:** project | local | user

## Purpose here
<what this plugin is for in THIS repo>

## When to use
<tasks / signals that should activate it>

## When NOT to use
<cases where it should stay out of the way>

## Constraints & guardrails
<scopes, side effects, data touched, anything to watch>
```

`grounded_in` points at this file. MVP surfaces it through `equip status` and the
manifest pointer; wiring it into `.context/INDEX` for automatic session pickup is
a noted fast-follow.

## Data flow

```
/dummyindex-equip (council)
  discover  ──▶ show blast radius
  interview ──▶ user answers (purpose / when / when-not / constraints / scope)
  write     ──▶ .context/equipment/<plugin>.md
  install   ──▶ equip install … --usage-doc .context/equipment/<plugin>.md
                  └─ CLI gate: native/vendor requires --usage-doc | --skip-usage-doc
                  └─ records grounded_in = (".context/equipment/<plugin>.md",)
status ─────▶ flags native/vendor items with empty grounded_in as incomplete
```

## Error handling

- Refused installs (missing flag / contradiction / missing file) write nothing —
  no settings, no manifest entry.
- Absolute `--usage-doc` outside the repo: install proceeds, path recorded as-is,
  warning emitted (the committed manifest will point outside the repo).
- An unparseable `settings.json` keeps the existing preserve-or-refuse behavior;
  the gate is evaluated before that path.

## Testing (existing fake-runner harness)

CLI (`tests/context/domains/equip/test_equip_discover_cli.py`):
- native install with neither flag → `rc 2`, message names `--usage-doc`.
- both flags → `rc 2`.
- `--usage-doc` missing file → `rc 1`.
- `--usage-doc` valid → `grounded_in` contains the repo-relative path; settings
  written.
- `--skip-usage-doc` → install succeeds; `grounded_in` empty.
- absolute-path-outside-repo → warning + recorded as-is.

Status (`tests/context/domains/equip/test_equip_lifecycle_*`):
- native/vendor item with empty `grounded_in` → reported `incomplete`.
- generated specialist with empty `grounded_in` → NOT reported incomplete.

## Non-goals / YAGNI

- No manifest schema bump.
- No interactive prompting in the CLI.
- No automatic `.context/INDEX` rewrite for the playbook (fast-follow).
- No change to generated-specialist grounding.
