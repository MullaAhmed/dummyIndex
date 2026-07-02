# Audit panel & onboarding — spec
confidence: INFERRED

## Intent

Two halves of one Leiden community, sharing the `ModelChoice`/`CouncilMode` alphabet and the "model is never silently defaulted" rule.

1. **Audit panel** (`context/domains/audit/`): deterministic plumbing for the on-demand argue-and-audit panel. The CLI scaffolds a `.context/audits/<slug>/` workspace, parses a shipped persona catalog, and resolves each persona onto the repo's installed agents. The *auditing* — picking the panel, running the rebuttal loop, writing `report.md` — is the `/dummyindex-audit` skill (LLM), not Python (`workspace.py:1-13`, `__init__.py:9-11`).
2. **Onboarding & config** (`cli/onboard.py` + `context/domains/config.py`): persist the user's council preferences to `.context/config.json` — scope, mode, model, hook, external docs, the v2 keys `command_depths` (per-command council-effort overrides), `wired` (the declarative plugins/skills list), and `dummyindex_version` (last config writer), plus the v3 doc-guard dials `doc_guard_enabled` and `doc_guard_allow` — which the audit domain reads back as the model/mode fallback via `resolve_depth`. The config is schema v3 (`CONFIG_SCHEMA_VERSION = 3`); v1 (`wire_superpowers`), v2 (missing doc-guard keys), and renamed model **values** (legacy `opus-4.7` → `opus-4.8`, via `_LEGACY_MODEL_VALUES`) are migrated in memory on read, so no committed config breaks across a schema or model-value rename. `migrate_config_in_place` persists such a stale config on disk — a value-preserving round-trip the installer runs so `/dummyindex-update` heals existing repos (current configs are left untouched; gated by `_needs_migration`). The PreToolUse doc guard uses `read_doc_guard_settings`, a tolerant hot-path accessor that reads only `doc_guard_enabled` / `doc_guard_allow` and defaults to guard-on if config is absent or malformed. Separately, `reconcile_wired_with_equipment` heals the *declared-intent* gap: a v1→v2 migration seeds `wired` from `default_wired()` alone, so a plugin the user equipped (recorded in `equipment.json`, enabled in `settings.json`) would silently fall out of `config.wired`. The reconciler unions every `kind=plugin` equipment item — matched on the shared `<plugin>@<marketplace>` key — back into `wired`, and the installer runs it on every install. Best-effort and idempotent: absent config is never materialised, an absent/unreadable `equipment.json` contributes nothing, and a no-op adds no git churn (`config.py` `reconcile_wired_with_equipment`).

## User-visible behavior

### Audit workspace scaffold
`dummyindex context audit start --describe "..."` creates `.context/audits/<slug>/` and writes four artifacts atomically: `audit.json` (structured head), `description.md` (human brief), `catalog.json` (resolved persona menu), and an empty `findings/` dir (`workspace.py:143-201`). The slug defaults to `slugify(description)` or an explicit `--slug` validated against path traversal (`workspace.py:48-72`, `157`). It refuses an existing dir without `--force` via `AuditExistsError` (`workspace.py:159-160`). Audit does **not** require a pre-existing `.context/` index — it runs on any repo (`workspace.py:10-12`, `__init__.py` docstring). A debate-log (`_debate-log.json`) records per-(round, persona) work status so a partially-run audit can resume (`log.py:1-25`).

### Persona catalog
Eight shipped personas live as markdown-frontmatter files under `dummyindex/skills/audit/agents/*.md` (architecture, correctness, data-integrity, maintainability, over-engineering, performance, security, tests). `load_catalog` hand-parses each `---` block into a `PersonaCard` (`catalog.py:65-95`, `201-218`). `resolve_catalog` then rewrites each card's `subagent_type` against the installed roster: a shipped name that is installed is kept; an absent one is rewritten to the equipped agent covering the persona's capability (`security` → security specialist, etc.) else `general-purpose`, preserving the original in `requested_subagent_type` (`catalog.py:159-198`, `models.py:68-91`). A bare repo with **no** roster sources (`collect_roster` returns `None`) passes cards through untouched — there's no evidence the global personas are absent (`catalog.py:98-118`, `171-172`).

### Onboarding questions / config
`dummyindex context onboard` persists the answers the `/dummyindex` skill collected: `--scope repo|subdir|explicit`, `--scope-path`, `--mode light|standard|deep`, `--model opus-4.8|sonnet-4.6|haiku-4.5`, `--hook/--no-hook`, repeatable `--doc` (`onboard.py:7-19`, `85-134`). `--model` is **required** in the non-defaults path; omitting it returns exit 2 (`onboard.py:115-117`). `--defaults` writes the recommended baseline (repo/standard/sonnet-4.6/hook-on) for CI, ignoring every other flag (`onboard.py:112-113`, `config.py:182-194`). The handler errors with exit 2 if `.context/` is absent (`onboard.py:105-110`). On success it writes `config.json` and echoes the resolved JSON (`onboard.py:131-134`).

## Contracts

Public functions (verified against `map/symbols.json`):

- `validate_slug(slug: str) -> str` — traversal-safe folder name; raises `AuditSlugError` (`workspace.py:48-61`).
- `slugify(description: str) -> str` — deterministic slug, falls back to `"audit"` (`workspace.py:64-72`).
- `audits_root(context_dir: Path) -> Path` / `audit_dir(context_dir: Path, slug: str) -> Path` (`workspace.py:75-82`).
- `resolve_model(context_dir: Path, model_flag: Optional[str]) -> ModelChoice` — flag → config → `ModelRequiredError`; invalid flag → `AuditError` (`workspace.py:85-105`).
- `resolve_mode(context_dir: Path, mode_flag: Optional[str]) -> CouncilMode` — a thin audit-bound wrapper that delegates to `config.resolve_depth(context_dir, DepthCommand.AUDIT, mode_flag or None)`; precedence is `--mode`/`--depth` flag → `command_depths[audit]` → `mode` → `STANDARD`. An invalid flag surfaces as `AuditError` (not the generic `ConfigError`) so audit's callers/tests are undisturbed (`workspace.py:115-128`).
- `ensure_audit(context_dir, *, description, mode, model, scope=(), slug=None, force=False, personas_dir=None, roster=...) -> AuditStart` (`workspace.py:131-201`).
- `read_audit(context_dir: Path, slug: str) -> AuditConfig` — raises `AuditNotFoundError` if absent (`workspace.py:204-215`).
- `load_catalog(personas_dir: Path) -> tuple[PersonaCard, ...]` (`catalog.py:65-76`); `parse_persona(text, persona_id) -> PersonaCard` (`catalog.py:79-95`).
- `collect_roster(project_root, context_dir) -> Optional[tuple[RosterAgent, ...]]` (`catalog.py:98-156`).
- `resolve_catalog(cards, roster) -> tuple[PersonaCard, ...]` — pure, `replace`-based (`catalog.py:159-187`).
- `default_personas_dir() -> Path` → `dummyindex/skills/audit/agents/` (`catalog.py:56-62`).
- `append_log(workspace, *, round_num, persona, status, note=None, now=None) -> LogEntry` (`log.py:61-118`); `read_log`, `is_round_complete`, `completed_rounds`, `latest_status` (`log.py:121-172`).
- `Config.from_dict(payload) -> Config` / `to_dict()`; `read_config(context_dir) -> Optional[Config]`; `read_doc_guard_settings(context_dir) -> tuple[bool, tuple[str, ...]]` — tolerant, hot-path PreToolUse guard settings read; `write_config(context_dir, config) -> Path` — atomic; stamps `dummyindex_version` on every write; `migrate_config_in_place(context_dir) -> bool` — re-persists a loadable-but-stale config (schema bump or renamed value), preserving choices; `False`/no-op on absent, current, or unreadable configs; `reconcile_wired_with_equipment(context_dir) -> bool` — unions `kind=plugin` items from `equipment.json` (keyed on `<plugin>@<marketplace>`) into `config.wired`, healing plugins a v1→v2 migration would drop; idempotent, `False`/no-op on absent config, absent/unreadable `equipment.json`, or nothing-to-add; `default_config() -> Config` — seeds `wired` from `DEFAULT_PLUGINS` and defaults the doc guard on; `resolve_depth(context_dir, command, depth_flag) -> CouncilMode` — the single per-command depth seam every command resolves through (precedence: flag → `command_depths[command]` → `mode` → `STANDARD`); `current_dummyindex_version() -> str`.
- `onboard.run(args: list[str]) -> int` (`onboard.py:85-134`).

Dataclasses (frozen): `AuditConfig` (`models.py:21-65`), `PersonaCard` (`models.py:68-103`), `AuditStart` (`models.py:106-125`), `RosterAgent` (`catalog.py:48-53`), `LogEntry` (`log.py:43-58`), `Config` (`config.py:124-228`).

Enums: `CouncilMode`, `ModelChoice` (member `OPUS_4_8 = "opus-4.8"`, renamed from `OPUS_4_7`), `ScopeKind`, `DepthCommand` (the closed `command_depths` key alphabet: `ingest`/`reconcile`/`audit`/`build`; `rebuild` deliberately absent) (`config.py:60-96`); `LogStatus`, `MAX_REBUTTAL_ROUNDS=3` (`enums.py:16-31`). `WiredEntry`/`WiredKind` are imported upward from base-layer `default_plugins.py` for `Config.wired`.

Errors: `AuditError` base + `AuditSlugError`, `AuditExistsError`, `AuditNotFoundError`, `ModelRequiredError`, `AuditLogError` (`errors.py:5-54`); `ConfigError(ValueError)` (`config.py:73-74`).

## Examples

Scaffold an audit (model resolved from config or flag), then the skill drives the panel:
```
dummyindex context audit start --describe "audit the auth flow for security holes"
# -> .context/audits/audit-the-auth-flow-for-security-holes/
#    audit.json, description.md, catalog.json, findings/
```

Persist preferences for CI:
```
dummyindex context onboard --defaults
# -> writes .context/config.json (repo / standard / sonnet-4.6 / hook on)
```

Persist explicit choices (model required):
```
dummyindex context onboard --scope repo --mode deep --model opus-4.8 --doc docs/
```

Roster resolution: shipped `security.md` carries `subagent_type: Security Engineer`. On a repo without that agent installed but with a security-capability specialist, `resolve_catalog` rewrites the card's `subagent_type` to that specialist and records `requested_subagent_type: "Security Engineer"` (`catalog.py:175-186`).
