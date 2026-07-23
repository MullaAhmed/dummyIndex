# Audit Panel and Onboarding Architecture Plan

confidence: INFERRED

## Bounded contexts

This generated feature contains two bounded contexts joined by a one-way dependency, not one cohesive domain.

1. **Configuration and onboarding kernel:** owns schema-v4 council preferences, strict deserialization, legacy normalization, host-aware defaults, depth resolution, plugin-intent reconciliation, and config persistence. Onboarding is its CLI adapter; installer code is a lifecycle consumer (`dummyindex/context/domains/config.py:72-682`, `dummyindex/cli/onboard.py:111-297`, `dummyindex/installer/install.py:535-665`).
2. **Audit workspace adapter:** owns audit records, slug safety, explicit model and inherited depth resolution, persona parsing and roster resolution, and deterministic workspace scaffolding. It stops at a resolved catalog; the agent skill owns panel selection and execution (`dummyindex/context/domains/audit/models.py:19-126`, `dummyindex/context/domains/audit/catalog.py:1-21`, `dummyindex/context/domains/audit/workspace.py:1-13`).

The architectural seam is narrow: audit imports `CouncilMode`, `ModelChoice`, `read_config`, and `resolve_depth` from the configuration kernel. Configuration does not import audit (`dummyindex/context/domains/audit/models.py:15-17`, `dummyindex/context/domains/audit/workspace.py:23-31`).

## Where it lives

- `dummyindex/context/domains/config.py` is the shared kernel and persistence boundary. It imports the base-layer default-plugin vocabulary, validates schema 1–4 input into schema 4, exposes host factories and read models, reconciles declared intent, and writes the canonical JSON (`dummyindex/context/domains/config.py:60-75`, `dummyindex/context/domains/config.py:160-301`, `dummyindex/context/domains/config.py:424-682`).
- `dummyindex/cli/onboard.py` is a thin command adapter. It parses persistence inputs, resolves or infers host coverage, rejects inconsistent host/model/hook combinations, builds a `Config`, and delegates the write (`dummyindex/cli/onboard.py:58-108`, `dummyindex/cli/onboard.py:111-206`, `dummyindex/cli/onboard.py:209-297`).
- `dummyindex/installer/install.py` orchestrates config lifecycle in install order: create absent defaults, migrate stale state, fold equipment intent, validate, reconcile reviewed defaults, then wire/install plugins (`dummyindex/installer/install.py:535-665`).
- `dummyindex/context/domains/audit/models.py` defines persisted audit heads; `catalog.py` turns shipped persona cards plus observable equipment into a resolved menu; `workspace.py` validates, resolves, and writes one workspace (`dummyindex/context/domains/audit/models.py:19-126`, `dummyindex/context/domains/audit/catalog.py:48-214`, `dummyindex/context/domains/audit/workspace.py:49-252`).

## Architecture in three sentences

The configuration kernel is a strict-reader/current-writer boundary: every supported legacy payload normalizes to schema 4, while current writes require explicit tri-state default-plugin policy (`dummyindex/context/domains/config.py:214-301`, `dummyindex/context/domains/config.py:378-421`, `dummyindex/context/domains/config.py:662-682`). Onboarding and installer code supply host and lifecycle context, then delegate normalization, reconciliation, and persistence to that kernel instead of duplicating schema rules (`dummyindex/cli/onboard.py:111-267`, `dummyindex/installer/install.py:535-665`). Audit consumes only the shared model/mode policy and separately composes immutable audit records, an evidence-resolved persona menu, and atomic workspace files before handing control to agent orchestration (`dummyindex/context/domains/audit/models.py:22-126`, `dummyindex/context/domains/audit/catalog.py:65-194`, `dummyindex/context/domains/audit/workspace.py:104-213`).

## Patterns named

- **Strict reader, current writer:** `Config.from_dict` rejects malformed types and unsupported versions, read-migrates versions 1–3, and always returns schema 4; `write_config` stamps the current CLI writer version (`dummyindex/context/domains/config.py:214-301`, `dummyindex/context/domains/config.py:662-682`).
- **Read-normalize-write migration:** `_needs_migration` gates stale schema or renamed model values, `Config.from_dict` performs normalization, and `write_config` persists only successful loads. Absent, current, or unreadable files remain byte-identical (`dummyindex/context/domains/config.py:525-564`).
- **Tri-state applicability policy:** `default_plugins_enabled` separates enabled, durable opt-out, and Codex-only not-applicable state from the ordered `wired` declaration ledger (`dummyindex/context/domains/config.py:24-50`, `dummyindex/context/domains/config.py:378-421`).
- **Monotone reconciliation:** reviewed defaults are appended only when missing; existing and custom declaration order is preserved; no-op paths do not write (`dummyindex/context/domains/config.py:622-659`, `tests/context/domains/test_config.py:1103-1205`).
- **Validate-before-reconcile orchestration:** installer reads config strictly before tolerant migration and reconciliation helpers, so malformed state cannot seed defaults or reach settings/runner work (`dummyindex/installer/install.py:609-649`).
- **Host-aware factory:** `default_config(platform=...)` centralizes the Claude, Codex, and both baselines; onboarding host inference reads exact managed markers and falls back to Claude when no marker exists (`dummyindex/context/domains/config.py:424-455`, `dummyindex/cli/onboard.py:209-247`).
- **Explicit expensive choice, inherited effort:** audit model resolution requires flag or config; audit mode delegates to the shared flag → command depth → global mode → standard chain (`dummyindex/context/domains/audit/workspace.py:104-140`, `dummyindex/context/domains/config.py:458-477`).
- **Evidence-sensitive roster resolution:** `roster=None` means no observable roster source and preserves shipped names; an observed empty roster is evidence that missing names must fall back (`dummyindex/context/domains/audit/catalog.py:96-194`, `tests/context/domains/audit/test_audit_domain.py:369-405`).
- **Deterministic scaffold/orchestrator boundary:** Python writes the audit head, brief, and resolved menu; it does not choose or execute the panel (`dummyindex/context/domains/audit/models.py:1-7`, `dummyindex/context/domains/audit/workspace.py:143-213`).

## Dependencies surfaced

### Configuration kernel upstream

- `dummyindex.context.default_plugins` supplies `WiredEntry`, `WiredKind`, reviewed defaults, and enablement semantics. It is explicitly a base-layer module that imports no domain, CLI, or installer code (`dummyindex/context/domains/config.py:68-68`, `dummyindex/context/default_plugins.py:1-15`, `dummyindex/context/default_plugins.py:62-108`).
- Equipment manifest types and readers are imported locally only by `reconcile_wired_with_equipment`, keeping optional reconciliation dependencies off the module-load path (`dummyindex/context/domains/config.py:567-619`).

### Configuration kernel downstream

- Onboarding and installer own user/lifecycle orchestration (`dummyindex/cli/onboard.py:42-53`, `dummyindex/installer/install.py:535-665`).
- Init and reconcile use the shared depth and default-plugin seams; status projects writer/depth/wired state read-only; the doc guard consumes the tolerant guard projection (`dummyindex/cli/init.py:29-44`, `dummyindex/cli/init.py:131-145`, `dummyindex/cli/reconcile.py:50-65`, `dummyindex/cli/status.py:102-180`, `dummyindex/cli/guard_doc_write.py:54-75`).
- Reconcile drift filtering reads config exclusions, and audit reads model/mode policy (`dummyindex/context/build/reconcile.py:45-52`, `dummyindex/context/domains/audit/workspace.py:23-31`).

### Audit upstream and downstream

- Audit depends upward on the configuration kernel, atomic text output, shipped personas, and the equipment manifest/agent directory as optional roster evidence (`dummyindex/context/domains/audit/workspace.py:23-47`, `dummyindex/context/domains/audit/catalog.py:56-154`).
- `cli/audit.py` is the primary command adapter; GC and doc migration also reuse `AuditSlugError`, which exposes audit's slug vocabulary outside the audit command surface (`dummyindex/cli/audit.py:45-95`, `dummyindex/cli/gc.py:79-94`, `dummyindex/cli/migrate_docs.py:49-63`).

### Cycle check

No source cycle is present in the inspected paths. Default-plugin code is below the domain layer; config imports equipment only inside reconciliation functions; audit imports config and equipment-facing catalog types, while neither config nor equipment imports audit; CLI and installer modules depend inward on both domains (`dummyindex/context/default_plugins.py:10-15`, `dummyindex/context/domains/config.py:68-68`, `dummyindex/context/domains/config.py:586-604`, `dummyindex/context/domains/audit/workspace.py:23-47`, `dummyindex/context/domains/audit/catalog.py:121-127`).

## Data model

- `Config` is an immutable schema-v4 record. Its `wired` tuple records ordered declared intent; `default_plugins_enabled` records applicability/opt-out independently; `dummyindex_version` describes the last config writer; doc-guard fields support a tolerant hot-path projection (`dummyindex/context/domains/config.py:160-212`, `dummyindex/context/domains/config.py:497-522`).
- V1 maps `wire_superpowers` directly to declarations and boolean default state. V2/v3 infer state from `wired`, except the exact Codex baseline maps an empty ledger to null; schema 4 requires an explicit boolean-or-null field (`dummyindex/context/domains/config.py:356-421`).
- `ScopeKind`, `CouncilMode`, `ModelChoice`, and `DepthCommand` are closed alphabets; only ingest, reconcile, audit, and build are depth-bearing (`dummyindex/context/domains/config.py:85-137`).
- `AuditConfig` schema 1 requires a model and serializes slug, request, mode, model, scope, and max rounds. `PersonaCard` preserves both resolved and requested agent identity; `AuditStart` reports the scaffold result (`dummyindex/context/domains/audit/models.py:19-126`).
- The audit workspace contains `audit.json`, `description.md`, `catalog.json`, and `findings/`; atomic output is delegated to `write_text_atomic` (`dummyindex/context/domains/audit/workspace.py:1-13`, `dummyindex/context/domains/audit/workspace.py:174-213`).

## Key decisions

- Keep config/onboarding architecture independent from audit. Audit is one consumer of shared preferences, not the owner of the schema.
- Require schema 4 to state default-plugin applicability explicitly, while migrating legacy ambiguity conservatively. Exact Codex baseline evidence is required before an empty legacy ledger becomes null (`dummyindex/context/domains/config.py:378-421`).
- Preserve user intent through monotone, ordered, idempotent reconciliation. Existing declarations are never reordered or removed, and explicit false remains a tombstone (`dummyindex/context/domains/config.py:622-659`, `tests/context/domains/test_config.py:1136-1192`).
- Keep tolerant helpers behind strict orchestration. Migration and equipment reconciliation may no-op on unreadable state, but installer validates first and skips all default lifecycle work on malformed config (`dummyindex/context/domains/config.py:540-619`, `dummyindex/installer/install.py:634-649`).
- Keep audit model selection explicit and depth selection shared. Missing config can default effort to standard, but cannot silently select a model (`dummyindex/context/domains/audit/workspace.py:104-140`).
- Preserve the distinction between unknown and known-empty roster state. Unknown evidence keeps shipped targets; known absence triggers capability or general-purpose fallback (`dummyindex/context/domains/audit/catalog.py:96-194`).
- Keep the Python audit domain below the orchestration line. It prepares deterministic state and never chooses auditors or runs rebuttals (`dummyindex/context/domains/audit/models.py:1-7`, `dummyindex/context/domains/audit/catalog.py:1-21`).

## Open questions

- Split the generated taxonomy: promote configuration/onboarding to a platform-kernel feature and retain audit-panel as a downstream workspace feature. The current community reflects import density, not a single responsibility.
- Explicit non-default onboarding creates an empty ledger with `default_plugins_enabled=None` even for an explicitly selected Claude host; reviewed defaults arrive only if installer reconciliation runs later (`dummyindex/cli/onboard.py:182-206`, `dummyindex/context/domains/config.py:622-659`). Decide whether standalone onboarding should invoke the same host reconciliation.
- `force=True` overwrites scaffold heads in an existing audit directory but does not clear old findings or other runtime artifacts (`dummyindex/context/domains/audit/workspace.py:169-205`). Define clean restart semantics before extending force behavior.
- Capability resolution chooses the first matching agent in observable roster order (`dummyindex/context/domains/audit/catalog.py:188-194`). Define a stable tie-break if manifest reordering must not change `catalog.json`.
- `AuditSlugError` is reused by GC and doc migration, revealing a shared workspace-slug concern under an audit-specific error type (`dummyindex/cli/gc.py:79-94`, `dummyindex/cli/migrate_docs.py:49-63`). Decide whether slug validation belongs in a neutral workspace layer.

## Audit trail

No catalogued prose document is quoted or treated as authority. The previous curated plan's schema-v3 claims conflicted with live schema-v4 code and were superseded in stage 1; this architecture revision preserves that correction. The feature's medium-confidence superpowers-era pointers carry broken references and absent linked files, so source and tests govern migration and default-plugin decisions; low-confidence prose remains historical context only.
