# Audit panel & onboarding — plan
confidence: INFERRED

## Bounded context

This feature is **two bounded contexts** the Leiden pass fused into one community, joined only by a shared vocabulary — not a shared responsibility:

1. **Audit panel** (`context/domains/audit/`) — deterministic plumbing for the on-demand argue-and-audit panel: scaffold a workspace, parse a persona menu, resolve personas onto the repo's real agents, journal debate progress. It owns its data (`models.py`, `enums.py`), its errors (`errors.py`), and its on-disk output (`.context/audits/<slug>/`).
2. **Onboarding & config** (`cli/onboard.py` + `context/domains/config.py`) — persist council preferences to `.context/config.json`. This is a **platform primitive**, not an audit concern: it is read by council, equip, the drift hook, *and* audit. Audit is one downstream consumer among several.

The seam between them is exactly two facts: the shared `ModelChoice`/`CouncilMode`/`ScopeKind` enum alphabet (defined in `config.py:42-64`, imported by audit via `enums.py:1-8` and `workspace.py:23`) and the model/mode fallback (`resolve_model`/`resolve_mode` read `config.json` when no flag is given, `workspace.py:85-128`). See **Open questions** — this fusion is flagged for split.

## Where it lives

- `dummyindex/context/domains/audit/` — the audit domain:
  - `workspace.py` — scaffold + slug + model/mode resolution (`validate_slug:48`, `slugify:64`, `resolve_model:85`, `resolve_mode:108`, `ensure_audit:131`, `read_audit:204`).
  - `catalog.py` — persona parse + roster resolution (`load_catalog:65`, `parse_persona:79`, `collect_roster:98`, `resolve_catalog:159`).
  - `models.py` — frozen dataclasses (`AuditConfig:22`, `PersonaCard:69`, `AuditStart:107`).
  - `enums.py` — `LogStatus:19`, `MAX_REBUTTAL_ROUNDS`.
  - `errors.py` — typed hierarchy (`AuditError:5` + 5 subclasses).
  - `log.py` — debate resumption journal (`append_log:61`, `read_log:121`, `is_round_complete:144`).
  - `__init__.py` — public-surface re-export (`__init__.py:67-101`).
- `dummyindex/context/domains/config.py` — `Config:78` + `read_config:197`/`write_config:214`/`default_config:182`; the shared enum alphabet.
- `dummyindex/cli/onboard.py` — thin `onboard` handler (`run:85`), dispatched as `ContextSubcommand.ONBOARD` (`cli/__init__.py:111`).
- `dummyindex/skills/audit/agents/*.md` — eight shipped persona files the catalog parses (`catalog.py:56-62`).
- `dummyindex/installer/install.py` — `_write_default_config:326` seeds a config at install time so `resolve_model` has a fallback.

## Architecture: the plumbing-vs-orchestration boundary

The single load-bearing decision is a hard line between **deterministic Python plumbing** and **LLM orchestration**. The boundary runs through the audit domain at a nameable seam:

- **Below the line (Python, this feature):** scaffold the workspace, parse the persona menu, resolve personas onto the installed roster, append a debate-log entry. All pure or filesystem-only; no model is ever called. The contract is stated in source at `workspace.py:1-13` and `log.py:10-13`.
- **Above the line (the `/dummyindex-audit` skill):** pick the panel from the menu, run the rebuttal loop, decide convergence, author `report.md` and `findings/*.md`. None of this is in Python — `catalog.py:5-9` documents the catalog as "just a menu," and `MAX_REBUTTAL_ROUNDS` (`enums.py`) is a constant the *skill* honours, not a loop Python runs.

The crossing point is `resolve_catalog` (`catalog.py:159-187`): Python hands the skill a roster-resolved menu, and from there the skill drives. The debate-log (`log.py`) is the only state that flows back down — the skill writes status via `append_log`, letting a re-invoked skill resume a partial run.

Every artifact that crosses to disk is a frozen dataclass with a `schema_version` and `to_dict()`, written tmp+`replace` via `write_text_atomic` per the data-access convention (`models.py:36-45`, `.context/conventions/data-access.md`). This is uniform across both halves — audit's `AuditConfig` and config's `Config` follow the identical persistence shape.

## Data model

### Audit workspace `.context/audits/<slug>/`
- `audit.json` — `AuditConfig.to_dict()`: `{schema_version:1, slug, description, mode, model, scope:[...], max_rounds:3}` (`models.py:36-45`). `from_dict` rejects a wrong `schema_version` and a missing `model` — the model is never silently defaulted, even on load (`models.py:48-65`).
- `description.md` — request + scope + settings brief (`workspace.py:221-239`).
- `catalog.json` — list of `PersonaCard.to_dict()`: `{persona_id, name, role, emoji, subagent_type, triggers:[...], description, requested_subagent_type}` (`models.py:93-103`).
- `findings/` — empty dir; per-persona markdown the agents author at runtime (`workspace.py:163`).
- `_debate-log.json` — `{schema_version:1, slug, entries:[{timestamp, round, persona, status, note}]}`; statuses `started|complete|failed|skipped` (`log.py:14-58`, `enums.py:19-34`).

### `.context/config.json`
Frozen `Config`: `{schema_version:1, scope, scope_path, mode, model, auto_refresh_hook, external_docs:[], reconcile_exclude:[], wire_superpowers}` (`config.py:100-111`). Cross-field invariant: `scope==subdir` requires `scope_path` (`config.py:95-98`). `from_dict` validates every enum, rejects non-bool flags, and rejects `bool` masquerading as `schema_version` (`config.py:113-161`).

## Dependencies

- **Upstream (config → audit):** `resolve_model`/`resolve_mode` call `read_config` (`config.py:197`) to source the fallback model/mode (`workspace.py:99-128`). Audit hard-depends on the config domain for its enum alphabet and its fallback — but never the reverse.
- **Upstream (install → config):** `_write_default_config` (`install.py:326`) seeds `config.json` so `resolve_model` has something to fall back to on a fresh repo; absent it, `resolve_model` raises `ModelRequiredError` rather than guess.
- **Downstream of config (non-audit):** council, equip, and the drift hook all read `Config`. This is why config is mis-homed here (see Open questions) — its blast radius far exceeds audit.
- **Downstream of audit (the skill, above the line):** `/dummyindex-audit` consumes `catalog.json` + `audit.json`, writes back only through `append_log`.
- **Lateral (audit → equip):** `collect_roster` reads `equipment.json` to resolve personas; it guards on `EquipmentSource.MARKETPLACE` to keep legacy schema-v3 plugin entries (recorded with `kind=agent`) out of the dispatch roster (`catalog.py:133-138`).
- **No cycles.** The dependency graph is a DAG: `install → config ← audit ← skill`, with `audit → equip` lateral. Config is a sink-leaning shared kernel; nothing it imports reaches back into audit.

## Key decisions

- **Deterministic plumbing; the orchestrator drives the panel.** No matching/selection logic in Python — panel choice and convergence are the skill's (LLM's) judgment; the catalog is just a menu (`catalog.py:5-9`, `log.py:10-13`). This is the feature's defining constraint, not an implementation detail.
- **Model never silently defaulted.** `resolve_model` and `AuditConfig.from_dict` both fail loud rather than assume one; `resolve_mode` *may* default to `standard` — only the model is the never-silent field (`workspace.py:85-128`, `models.py:54-57`). The asymmetry is deliberate: a wrong model is expensive and unrecoverable; a wrong mode is cheap.
- **Roster resolution is evidence-gated.** `collect_roster` returns `None` when neither `.claude/agents/` nor `equipment.json` exists, and `resolve_catalog(None)` is the identity — a bare repo never downgrades a persona to `general-purpose` on absent evidence (`catalog.py:111-118`, `171-172`). A corrupt `equipment.json` degrades to the agents-dir reading, not a crash (`catalog.py:126-130`).
- **Atomic, byte-stable writes.** All artifacts go through `write_text_atomic` / tmp+`replace`, sorted/deterministic JSON, repo-relative paths — per `.context/conventions/data-access.md`.
- **Audit runs without a `.context/` index.** Unlike council/propose, an on-demand audit grounds only in conventions + feature docs *if they exist* (`workspace.py:10-12`). This is what lets audit be a standalone tool, not a council stage.
- **Config is a shared kernel, not an audit member.** It is co-located here only by Leiden clustering; the `--defaults` CI path (`config.py:182-194`) and the multi-consumer read surface mark it as platform-level.

## Open questions

- **Two distinct concerns Leiden bound together (recommend split).** The audit-panel domain and onboarding/config read as **two bounded contexts**, not one. They share only (a) the `ModelChoice`/`CouncilMode`/`ScopeKind` enum alphabet (`config.py:42-64`) and (b) the model/mode fallback (`workspace.py:99-127`) — a vocabulary-and-fallback coupling, not a behavioural one. Config is consumed far beyond audit (council, equip, drift hook), and onboarding's user flow has nothing to do with adversarial auditing. **Architect recommendation:** promote config/onboarding to its own feature doc (a platform-kernel feature), and have audit-panel cite it as an upstream dependency rather than a co-member. The clustering grouped them on import-edge density; the *concern* boundary disagrees, and the concern boundary should win.
- The interactive 5-question onboarding flow lives in the `/dummyindex` skill, not in `onboard.py` (`onboard.py:3-5`) — the Python side is persistence only; the question wording is unverifiable from source.
- `report.md` and per-persona `findings/*.md` are authored by agents above the plumbing line at runtime; their schema is convention in the persona markdown, not enforced by Python.
