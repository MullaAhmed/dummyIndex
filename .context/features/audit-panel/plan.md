# Audit Panel and Onboarding Architecture Plan

confidence: INFERRED

## Bounded contexts

This feature holds two bounded contexts with a one-way dependency. It is not one cohesive domain.

1. **Configuration and onboarding kernel:** owns schema-v5 council preferences and strict deserialization. It also owns legacy normalization, host-aware defaults, depth resolution, plugin-intent reconciliation (defaults and equipment), and config persistence. Onboarding is its CLI adapter. Installer code is a lifecycle consumer (`dummyindex/context/domains/config.py:82-756`, `dummyindex/cli/onboard.py:114-308`, `dummyindex/installer/install/project_init.py:253-337`).
2. **Audit workspace adapter:** owns audit records, slug safety, model and inherited depth resolution, persona parsing, roster resolution, and scaffolding. The agent skill owns panel selection and execution (`dummyindex/context/domains/audit/models.py:19-126`, `dummyindex/context/domains/audit/catalog.py:1-21`, `dummyindex/context/domains/audit/workspace.py:1-13`).

Audit imports `ConfigError`, `CouncilMode`, `DepthCommand`, `ModelChoice`, `read_config`, and `resolve_depth` from the configuration kernel. Configuration does not import audit (`dummyindex/context/domains/audit/workspace.py:23-31`).

## Where it lives

- `dummyindex/skills/audit/SKILL.md` owns host orchestration and one supported closeout reflection. Its bundled `closeout.md` generates inventory hashes and manifest shape from explicit review decisions. The common learning path gates and promotes the managed rule. Report and audited source stay unchanged after closeout.

- `dummyindex/context/domains/config.py` is the shared kernel and persistence boundary. It imports the base-layer default-plugin vocabulary. It validates schema 1-4 input into current schema 5. v5 adds the `build` auto-recouncil policy. It exposes host factories and read models. It reconciles declared intent (reviewed defaults and equipment write-back). It writes the canonical JSON (`dummyindex/context/domains/config.py:78-104`, `dummyindex/context/domains/config.py:177-354`, `dummyindex/context/domains/config.py:498-756`).
- `dummyindex/cli/onboard.py` is a thin command adapter. It parses persistence inputs. It resolves or infers host coverage. It rejects inconsistent host, model, and hook combinations. It builds a `Config` and delegates the write (`dummyindex/cli/onboard.py:58-111`, `dummyindex/cli/onboard.py:114-218`, `dummyindex/cli/onboard.py:221-308`).
- `dummyindex/installer/install/` orchestrates config lifecycle in install order. It creates absent defaults at `dummyindex/installer/install/orchestrate.py:333`. For existing repos, it migrates stale state, folds equipment intent, validates, reconciles reviewed defaults, and wires plugins (`project_init.py:253-337`). The enriched-refresh path also calls `reconcile_claude_md` at `project_init.py:98`.
- `dummyindex/context/domains/audit/models.py` defines persisted audit heads. `catalog.py` turns shipped persona cards plus observable equipment into a resolved menu. `workspace.py` validates, resolves, and writes one workspace (`dummyindex/context/domains/audit/models.py:19-126`, `dummyindex/context/domains/audit/catalog.py:48-196`, `dummyindex/context/domains/audit/workspace.py:49-252`).

## Architecture summary

The configuration kernel is a strict-reader, current-writer boundary. Every supported legacy payload normalizes to schema 5. Current writes require explicit tri-state default-plugin policy (`dummyindex/context/domains/config.py:262-354`, `dummyindex/context/domains/config.py:736-756`). Onboarding and installer code supply host and lifecycle context. They delegate normalization, reconciliation, and persistence to the kernel (`dummyindex/cli/onboard.py:114-277`, `dummyindex/installer/install/project_init.py:253-337`). Audit consumes only the shared model and mode policy. It composes immutable records, a persona menu, and atomic workspace files before agent orchestration (`dummyindex/context/domains/audit/models.py:22-126`, `dummyindex/context/domains/audit/catalog.py:65-196`, `dummyindex/context/domains/audit/workspace.py:104-213`).

## Patterns named

- **Strict reader, current writer:** `Config.from_dict` rejects malformed types and unsupported versions. It read-migrates versions 1-4 and always returns schema 5. `write_config` stamps the current CLI writer version (`dummyindex/context/domains/config.py:262-354`, `dummyindex/context/domains/config.py:736-756`).
- **Read-normalize-write migration:** `_needs_migration` gates stale schema or renamed model values. A legacy model label alone marks a current-schema config stale. `Config.from_dict` normalizes. `write_config` persists only successful loads. Absent, current, or unreadable files stay byte-identical (`dummyindex/context/domains/config.py:599-638`, `dummyindex/context/domains/config.py:97-104`).
- **Tri-state applicability policy:** `default_plugins_enabled` separates enabled, durable opt-out, and Codex-only not-applicable state. It stays apart from the ordered `wired` declaration ledger (`dummyindex/context/domains/config.py:226-239`, `dummyindex/context/domains/config.py:449-479`).
- **Monotone reconciliation:** reviewed defaults are appended only when missing. Existing and custom declaration order is preserved. No-op paths do not write (`dummyindex/context/domains/config.py:696-733`, `tests/context/domains/test_config.py:1185-1295`). The same shape heals `wired` from `equipment.json` (`reconcile_wired_with_equipment`, `:641-693`).
- **Validate-before-reconcile orchestration:** the installer reads config strictly before tolerant migration and reconciliation helpers. Malformed state therefore cannot seed defaults or reach settings or runner work (`dummyindex/installer/install/project_init.py:326-341`).
- **Host-aware factory:** `default_config(platform=...)` centralizes the Claude, Codex, and both baselines. Onboarding host inference reads exact managed markers. It falls back to Claude when no marker exists (`dummyindex/context/domains/config.py:498-529`, `dummyindex/cli/onboard.py:221-258`).
- **Explicit expensive choice, inherited effort:** audit model resolution requires a flag or config. Audit mode delegates to the shared chain: flag, command depth, global mode, then standard (`dummyindex/context/domains/audit/workspace.py:104-140`, `dummyindex/context/domains/config.py:532-551`).
- **Evidence-sensitive roster resolution:** `roster=None` means no observable roster source. It preserves shipped names. An observed empty roster is evidence that missing names must fall back (`dummyindex/context/domains/audit/catalog.py:96-196`, `tests/context/domains/audit/test_audit_domain.py:369-405`).
- **Deterministic scaffold/orchestrator boundary:** Python writes the audit head, brief, and resolved menu. It does not choose or execute the panel (`dummyindex/context/domains/audit/models.py:1-7`, `dummyindex/context/domains/audit/workspace.py:143-213`).

## Dependencies surfaced

### Configuration kernel upstream

- `dummyindex.context.default_plugins` supplies `WiredEntry`, `WiredKind`, reviewed defaults, and enablement semantics. It imports no domain, CLI, or installer code (`dummyindex/context/domains/config.py:78-78`, `dummyindex/context/default_plugins.py:20-35`, `dummyindex/context/default_plugins.py:165-272`).
- Equipment manifest types and readers are imported locally only by `reconcile_wired_with_equipment`. This keeps optional reconciliation dependencies off the module-load path (`dummyindex/context/domains/config.py:670-674`).

### Configuration kernel downstream

- Onboarding and installer own user and lifecycle orchestration (`dummyindex/cli/onboard.py:44-56`, `dummyindex/installer/install/project_init.py:253-337`).
- Init and reconcile use the shared depth and default-plugin seams. Status projects writer, depth, and wired state read-only. The doc guard consumes the tolerant guard projection (`dummyindex/cli/init.py:29-44`, `dummyindex/cli/init.py:131-145`, `dummyindex/cli/reconcile.py:50-65`, `dummyindex/cli/status.py:102-180`, `dummyindex/cli/guard_doc_write.py:54-75`).
- Reconcile drift filtering reads config exclusions. Audit reads model and mode policy (`dummyindex/context/build/reconcile.py:45-52`, `dummyindex/context/domains/audit/workspace.py:23-31`).

### Audit upstream and downstream

- Audit depends upward on the configuration kernel, atomic text output, shipped personas, and the equipment manifest. The manifest and agent directory supply optional roster evidence (`dummyindex/context/domains/audit/workspace.py:23-47`, `dummyindex/context/domains/audit/catalog.py:56-154`).
- `cli/audit.py` is the primary command adapter. GC and doc migration also reuse `AuditSlugError`. That exposes audit's slug vocabulary outside the audit command surface (`dummyindex/cli/audit.py:45-95`, `dummyindex/cli/gc.py:79-94`, `dummyindex/cli/migrate_docs.py:49-63`).

### Cycle check

No source cycle appears in the inspected paths. Default-plugin code sits below the domain layer. Config imports equipment only inside reconciliation functions. Audit imports config and equipment-facing catalog types. Neither config nor equipment imports audit. CLI and installer modules depend inward on both domains (`dummyindex/context/default_plugins.py:20-35`, `dummyindex/context/domains/config.py:78-78`, `dummyindex/context/domains/config.py:670-674`, `dummyindex/context/domains/audit/workspace.py:23-47`, `dummyindex/context/domains/audit/catalog.py:121-127`).

## Data model

- `Config` is an immutable schema-v5 record. Its `wired` tuple records ordered declared intent. `default_plugins_enabled` records applicability and opt-out independently. `build` carries the v5 `BuildPolicy.auto_recouncil` default-on flag. `dummyindex_version` describes the last config writer. Doc-guard fields support a tolerant hot-path projection (`dummyindex/context/domains/config.py:206-230`, `dummyindex/context/domains/config.py:571-596`).
- V1 maps `wire_superpowers` directly to declarations and boolean default state. V2 and v3 infer state from `wired`, except that the exact Codex baseline maps an empty ledger to `null`. Schema 4 and up require an explicit boolean-or-null field (`dummyindex/context/domains/config.py:409-495`).
- `ScopeKind`, `CouncilMode`, `ModelChoice`, and `DepthCommand` are closed alphabets. The model alphabet is generation-less family labels (`current|opus|sonnet|haiku|fable`). Version-pinned predecessors read-migrate through `_LEGACY_MODEL_VALUES`. Only ingest, reconcile, audit, and build are depth-bearing (`dummyindex/context/domains/config.py:97-155`).
- `AuditConfig` schema 1 requires a model. It serializes slug, request, mode, model, scope, and max rounds. `PersonaCard` preserves both resolved and requested agent identity. `AuditStart` reports the scaffold result (`dummyindex/context/domains/audit/models.py:22-126`).
- The audit workspace contains `audit.json`, `description.md`, `catalog.json`, and `findings/`. Atomic output goes through `write_text_atomic` (`dummyindex/context/domains/audit/workspace.py:1-13`, `dummyindex/context/domains/audit/workspace.py:174-213`).

## Key decisions

- Keep config and onboarding architecture independent from audit. Audit is one consumer of shared preferences. It does not own the schema.
- Require schema 4 and up to state default-plugin applicability explicitly. Migrate legacy ambiguity conservatively. Exact Codex baseline evidence is required before an empty legacy ledger becomes `null` (`dummyindex/context/domains/config.py:449-495`).
- Preserve user intent through monotone, ordered, idempotent reconciliation. Existing declarations are never reordered or removed. Explicit `false` remains a tombstone (`dummyindex/context/domains/config.py:696-733`, `tests/context/domains/test_config.py:1218-1289`).
- Keep tolerant helpers behind strict orchestration. Migration and equipment reconciliation may no-op on unreadable state. The installer validates first and skips all default lifecycle work on malformed config (`dummyindex/context/domains/config.py:599-693`, `dummyindex/installer/install/project_init.py:326-341`).
- Keep audit model selection explicit and depth selection shared. Missing config can default effort to standard. It cannot silently select a model (`dummyindex/context/domains/audit/workspace.py:104-140`).
- Preserve the distinction between unknown and known-empty roster state. Unknown evidence keeps shipped targets. Known absence triggers capability or general-purpose fallback (`dummyindex/context/domains/audit/catalog.py:96-196`).
- Keep the Python audit domain below the orchestration line. It prepares deterministic state. It never chooses auditors or runs rebuttals (`dummyindex/context/domains/audit/models.py:1-7`, `dummyindex/context/domains/audit/catalog.py:1-21`).

## Open questions

- Split the generated taxonomy. Promote configuration and onboarding to a platform-kernel feature. Keep audit-panel as a downstream workspace feature. The current community reflects import density, not a single responsibility.
- Explicit non-default onboarding creates an empty ledger with `default_plugins_enabled=None`. This holds even for an explicitly selected Claude host. Reviewed defaults arrive only if installer reconciliation runs later (`dummyindex/cli/onboard.py:194-218`, `dummyindex/context/domains/config.py:696-733`). Decide whether standalone onboarding should invoke the same host reconciliation.
- `force=True` overwrites scaffold heads in an existing audit directory. It does not clear old findings or other runtime artifacts (`dummyindex/context/domains/audit/workspace.py:171-213`). Define clean restart semantics before extending force behavior.
- Capability resolution chooses the first matching agent in observable roster order (`dummyindex/context/domains/audit/catalog.py:188-195`). Define a stable tie-break if manifest reordering must not change `catalog.json`.
- `AuditSlugError` is reused by GC and doc migration. That reveals a shared workspace-slug concern under an audit-specific error type (`dummyindex/cli/gc.py:87-141`, `dummyindex/cli/migrate_docs.py:56-83`). Decide whether slug validation belongs in a neutral workspace layer.

## Audit trail

No catalogued prose document is quoted or treated as authority. The previous curated plan's schema-v3 claims conflicted with live schema-v4 code. Stage 1 superseded them. The feature's medium-confidence superpowers-era pointers carry broken references and absent linked files. Source and tests therefore govern migration and default-plugin decisions. Low-confidence prose remains historical context only.
