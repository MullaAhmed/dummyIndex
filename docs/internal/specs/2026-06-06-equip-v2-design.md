# Equip v2 — codified, evolving toolkit engine

**Date:** 2026-06-06
**Status:** Approved design → implementation
**Supersedes:** the Slice-B MVP section of the build-loop slices spec (templates-first thin slice). Foundation stays; this deepens it.
**Parent:** build-loop overview (plan → equip → execute).

## 0. Directives (owner-set, non-negotiable)

1. **B lives in code.** Every *decision* — what to detect, generate, adopt, wire, refresh, retire — is deterministic Python in `dummyindex/context/domains/equip/`. No agent judgment inside the CLI path.
2. **Dispatch is always through skills.** Python never spawns/invokes agents. Skills (markdown) are the only dispatch layer; the CLI emits *pointers* (`subagent_type`, grounding paths) for skills to act on.
3. **Full-fledged dev tool, not MVP.** Complete lifecycle, complete safety, complete tests.
4. **Evolving agent builder** (Hermes-derived, see §7): generated tooling is versioned, hash-baselined, patchable, and improves from build-run learnings — without ever stomping user edits.

## 1. Pipeline

```
detect → catalog → render | adopt → apply (files + settings hooks) → manifest (v2)
   lifecycle: status | refresh | reset | uninstall      evolution: patch
```

## 2. Detection — `detect.py` (extend)

`StackProfile` grows into a toolchain profile (all frozen, tuple fields):

```python
@dataclass(frozen=True)
class StackProfile:
    label: str                      # "python" | "node" | ... | "generic"
    frameworks: tuple[str, ...]
    formatter: str | None           # "ruff" | "black" | "prettier"
    format_command: str | None      # 'ruff format "$CLAUDE_FILE_PATHS"' ...
    test_runner: str | None         # "pytest" | "jest" | "vitest" | "go test" | "cargo test"
    test_command: str | None        # "uv run pytest -q" | "npx jest" | ...
    linter: str | None              # "ruff" | "eslint"
    lint_command: str | None
    type_checker: str | None        # "mypy" | "pyright" | "tsc"
    typecheck_command: str | None
```

Same token-table style as today (raw substring over manifests; no TOML/JSON parsing). `uv.lock`/`uv` in pyproject ⇒ prefix python commands with `uv run`. Missing map/manifests degrade to `generic` with `None` commands — equip still works on a fresh repo.

## 3. Catalog — `catalog.py` (new; the policy core)

```python
def build_catalog(
    *, profile: StackProfile, conventions: tuple[str, ...],
    preflight: PreflightReport, proposal_capabilities: tuple[str, ...] = (),
) -> CatalogDecision
```

`CatalogDecision` (frozen): `generate: tuple[GenerateSpec, ...]`, `adopt: tuple[AdoptSpec, ...]`, `hooks: tuple[HookSpec, ...]`.

Standard generated set (always): `<stack>-implementer`, `<stack>-tester`, `<proj>-reviewer` agents + `<proj>-verify` skill. Hook set: PostToolUse format hook iff `format_command` detected. Adoption set: registry specialists covering capability gaps (§4), plus whatever `proposal_capabilities` (§6) demands. Pure function; fully unit-testable.

## 4. Adoption — `adopt.py` (new)

Sources, in order:
1. **Project agents** — `preflight.project_agents` (file stems under `.claude/agents/`); capabilities inferred from the stem via the same keyword table used everywhere (`security` → security, `db|data` → database, …); `subagent_type` = the stem.
2. **Known-specialist registry** — `dummyindex.context.domains.dev_pick.SubagentType` members (Backend Architect, Frontend Developer, Data Engineer, AI Engineer, Senior Developer, …) with a fixed capability map (e.g. Data Engineer → `("database", "data")`, Security Engineer → `("security", "review")`). Registry agents have no project file: `path=""`, `source="installed"`.

Adopted items are manifest records only — adoption never writes files.

## 5. Hook wiring — `hookwire.py` (new) + shared `claude_settings.py` (refactor)

Extract the proven machinery from `context/hooks.py` into `dummyindex/context/claude_settings.py`:
`load_settings` (preserve-or-refuse, `MalformedSettingsError`), `install_hook_entry(settings_path, event, hook_body, sentinel)` (idempotent, refresh-in-place by sentinel), `remove_hook_entries(settings_path, sentinel)`, atomic `_write_json`. `hooks.py` becomes a thin consumer (behavior identical; its tests must stay green unmodified except imports).

Equip's sentinel: **`DUMMYINDEX_EQUIP`** (distinct from `DUMMYINDEX_AUTO_REFRESH`). v2 *writes* the PostToolUse format hook:

```jsonc
{ "matcher": "Write|Edit",
  "hooks": [{ "type": "command",
    "command": "# DUMMYINDEX_EQUIP\ncommand -v ruff >/dev/null 2>&1 || exit 0\nruff format \"$CLAUDE_FILE_PATHS\" 2>/dev/null || true\nexit 0\n" }] }
```

(command built from `profile.format_command`; guard binary = formatter name). Unparseable settings ⇒ refuse + report, never overwrite (existing discipline).

## 6. Per-proposal scoping

`equip --for-proposal S` reads `proposals/S/plan.md` + `checklist.md` text, extracts capability keywords via a fixed table (`database|migration|sql` → database; `security|auth|secret` → security; `frontend|ui|css|react` → frontend; `performance|optimi` → performance; `docs|documentation` → docs), and passes them to `build_catalog` as `proposal_capabilities`. Coverage rule: **adopt before generate**; a capability no registry/project agent covers falls back to the generic implementer (no speculative templates).

## 7. Evolution mechanics (Hermes-derived)

**Origin-hash baselines** (Hermes `.bundled_manifest`: *"unchanged → safe to pull upstream; changed → user-modified, skipped forever"*):
- On every generated write: `origin_hash = sha256(content)` recorded in the manifest.
- State fn: `classify(item) → PRISTINE (disk hash == origin) | USER_MODIFIED (≠) | MISSING`.
- `refresh` re-renders only PRISTINE items whose fresh render differs (then re-baselines + bumps version). USER_MODIFIED is skipped forever.
- `uninstall` removes PRISTINE files + our `DUMMYINDEX_EQUIP` hook entries + the manifest; USER_MODIFIED files are skipped + reported.
- `reset NAME` restores the pristine render of one item and re-baselines (the explicit escape hatch).
- The in-body sentinel comment stays as a human-visible marker; **the hash is the authority**.

**Patch seam** (Hermes `patch`: old/new replacement, *"preferred — more token-efficient than edit"*):
- `equip patch --item NAME --from-file F` where F is JSON `{"old": "...", "new": "..."}`; the old string must match exactly once.
- Applying a patch via the CLI = sanctioned evolution: write atomically, **re-baseline origin_hash**, bump `version:` (patch-level), update manifest. Hand edits (not via CLI) stay USER_MODIFIED.

**Learning triggers** (Hermes skill-creation triggers, verbatim adopted): the **build skill** runs a post-build learning step — after a complex task succeeds, after an error→working-path discovery, or after a user correction, it drafts the minimal old/new patch for the relevant generated agent/skill and applies it via `equip patch`. Judgment in markdown; mechanics in Python.

**Versioned artifacts:** generated frontmatter carries `version: 1.0.0`; refresh bumps minor, patch bumps patch-level; manifest mirrors it.

**Progressive disclosure** (Hermes 3-level loading): `equipment.json` is the lean index (level 0); `build --next` emits pointers, never content (level 1); templates ground by **pointing into `.context/`**, never pasting it (level 2).

## 8. Manifest schema v2

```jsonc
{ "schema_version": 2, "items": [{
    "kind": "agent|skill|command|hook",
    "name": "python-implementer",
    "path": ".claude/agents/python-implementer.md",   // "" for adopted registry agents
    "source": "generated|installed",
    "subagent_type": "python-implementer",            // null for skills/hooks
    "capabilities": ["implement"],
    "grounded_in": [".context/HOW_TO_USE.md", "..."],
    "version": "1.0.0",                               // generated only (null otherwise)
    "origin_hash": "sha256:..."                       // generated only (null otherwise)
}]}
```

`from_dict` tolerates v1 manifests (missing fields → `None`/defaults). C's loader already tolerates extra fields.

## 9. CLI surface (wire-only)

```
dummyindex context equip [apply] [path] [--root DIR] [--dry-run] [--for-proposal S] [--json]
dummyindex context equip status   [--root DIR] [--json]
dummyindex context equip refresh  [--root DIR] [--dry-run]
dummyindex context equip reset NAME [--root DIR]
dummyindex context equip uninstall [--root DIR] [--dry-run]
dummyindex context equip patch --item NAME --from-file F [--root DIR]
```

Default verb `apply` (back-compat with bare `equip`). Exit codes 0/2/1 per convention.

## 10. C passthrough (small)

`Choice` gains `subagent_type: str | None`; `build --next` (text + `--json`) emits it (fallback ⇒ `general-purpose`). The **build skill** dispatches via that field. No other C changes.

## 11. Skills (markdown)

- `skills/equip/SKILL.md`: present richer toolkit + lifecycle verbs; safety framing; never run patch/refresh without showing the diff intent.
- `skills/build/SKILL.md`: dispatch via `subagent_type`; **post-build learning step** with the three Hermes triggers → `equip patch`.
- Templates (4): implementer (framework slot), tester (embeds `test_command`), reviewer (grounded in `.context/conventions/` + feature `concerns.md`), verify skill (embeds test/lint/typecheck commands). All carry `version:` frontmatter, sentinel comment in body, grounding pointers, and the checklist/spec-led discipline.

## 12. Testing (≥ existing bar)

- detect: toolchain table coverage incl. uv-prefix, degrade-to-generic.
- catalog: standard set, hook iff formatter, proposal-capability coverage, adopt-before-generate.
- adopt: project-agent inference, registry map, no file writes.
- claude_settings refactor: `hooks.py` behavior unchanged (existing tests green); equip hook installs additively; user hooks preserved; malformed settings refused; both sentinels coexist + uninstall independently.
- lifecycle: pristine/user-modified/missing classification; refresh skips user-modified; reset re-baselines; uninstall removes only ours.
- patch: exact-once match enforced; re-baseline + version bump; manifest sync.
- manifest: v1 → v2 tolerant load, round-trip.
- e2e: fresh repo → ingest → propose → equip (full set + hook in settings.json) → hand-edit one artifact → status shows USER_MODIFIED → refresh skips it → patch another via CLI → status PRISTINE w/ bumped version → build --next emits subagent_type → uninstall leaves the user-modified file + user hooks.

## 13. Non-goals (this iteration)

Remote/hub registries and skill marketplaces; security-scanning of adopted tooling; auto-learning without the build skill in the loop; multi-repo equipment.
