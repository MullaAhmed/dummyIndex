# Audit Panel and Onboarding Implementation Plan

confidence: INFERRED

## Where it lives

- `dummyindex/context/domains/config.py` is the shared policy kernel: schema-v4 data, strict reads, legacy migration, host-aware defaults, tri-state default-plugin reconciliation, depth resolution, and atomic persistence (`dummyindex/context/domains/config.py:72-682`).
- `dummyindex/cli/onboard.py` is CLI plumbing: parse and validate persistence flags, resolve the host set, build a `Config`, call the writer, and report exact persisted output (`dummyindex/cli/onboard.py:58-297`).
- `dummyindex/installer/install.py` is lifecycle plumbing: create defaults only when config is absent, migrate stale config on install, reconcile equipment intent, then validate and reconcile defaults before plugin wiring (`dummyindex/installer/install.py:535-665`).
- `dummyindex/context/domains/audit/models.py`, `catalog.py`, and `workspace.py` own the deterministic audit records, persona resolution, slug/model/mode policy, and workspace materialization (`dummyindex/context/domains/audit/models.py:19-126`, `dummyindex/context/domains/audit/catalog.py:31-214`, `dummyindex/context/domains/audit/workspace.py:49-252`).
- `tests/context/domains/test_config.py` and `tests/context/domains/audit/test_audit_domain.py` pin schema migration, host inference, opt-out preservation, no-op byte identity, audit scaffolding, and roster fallback (`tests/context/domains/test_config.py:59-1531`, `tests/context/domains/audit/test_audit_domain.py:49-670`).

## Architecture in three sentences

The config domain is the core data framework: it turns persisted JSON into one strict schema-v4 object while preserving legacy user intent and exposing host-aware default and depth policies (`dummyindex/context/domains/config.py:160-477`). Onboarding and installer modules are boundary plumbing that collect choices or lifecycle context, call the config policy, and persist or reconcile results without owning schema semantics (`dummyindex/cli/onboard.py:111-267`, `dummyindex/installer/install.py:535-665`). The audit domain consumes the shared model/mode vocabulary, builds a safe filesystem workspace and roster-resolved persona menu, then stops before agent selection or LLM execution (`dummyindex/context/domains/audit/models.py:22-126`, `dummyindex/context/domains/audit/catalog.py:65-194`, `dummyindex/context/domains/audit/workspace.py:104-213`).

## Data model

- `.context/config.json` uses schema 4. `default_plugins_enabled` is an explicit tri-state independent of the ordered `wired` ledger: true enables reviewed defaults, false tombstones all defaults, and null means defaults have not applied to a Codex-only baseline (`dummyindex/context/domains/config.py:24-50`, `dummyindex/context/domains/config.py:160-212`).
- Closed enum alphabets define scope, global council mode, model choice, and depth-bearing commands; the `current` model delegates to the host session, and deterministic rebuild is deliberately absent from depth commands (`dummyindex/context/domains/config.py:85-137`).
- `wired` is an ordered tuple of `WiredEntry`; default reconciliation deduplicates by target and appends missing reviewed entries after custom entries, preserving the user's ledger order (`dummyindex/context/domains/config.py:645-658`).
- `AuditConfig` schema 1 carries slug, description, mode, explicit model, scope, and max rounds; `PersonaCard` carries the resolved agent plus an optional requested agent; `AuditStart` reports created paths and catalog (`dummyindex/context/domains/audit/models.py:19-126`).
- The audit workspace contains `audit.json`, `description.md`, `catalog.json`, and `findings/`; agent-authored findings and final synthesis remain above the deterministic Python boundary (`dummyindex/context/domains/audit/workspace.py:1-13`, `dummyindex/context/domains/audit/workspace.py:186-213`).

## Key decisions

- Separate applicability from declaration. A Codex-only empty ledger is `null`, while an intentional empty Claude-era ledger is `false`; schema-v4 payloads must state the distinction explicitly (`dummyindex/context/domains/config.py:378-421`).
- Preserve user intent across upgrades. Migration rewrites only stale-but-loadable content, keeps existing choices and custom ledger order, and does not churn current or unreadable files (`dummyindex/context/domains/config.py:525-564`, `tests/context/domains/test_config.py:1332-1373`).
- Make opt-out durable and reconciliation idempotent. Codex and explicit false do not mutate; Claude-enabled transitions append only missing defaults and no-op runs preserve bytes (`dummyindex/context/domains/config.py:622-659`, `tests/context/domains/test_config.py:1103-1205`).
- Fail closed before plugin lifecycle work. Installer orchestration validates config before migration or default backfill and skips defaults when config is malformed (`dummyindex/installer/install.py:609-649`).
- Keep model selection explicit while allowing effort fallback. Audit model resolution ends in `ModelRequiredError`; audit mode shares the global depth precedence and may fall back to standard (`dummyindex/context/domains/audit/workspace.py:104-140`).
- Treat persona selection as agent judgment, but make the menu deterministic. Python parses sorted shipped cards and resolves dispatch targets from observable roster evidence; it does not choose the task panel (`dummyindex/context/domains/audit/catalog.py:1-21`, `dummyindex/context/domains/audit/catalog.py:65-194`).
- Audit trail: the previous curated feature spec and plan described schema v3 and omitted `default_plugins_enabled`; live schema-v4 code and tests supersede those claims. The feature's catalogued medium-confidence superpowers-era pointers also report broken references and their linked files are absent, so they are not used as authority.

## Open questions

- The clustering combines audit mechanics with a cross-cutting config/onboarding kernel. The dependency is real—shared model/mode resolution—but config serves more than audit, so a later taxonomy pass should consider separating the bounded contexts.
- Explicit non-default onboarding constructs `Config` with an empty `wired` ledger and the dataclass default `default_plugins_enabled=None`, even for an explicitly named Claude host; reviewed defaults are added only when installer reconciliation later runs (`dummyindex/cli/onboard.py:182-206`, `dummyindex/context/domains/config.py:622-659`). Confirm whether standalone onboarding should invoke the same reconciliation contract.
- `--defaults` infers hosts from managed guidance markers, while explicit onboarding without `--platform` deliberately preserves the historical Claude hook default even if the required model is `current` (`dummyindex/cli/onboard.py:143-168`, `dummyindex/cli/onboard.py:209-267`). The asymmetry is documented in source but remains easy for callers to misread.
- `force=True` reuses an existing audit directory and overwrites scaffold files without clearing old findings or other runtime state (`dummyindex/context/domains/audit/workspace.py:169-205`). Define whether force means partial refresh or a clean restart before extending the CLI surface.
- Roster capability resolution chooses the first matching equipment-order agent (`dummyindex/context/domains/audit/catalog.py:188-194`). If byte-identical catalogs across manifest reorderings become a requirement, the roster needs an explicit stable preference rule.
