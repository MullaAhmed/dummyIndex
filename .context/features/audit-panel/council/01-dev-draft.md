# Audit panel & onboarding — plan
confidence: INFERRED

## Where it lives

- `dummyindex/context/domains/audit/` — the audit-panel domain: `workspace.py` (scaffold + slug + model/mode resolution), `catalog.py` (persona parse + roster resolution), `models.py` (frozen dataclasses), `enums.py` (`LogStatus`, `MAX_REBUTTAL_ROUNDS`), `errors.py` (typed hierarchy), `log.py` (debate resumption log), `__init__.py` (public surface re-export, `__init__.py:67-101`).
- `dummyindex/context/domains/config.py` — `Config` dataclass + `read_config`/`write_config`/`default_config`; the shared `ModelChoice`/`CouncilMode`/`ScopeKind` alphabet the audit domain imports (`enums.py:1-8`, `workspace.py:23`).
- `dummyindex/cli/onboard.py` — the thin `onboard` CLI handler; dispatched as `ContextSubcommand.ONBOARD` (`cli/__init__.py:111`).
- `dummyindex/skills/audit/agents/*.md` — eight shipped persona files the catalog parses (`catalog.py:56-62`).
- `dummyindex/installer/install.py:326` — `_write_default_config` seeds a config at install time so `resolve_model` has a fallback.

## Architecture in three sentences

The audit domain is **deterministic plumbing only**: it scaffolds an on-disk workspace, parses a persona menu, and resolves personas onto the repo's real agents, but never runs the audit itself — the `/dummyindex-audit` skill orchestrates the panel and rebuttal loop, capped by `MAX_REBUTTAL_ROUNDS` and resumed via the debate log (`workspace.py:1-13`, `log.py:1-25`). Every artifact is a frozen dataclass with a `schema_version` and `to_dict()`, written tmp+`replace` through `write_text_atomic` per the data-access convention (`models.py:36-45`, `workspace.py:175-192`). Onboarding/config is the same shape — a frozen `Config` persisted atomically — and supplies the model/mode the audit domain falls back to, binding the two halves into one community via the shared `ModelChoice`/`CouncilMode` alphabet (`config.py:50-64`, `workspace.py:99-128`).

## Data model

### Audit workspace `.context/audits/<slug>/`
- `audit.json` — `AuditConfig.to_dict()`: `{schema_version:1, slug, description, mode, model, scope:[...], max_rounds:3}` (`models.py:36-45`). `from_dict` rejects a wrong `schema_version` and a missing `model` — the model is never silently defaulted, even on load (`models.py:48-65`).
- `description.md` — request + scope + settings brief (`workspace.py:221-239`).
- `catalog.json` — list of `PersonaCard.to_dict()`: `{persona_id, name, role, emoji, subagent_type, triggers:[...], description, requested_subagent_type}` (`models.py:93-103`).
- `findings/` — empty dir; per-persona markdown the agents author (`workspace.py:163`).
- `_debate-log.json` — `{schema_version:1, slug, entries:[{timestamp, round, persona, status, note}]}`; statuses `started|complete|failed|skipped` (`log.py:14-58`, `enums.py:19-34`).

### `.context/config.json`
Frozen `Config`: `{schema_version:1, scope, scope_path, mode, model, auto_refresh_hook, external_docs:[], reconcile_exclude:[], wire_superpowers}` (`config.py:100-111`). Cross-field invariant: `scope==subdir` requires `scope_path` (`config.py:95-98`). `from_dict` validates every enum, rejects non-bool flags, and rejects `bool` masquerading as `schema_version` (`config.py:113-161`).

## Key decisions

- **Deterministic plumbing; the orchestrator drives the panel.** No matching/selection logic in Python — panel choice and convergence are the skill's (LLM's) judgment; the catalog is just a menu (`catalog.py:5-9`, `log.py:10-13`).
- **Model never silently defaulted.** `resolve_model` and `AuditConfig.from_dict` both fail loud rather than assume one; `resolve_mode` *may* default to `standard` — only the model is the never-silent field (`workspace.py:85-128`, `models.py:54-57`).
- **Roster resolution is evidence-gated.** `collect_roster` returns `None` when neither `.claude/agents/` nor `equipment.json` exists, and `resolve_catalog(None)` is the identity — a bare repo never downgrades a persona to `general-purpose` on absent evidence (`catalog.py:111-118`, `171-172`). A corrupt `equipment.json` degrades to the agents-dir reading, not a crash (`catalog.py:126-130`).
- **Atomic, byte-stable writes.** All artifacts go through `write_text_atomic` / tmp+`replace`, sorted/deterministic JSON, repo-relative paths — per the data-access convention.
- **Audit runs without a `.context/` index.** Unlike council/propose, an on-demand audit grounds only in conventions + feature docs *if they exist* (`workspace.py:10-12`).
- **Marketplace plugins excluded from the roster** — legacy schema-v3 manifests recorded plugins with `kind=agent`, so `collect_roster` guards on `EquipmentSource.MARKETPLACE` to keep a plugin name out of the dispatch roster (`catalog.py:133-138`).

## Open questions

- **Two concerns in one community.** The Leiden clustering grouped the audit-panel domain and onboarding/config together, but they read as **two distinct concerns** joined only by the shared `ModelChoice`/`CouncilMode` alphabet and the model/mode fallback (`workspace.py:99-127`). Onboarding/config is also consumed far beyond audit (council, equip, drift hook). Flag for the architect: consider whether config warrants its own feature doc, with audit-panel citing it as a dependency rather than a co-member.
- The interactive 5-question onboarding flow lives in the `/dummyindex` skill, not in `onboard.py` (`onboard.py:3-5`) — the Python side is persistence only; the question wording is unverifiable from source.
- `report.md` and per-persona `findings/*.md` are authored by agents at runtime; their schema is convention in the persona markdown, not enforced by Python.
