# Build-loop MVP — seams contract + slice specs (A/B/C)

**Date:** 2026-06-06
**Status:** FROZEN contract + 3 thin-MVP slice specs. Each slice is built by a parallel agent in its own worktree.
**Parent:** `docs/specs/2026-06-06-build-loop-overview.md`
**Principle:** dummyindex stays the spine (never writes production code). It plans, equips `.context/`-grounded tooling into `.claude/`, orchestrates, and re-indexes. KISS: thin vertical MVPs that prove the loop end-to-end, not complete subsystems.

---

## PART 0 — FROZEN SEAMS CONTRACT (all three slices build against this; do not deviate)

### 0.1 Proposal artifact — produced by A, consumed by C
Location: `.context/proposals/<slug>/`
Files:
- `proposal.json` — `{ "schema_version": 1, "slug": str, "title": str, "status": "planned|building|done", "related_features": [str], "conventions": [str], "reused_symbols": [str] }`
- `spec.md` — intent, contracts, **acceptance criteria** (a `## Acceptance` section with `- [ ]` items).
- `plan.md` — ordered implementation tasks; each task names target file paths.
- `checklist.md` — the **executable checklist**: a flat markdown list of `- [ ]` items derived from `plan.md` tasks + `spec.md` acceptance. C flips `- [ ]` → `- [x]` as items complete.

### 0.2 Equipment manifest — produced by B, consumed by C
Location: `.context/equipment.json`
Schema:
```json
{ "schema_version": 1, "items": [
  { "kind": "agent|skill|command|hook", "name": "string",
    "path": ".claude/...relative-path...", "source": "generated|installed",
    "capabilities": ["implement","test","review","format","..."],
    "grounded_in": [".context/HOW_TO_USE.md", ".context/conventions/..."] } ] }
```
B writes additively and **honors preflight/never-clobber**: read the preflight inventory, never overwrite a user-authored file, sentinel-mark generated files, back up before writing.

### 0.3 C mapping — execution
For each unchecked `- [ ]` item in `checklist.md`: pick the `equipment.json` item whose `capabilities` best match the task (simple keyword match on the item text), else fall back to `general-purpose` (or a `dev-pick` result). Dispatch grounded in `.context/` + the proposal's `spec.md`/`plan.md`. On task complete → flip the checklist item. When all items checked → run `dummyindex context rebuild --changed` to re-index (close the loop).

### 0.4 Checklist + spec-led discipline (the shipped reliability behavior)
Every build-loop skill instructs its agent to: (1) read the proposal `spec.md` first; (2) work `checklist.md` top-to-bottom; (3) tick an item **only after verifying** it (tests pass / file exists / behavior confirmed); (4) stop and report if blocked rather than guessing. (Informed by hermes-agent: context files shape the agent; verification precedes tick; isolated workstreams.)

### 0.5 CLI split (Python = deterministic toolbox; markdown skill = orchestration)
Each slice ships a thin CLI module + a skill. The CLI does deterministic state/scaffolding; the skill drives agents.

### 0.6 NEW-FILES-ONLY rule for the parallel agents (critical)
Each agent creates ONLY files under its own new modules/dirs. It must **NOT edit any shared registration file**: `dummyindex/cli/__init__.py`, `dummyindex/context/enums.py`, `dummyindex/cli/_usage.py`, `dummyindex/__main__.py`, `pyproject.toml`, `dummyindex/skills/skill.md`. Instead, each agent writes an `INTEGRATION.md` at the repo root of its worktree listing the exact registrations it needs (enum member, handler import+entry, usage block, install-copy block, package-data glob, skill.md pointer). The orchestrator's integration pass applies all registrations once.

### 0.7 Conventions (docs/CONVENTIONS.md — all slices follow)
Wire-only CLI returning int (0/2/1); frozen dataclasses with `tuple[...]`; enum constants; typed exceptions per area; `print` only at CLI boundary; atomic writes (tmp+replace); tests under `tests/context/`, pytest markers, bare asserts; run `uv run pytest`. Reuse existing helpers: `_parse_path_and_root` / `_resolve_context_root` (`cli/_common.py`), `query` domain, `dev-pick`, preflight inventory.

---

## SLICE A — Grounded planning (`/dummyindex-plan`)

**Goal:** turn an NL feature request into a `.context/proposals/<slug>/` artifact (§0.1) that is consistency-checked against `.context/`.

**New files only:**
- `dummyindex/cli/propose.py` — `_cmd_propose(args) -> int`. `dummyindex context propose --slug S --title "..."`:
  1. Create `.context/proposals/<slug>/` with `proposal.json` + template `spec.md`/`plan.md`/`checklist.md` (atomic writes; refuse if slug dir exists unless `--force`).
  2. Run a **consistency scan** (deterministic, no LLM): reuse the `query` domain to get top related features for the title; list `.context/conventions/*` that exist; write findings into `proposal.json.related_features` + `conventions` and a `## Consistency` section stub in `spec.md`.
  3. Print the proposal path + the related features found.
- `dummyindex/context/domains/proposals/` — domain pkg: `models.py` (frozen `Proposal` dataclass), `store.py` (`proposal_dir`, `ensure_proposal`, atomic write, `write_text_atomic`), `scan.py` (`scan_consistency(context_dir, title) -> RelatedHits` reusing the query domain). `__init__.py` re-exports.
- `dummyindex/skills/plan/SKILL.md` — `name: dummyindex-plan`. Orchestration: gather the NL request → run `dummyindex context propose` → read the consistency hits → the agent fleshes `spec.md` (intent/contracts/**acceptance**), `plan.md` (ordered tasks w/ file paths citing reused symbols from `map/symbols.json`), and derives `checklist.md` (`- [ ]` per task + acceptance). Embed the §0.4 discipline. Output: a ready `.context/proposals/<slug>/`.
- `tests/context/test_propose.py` — propose scaffolds the dir; idempotency/`--force`; consistency scan returns related features on a fixture repo; proposal.json schema.
- `INTEGRATION.md` — registrations needed (enum `PROPOSE="propose"`; handler; usage; skill packaging + install copy for `skills/plan/`; skill.md pointer).

**Acceptance / checklist (A):**
- [ ] `dummyindex context propose --slug demo --title "X"` creates `.context/proposals/demo/` with all 4 artifact files.
- [ ] Re-running without `--force` errors; with `--force` overwrites.
- [ ] Consistency scan lists ≥0 related features (reuses `query`) and existing conventions, persisted to `proposal.json`.
- [ ] `skills/plan/SKILL.md` exists, embeds the spec+checklist discipline, names the exact artifact files.
- [ ] `uv run pytest tests/context/test_propose.py -q` passes; whole `tests/context` suite still green.
- [ ] `INTEGRATION.md` lists every shared-file registration.

---

## SLICE B — Equip (`/dummyindex-equip`), templates-first

**Goal:** generate a small set of project-tuned tooling from templates + (optionally) install matching existing tooling into `.claude/`, additively and safely; record it in `equipment.json` (§0.2).

**New files only:**
- `dummyindex/cli/equip.py` — `_cmd_equip(args) -> int`. `dummyindex context equip [--for-proposal S] [--dry-run]`:
  1. Detect stack: read `.context/map/files.json` + repo manifests → a dominant stack label (KISS: extension/framework counting; reuse `dev-pick` detection helpers if importable).
  2. Read the **preflight inventory** (`build_preflight_report`) to know existing `.claude/` agents/skills/hooks — never clobber.
  3. From `templates/`, render a small tuned set: (a) one project implementer agent (`.claude/agents/<stack>-implementer.md`) whose prompt embeds `.context/` grounding + conventions; (b) one verify/test skill (`.claude/skills/<proj>-verify/SKILL.md`); (c) if a formatter is detected (ruff/black/prettier), one PostToolUse format hook entry (recorded in equipment, applied to settings by integration — do NOT edit settings.json here in MVP; list it).
  4. Sentinel-mark generated files; skip any path that already exists and isn't ours (report skips). `--dry-run` prints what it would write.
  5. Write `.context/equipment.json` (§0.2). Print a summary.
- `dummyindex/context/domains/equip/` — `models.py` (frozen `EquipmentItem`, `EquipmentManifest`), `detect.py` (`detect_stack(context_dir) -> StackProfile`), `render.py` (template fill), `manifest.py` (read/write equipment.json atomically), `safety.py` (preflight-aware `is_safe_to_write(path)`). `__init__.py` re-exports.
- `dummyindex/skills/equip/templates/` — `*.md.tmpl` (implementer-agent, verify-skill) with `{{stack}}`/`{{conventions}}`/`{{context_root}}` slots.
- `dummyindex/skills/equip/SKILL.md` — `name: dummyindex-equip`. Orchestration: run `dummyindex context equip` → review the proposed toolkit with the user-safety framing → confirm. Embed §0.4.
- `tests/context/test_equip.py` — stack detection on a fixture; render fills slots; manifest schema; **never-clobber** (pre-existing user file is skipped, not overwritten); `--dry-run` writes nothing.
- `INTEGRATION.md` — registrations + the format-hook settings entry to apply.

**Acceptance / checklist (B):**
- [ ] `dummyindex context equip --dry-run` writes nothing and lists the planned items.
- [ ] `dummyindex context equip` on a fixture writes the implementer agent + verify skill under `.claude/`, additively.
- [ ] A pre-existing user file at a target path is **skipped** (never overwritten); the skip is reported.
- [ ] `.context/equipment.json` matches §0.2 schema and lists every item with `capabilities` + `grounded_in`.
- [ ] Generated tooling prompts reference `.context/` (grounding present).
- [ ] `uv run pytest tests/context/test_equip.py -q` passes; whole `tests/context` suite green.
- [ ] `INTEGRATION.md` lists registrations + the format-hook entry.

---

## SLICE C — Build (`/dummyindex-build`), grounded execution

**Goal:** drive a proposal's `checklist.md` to completion using `equipment.json` (with generic fallback), then re-index. MVP = deterministic checklist/mapping state in CLI; the skill does the actual agent dispatch.

**New files only:**
- `dummyindex/cli/build_loop.py` — `_cmd_build(args) -> int`. Verbs:
  - `dummyindex context build --proposal S --next` → print the next unchecked checklist item + the mapped equipment item (capability match per §0.3, else `general-purpose`/`dev-pick`) + the grounding paths to inject. JSON with `--json`.
  - `dummyindex context build --proposal S --check "<item text or index>"` → flip that `- [ ]` to `- [x]` atomically.
  - `dummyindex context build --proposal S --status` → counts done/total; when all done, print the re-index command to run.
- `dummyindex/context/domains/buildloop/` — `checklist.py` (parse/flip `- [ ]` items atomically), `mapping.py` (`map_task_to_equipment(item, manifest) -> Choice` with fallback), `models.py` (frozen `ChecklistItem`, `Choice`). `__init__.py` re-exports.
- `dummyindex/skills/build/SKILL.md` — `name: dummyindex-build`. Orchestration loop: read `spec.md` → loop: `build --next` → dispatch the mapped agent (Task tool) grounded in `.context/` + spec/plan, **verify**, `build --check` → repeat until `--status` is all-done → run `rebuild --changed`. Embed §0.4 (verify-before-tick, stop-on-block).
- `tests/context/test_build_loop.py` — checklist parse/flip idempotency; mapping picks by capability + falls back; `--status` counts; all-done prints re-index hint.
- `INTEGRATION.md` — registrations.

**Acceptance / checklist (C):**
- [ ] `build --proposal S --next` prints the first unchecked item + a mapped equipment choice (or fallback) + grounding paths.
- [ ] `build --proposal S --check "<item>"` flips exactly that item to `- [x]`, atomically; idempotent.
- [ ] `build --proposal S --status` reports done/total and, when complete, prints `dummyindex context rebuild --changed`.
- [ ] Mapping falls back to `general-purpose` when no capability matches.
- [ ] `skills/build/SKILL.md` encodes the verify-before-tick loop + final re-index.
- [ ] `uv run pytest tests/context/test_build_loop.py -q` passes; whole `tests/context` suite green.
- [ ] `INTEGRATION.md` lists registrations.

---

## Integration pass (orchestrator, after the 3 agents)
1. Merge the three worktrees' NEW files onto `main`.
2. Apply ALL registrations once from the three `INTEGRATION.md` files: `ContextSubcommand` members (`PROPOSE`,`EQUIP`,`BUILD`), `_HANDLERS` entries + imports, `_usage.py` blocks, `__main__.install()` copy blocks for the 3 new skills (each its own top-level skill dir) + `pyproject.toml` package-data globs (`skills/plan/*.md`, `skills/equip/**`, `skills/build/*.md`), `skills/skill.md` pointer.
3. `uv run pytest -q` green.
4. **End-to-end proof on one tiny feature:** `propose` a trivial feature → `equip` → walk `build` to all-done → confirm `rebuild --changed` runs. Stop and ask the user on any collision (e.g., path or semantic conflict), per the session-memory precedent.
