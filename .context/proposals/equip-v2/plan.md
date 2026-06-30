# Equip v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `dummyindex context equip` from the templates-first MVP into the full codified, evolving toolkit engine specified in `docs/specs/2026-06-06-equip-v2-design.md`.

**Architecture:** All policy in deterministic Python under `dummyindex/context/domains/equip/` (detect → catalog → render|adopt → apply → manifest v2), with Hermes-derived evolution mechanics (origin-hash baselines, patch seam, versioned artifacts). Skills remain the only dispatch layer. Settings-hook machinery is extracted from `context/hooks.py` into a shared `context/claude_settings.py` consumed by both.

**Tech Stack:** Python 3.10+ stdlib (`hashlib`, `json`, `re`), pytest via `uv run pytest`, existing dummyindex conventions (`docs/CONVENTIONS.md`).

**Spec:** `docs/specs/2026-06-06-equip-v2-design.md` — **read it first; schemas/signatures there are normative.** Where this plan and the spec disagree, the spec wins.

**Conventions guardrails:** frozen dataclasses w/ `tuple[...]`; fixed alphabets are `(str, Enum)` in `<area>/enums.py`; constants in `<area>/_constants.py`; typed errors; no `print` in domains; atomic writes via `dummyindex.context.domains._io.write_text_atomic`; CLI wire-only (0/2/1); tests mirror layout, bare asserts. Commit per task with `WIP:` prefix; final integration commit drops the prefix convention used by main commits.

---

## File structure (locked)

**Create**
- `dummyindex/context/claude_settings.py` — shared settings.json machinery (extracted from hooks.py).
- `dummyindex/context/domains/equip/catalog.py` — `build_catalog` policy core (+ `CatalogDecision`, `GenerateSpec`, `AdoptSpec`, `HookSpec` in models.py).
- `dummyindex/context/domains/equip/adopt.py` — project-agent + registry adoption.
- `dummyindex/context/domains/equip/hookwire.py` — equip's PostToolUse format hook via claude_settings.
- `dummyindex/context/domains/equip/lifecycle.py` — classify/status/refresh/reset/uninstall.
- `dummyindex/context/domains/equip/evolve.py` — `apply_patch` (exact-once old/new, re-baseline, version bump).
- `dummyindex/context/domains/equip/_hash.py` — `content_hash(text) -> "sha256:..."`.
- `dummyindex/skills/equip/templates/tester-agent.md.tmpl`, `reviewer-agent.md.tmpl`.
- `tests/context/test_equip_catalog.py`, `test_equip_adopt.py`, `test_equip_lifecycle.py`, `test_equip_evolve.py`, `test_claude_settings.py`, `test_equip_e2e.py`.

**Modify**
- `dummyindex/context/domains/equip/{models,enums,detect,render,manifest,plan,safety,_constants,__init__}.py` — per spec §2/§3/§8 (StackProfile toolchain fields; EquipmentItem `subagent_type`/`version`/`origin_hash`; schema v2 tolerant load; template slots; version frontmatter).
- `dummyindex/context/hooks.py` — consume claude_settings (no behavior change).
- `dummyindex/cli/equip.py` — verb dispatch `apply|status|refresh|reset|uninstall|patch` (default apply), `--for-proposal`, `--json`, `--dry-run`.
- `dummyindex/context/domains/buildloop/{models,mapping}.py` + `dummyindex/cli/build_loop.py` — `Choice.subagent_type` passthrough.
- `dummyindex/skills/equip/SKILL.md`, `dummyindex/skills/build/SKILL.md`, `dummyindex/skills/equip/templates/{implementer-agent,verify-skill}.md.tmpl`.
- `dummyindex/cli/_usage.py` — equip verb docs.
- `tests/context/{test_equip,test_build_loop,test_hooks}.py` — extend.

---

## Phase 1 — Domain (Tasks 1–8)

### Task 1: Extract `claude_settings.py`; hooks.py consumes it
**Files:** Create `dummyindex/context/claude_settings.py`; Modify `dummyindex/context/hooks.py`; Test `tests/context/test_claude_settings.py`.
- [ ] Write failing tests: `install_hook_entry` adds an entry under an event; idempotent re-install; refresh-in-place when body changes (same sentinel); `MalformedSettingsError` on bad JSON / non-object (file untouched); `remove_hook_entries` strips only the given sentinel, preserves user entries + other sentinels; atomic write (no `.tmp`残留).
```python
def test_install_then_remove_by_sentinel(tmp_path):
    sp = tmp_path / ".claude" / "settings.json"
    body = {"matcher": "*", "hooks": [{"type": "command", "command": "# S1\necho hi\n"}]}
    assert install_hook_entry(sp, "PostToolUse", body, sentinel="S1") is True
    assert install_hook_entry(sp, "PostToolUse", body, sentinel="S1") is False  # idempotent
    sp_data = json.loads(sp.read_text(encoding="utf-8"))
    sp_data["hooks"]["PostToolUse"].append({"hooks": [{"type": "command", "command": "user-own"}]})
    sp.write_text(json.dumps(sp_data), encoding="utf-8")
    removed = remove_hook_entries(sp, sentinel="S1")
    assert removed == ["PostToolUse"]
    left = json.loads(sp.read_text(encoding="utf-8"))
    assert any("user-own" in h["command"] for e in left["hooks"]["PostToolUse"] for h in e["hooks"])
```
- [ ] Run → FAIL (module missing). Implement: lift `_load_settings`/`MalformedSettingsError`/`_write_json`/`_install_claude_hook`-equivalent from `hooks.py` verbatim into public `load_settings`, `install_hook_entry(settings_path, event, hook_body, *, sentinel) -> bool`, `remove_hook_entries(settings_path, *, sentinel) -> list[str]`, `write_settings`. Rewire `hooks.py` to import these (keep its public API + SENTINEL unchanged).
- [ ] Run: `uv run pytest tests/context/test_claude_settings.py tests/context/test_hooks.py -q` → PASS, **hooks tests unmodified**.
- [ ] Commit `WIP: extract shared claude_settings machinery`.

### Task 2: Manifest schema v2 + `_hash.py`
**Files:** Modify `equip/models.py`, `equip/enums.py` (none needed), `equip/manifest.py`, `equip/_constants.py`; Create `equip/_hash.py`; Test extend `tests/context/test_equip.py`.
- [ ] Failing tests: `EquipmentItem` round-trips `subagent_type/version/origin_hash`; v1 dict (missing new keys) loads with `None`s; `SCHEMA_VERSION == 2`; `content_hash("x")` is stable + `sha256:`-prefixed.
- [ ] Implement per spec §8: optional fields `subagent_type: str | None = None`, `version: str | None = None`, `origin_hash: str | None = None` (frozen, after required fields); `_hash.content_hash` = `"sha256:" + hashlib.sha256(text.encode()).hexdigest()`; bump `_constants.SCHEMA_VERSION = 2`; `from_dict` uses `.get(...)`.
- [ ] Run targeted + `tests/context/test_equip.py` → PASS. Commit `WIP: manifest v2 + content hashing`.

### Task 3: Toolchain detection
**Files:** Modify `equip/detect.py`, `equip/models.py`; Test extend `tests/context/test_equip.py` (or new section).
- [ ] Failing tests: pyproject with `pytest`+`mypy`+`ruff`+`uv.lock` ⇒ `test_command == "uv run pytest -q"`, `lint_command == "ruff check ."`, `typecheck_command == "mypy ."`, `format_command == 'ruff format "$CLAUDE_FILE_PATHS"'`; package.json with `jest`+`prettier`+`eslint` ⇒ npm-family commands (`npx jest`, `npx eslint .`, `npx prettier --write "$CLAUDE_FILE_PATHS"`); empty repo ⇒ all `None`, label `generic`.
- [ ] Implement per spec §2: extend `StackProfile` (frozen) with the 8 toolchain fields; token tables `_TEST_TOKENS`/`_LINT_TOKENS`/`_TYPECHECK_TOKENS` mirroring `_FORMATTER_TOKENS` style; `uv.lock` presence (or `[tool.uv]`) prefixes python commands with `uv run`. Update existing constructor call sites/tests.
- [ ] PASS → Commit `WIP: toolchain detection (test/lint/typecheck/format commands)`.

### Task 4: Adoption
**Files:** Create `equip/adopt.py`; Modify `equip/models.py` (AdoptSpec if placed here), `equip/__init__.py`; Test `tests/context/test_equip_adopt.py`.
- [ ] Failing tests: registry map covers every `dev_pick.SubagentType` member with non-empty capabilities; `adopt_existing(preflight, needed=("security",))` returns a `Security Engineer`-typed item *iff* the registry names one, with `source=INSTALLED`, `path==""`; a preflight `project_agents=("db-helper",)` yields an adopted item with `subagent_type=="db-helper"` and `"database"` in capabilities; **no filesystem writes** (function is pure over inputs).
- [ ] Implement per spec §4: `_REGISTRY_CAPABILITIES: dict[SubagentType, tuple[str, ...]]`; `_infer_capabilities(stem) -> tuple[str, ...]` via the shared keyword table (define `_CAPABILITY_TOKENS` in `equip/_constants.py`: database/security/frontend/performance/docs/test/review/implement); `adopt_existing(*, preflight: PreflightReport, needed: tuple[str, ...]) -> tuple[EquipmentItem, ...]` — project agents first, registry fills remaining gaps, each capability adopted at most once.
- [ ] PASS → Commit `WIP: adopt existing project/registry specialists`.

### Task 5: Catalog policy core
**Files:** Create `equip/catalog.py`; Modify `equip/models.py` (`GenerateSpec(name, kind, template, capabilities, rel_path)`, `HookSpec(name, event, matcher, command)`, `CatalogDecision(generate, adopt, hooks)` — all frozen), `equip/__init__.py`; Test `tests/context/test_equip_catalog.py`.
- [ ] Failing tests: python profile ⇒ 3 agents + 1 skill generated, format hook present; profile w/o formatter ⇒ no hooks; `proposal_capabilities=("database",)` ⇒ adopt list includes a database specialist (adopt-before-generate: no new template); unknown capability `("blockchain",)` ⇒ no crash, no extra generation (generic implementer already covers).
- [ ] Implement per spec §3+§6: pure `build_catalog(*, profile, conventions, preflight, proposal_capabilities=()) -> CatalogDecision`. Standard set names: `{label}-implementer/tester`, `{proj}-reviewer`, `{proj}-verify`. Hook command per spec §5 template using `profile.format_command` + formatter binary guard.
- [ ] PASS → Commit `WIP: catalog policy core`.

### Task 6: Templates + render v2
**Files:** Create `templates/tester-agent.md.tmpl`, `templates/reviewer-agent.md.tmpl`; Modify `templates/implementer-agent.md.tmpl`, `templates/verify-skill.md.tmpl`, `equip/render.py`; Test extend `tests/context/test_equip.py`.
- [ ] Failing tests: rendered tester contains the literal `test_command`; reviewer references `.context/conventions/` and `concerns.md`; every rendered artifact starts with YAML frontmatter containing `version: 1.0.0` and (in body) the `DUMMYINDEX_EQUIP`-marked generated-by comment; no `{{` left after render.
- [ ] Implement: new slots `{{test_command}}`, `{{lint_command}}`, `{{typecheck_command}}`, `{{framework}}`; `render.py` gains the two template constants + slot map; keep frontmatter at byte 0 (regression from B-MVP). Templates ground by **pointing** at `.context/` paths (spec §7 progressive disclosure) and embed the verify-before-tick discipline.
- [ ] PASS → Commit `WIP: standard template set w/ toolchain slots + version frontmatter`.

### Task 7: Lifecycle (status/refresh/reset/uninstall) on origin-hash
**Files:** Create `equip/lifecycle.py`; Modify `equip/plan.py` (record `origin_hash`+`version` on build), `equip/safety.py` (hash-aware), `equip/__init__.py`; Test `tests/context/test_equip_lifecycle.py`.
- [ ] Failing tests:
```python
def test_classify_and_refresh_respect_user_edits(tmp_path):
    root = _equipped_fixture(tmp_path)             # helper: apply a 2-item toolkit
    target = root / ".claude" / "agents" / "python-implementer.md"
    assert classify_item(root, _item(root, "python-implementer")) is ItemState.PRISTINE
    target.write_text(target.read_text() + "\nuser tweak\n", encoding="utf-8")
    assert classify_item(root, _item(root, "python-implementer")) is ItemState.USER_MODIFIED
    report = refresh(root, fresh_renders=_renders(root))
    assert "python-implementer" in report.skipped_user_modified
def test_reset_rebaselines(tmp_path): ...          # reset → PRISTINE again, version minor-bumped
def test_uninstall_only_ours(tmp_path): ...        # user-modified file survives; pristine + hook entry + manifest removed
```
- [ ] Implement per spec §7: `ItemState(str, Enum)` PRISTINE/USER_MODIFIED/MISSING in `equip/enums.py`; `classify_item`, `status(...) -> StatusReport`, `refresh(...) -> RefreshReport` (re-render PRISTINE-and-stale only, re-baseline + minor bump), `reset(root, manifest, name)`, `uninstall(root, manifest) -> UninstallReport` (files PRISTINE-only + `remove_hook_entries(sentinel="DUMMYINDEX_EQUIP")` + delete manifest). All frozen report dataclasses; no prints.
- [ ] PASS → Commit `WIP: hash-baselined lifecycle`.

### Task 8: Patch seam
**Files:** Create `equip/evolve.py`; Modify `equip/errors.py` (`PatchError(EquipError)`), `equip/__init__.py`; Test `tests/context/test_equip_evolve.py`.
- [ ] Failing tests: exact-once replacement applied atomically; zero matches ⇒ `PatchError`; two matches ⇒ `PatchError`; after patch `origin_hash` re-baselined (classify ⇒ PRISTINE) and `version` patch-bumped `1.0.0→1.0.1`; manifest persisted.
- [ ] Implement per spec §7: `apply_patch(*, root: Path, manifest: EquipmentManifest, name: str, old: str, new: str) -> EquipmentItem` (count occurrences, replace, `write_text_atomic`, new hash, `_bump(version, "patch")`, `dataclasses.replace`, write manifest). `_bump(v, level)` helper handles minor/patch.
- [ ] PASS → Commit `WIP: equip patch evolution seam`.

## Phase 2 — Surface (Tasks 9–12)

### Task 9: Hookwire + apply pipeline
**Files:** Create `equip/hookwire.py`; Modify `cli/equip.py` (apply path uses catalog+adopt+hookwire+baselines); Test extend `tests/context/test_equip.py` + `tests/context/test_claude_settings.py`.
- [ ] Failing tests: apply on a python fixture writes the PostToolUse entry with `DUMMYINDEX_EQUIP` sentinel into `.claude/settings.json`; pre-existing user PostToolUse entry preserved; `DUMMYINDEX_AUTO_REFRESH` SessionStart entry untouched; malformed settings ⇒ hook skipped + reported, files still written; `--dry-run` writes neither files nor settings; manifest items carry `origin_hash`/`version`/`subagent_type`.
- [ ] Implement: `wire_hooks(settings_path, hooks: tuple[HookSpec, ...]) -> tuple[str, ...]` via `install_hook_entry(..., sentinel=EQUIP_SENTINEL)`; `EQUIP_SENTINEL = "DUMMYINDEX_EQUIP"` in `_constants.py`. CLI apply: detect → preflight → (proposal caps via §6 extractor in `equip/catalog.py` or `equip/_proposal.py`) → `build_catalog` → render+write (safety: skip non-ours) → adopt → wire hooks → manifest v2.
- [ ] PASS → Commit `WIP: hook wiring + v2 apply pipeline`.

### Task 10: CLI verbs
**Files:** Modify `dummyindex/cli/equip.py`, `dummyindex/cli/_usage.py`; Test extend `tests/context/test_equip.py`.
- [ ] Failing tests (via `dispatch(["equip", ...])`): bare `equip` == `equip apply`; `equip status --json` payload has per-item `state`; `equip refresh --dry-run` lists-but-skips; `equip reset python-implementer` restores; `equip uninstall` leaves user-modified + reports; `equip patch --item X --from-file f.json` applies; unknown verb ⇒ 2; `--for-proposal missing-slug` ⇒ 2 with message. Local flag parsing (NOT `_parse_path_and_root` — same `--status`-style collision class as build_loop; reuse its `_pull_flag_value` pattern locally).
- [ ] Implement verb table as `(str, Enum)` `EquipVerb` in `equip/enums.py`; wire-only handlers calling the domain; `_usage.py` block updated to the §9 surface.
- [ ] PASS → Commit `WIP: equip verb surface`.

### Task 11: C passthrough (`subagent_type`)
**Files:** Modify `domains/buildloop/models.py` (`Choice.subagent_type: str | None = None`), `domains/buildloop/mapping.py` (thread item's `subagent_type` or None), `cli/build_loop.py` (`--next` emits `subagent_type`, text + json; fallback ⇒ `"general-purpose"`); Test extend `tests/context/test_build_loop.py`.
- [ ] Failing test: equipment item `{"name":"db-specialist","subagent_type":"Data Engineer","capabilities":["database"]}` ⇒ `--next --json` payload `subagent_type == "Data Engineer"`; fallback case ⇒ `"general-purpose"`.
- [ ] Implement minimal threading. PASS → Commit `WIP: build --next emits subagent_type`.

### Task 12: Skills + e2e
**Files:** Modify `skills/equip/SKILL.md`, `skills/build/SKILL.md`; Create `tests/context/test_equip_e2e.py`.
- [ ] Update equip SKILL.md: lifecycle verbs walkthrough, safety framing (always `--dry-run`/`status` first, show intent before `patch`/`refresh`). Update build SKILL.md: dispatch via `subagent_type` from `--next`; **post-build learning step** with the three Hermes triggers (complex-task success / error→working-path / user correction) → draft minimal old/new → `dummyindex context equip patch --item NAME --from-file <tmp>.json`.
- [ ] e2e test (single integration test, tmp repo): build_all → apply → assert files+hook+manifest → hand-edit one agent → status USER_MODIFIED → refresh skips → patch another via `_cmd_equip(["patch", ...])` → PRISTINE + `1.0.1` → uninstall → user-modified file remains, user hook remains, ours gone.
- [ ] `uv run pytest -q` full suite green. Commit `WIP: skills + e2e`.

## Phase 3 — Review + validation (Task 13)
- [ ] `python-reviewer` agent over the diff; fix BLOCK/HIGH; re-run suite.
- [ ] Live smoke on `/home/ahmed/.claude/jobs/f87b88de/tmp/bl-e2e` (or recreate): apply → status → hand-edit → refresh → patch → uninstall, eyeballing output.
- [ ] Squash-free final commit on main (drop WIP wording in the last message): `feat(equip): v2 — codified evolving toolkit engine (catalog, adopt, hookwire, hash lifecycle, patch seam)`.
- [ ] Update `dummyindex/skills/skill.md` equip bullet (lifecycle + evolution one-liner) + memory note.

## Self-review (done)
**Spec coverage:** §2→T3, §3→T5, §4→T4, §5→T1+T9, §6→T5+T9/T10, §7→T2+T6+T7+T8+T12(skill), §8→T2, §9→T10, §10→T11, §11→T12, §12→all test steps + T12 e2e, refactor-no-behavior-change→T1. ✓
**Placeholders:** none — every step names exact files/behaviors; test bodies given where novel (T1, T7, T11), table-driven ones described precisely. ✓
**Type consistency:** `ItemState`/`classify_item`/`refresh`/`reset`/`uninstall` (T7) match T10's CLI calls; `Choice.subagent_type` (T11) matches T9's manifest field (T2); `EQUIP_SENTINEL` defined T9, used T7-uninstall via shared constant. ✓
