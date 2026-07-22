# Audit Panel and Onboarding Architect Notes

## What I changed

- Reframed the feature as two bounded contexts with a one-way dependency: configuration/onboarding kernel and audit workspace adapter.
- Reorganized the plan around strict schema normalization, host-aware defaults, reconciliation semantics, audit orchestration boundaries, dependency direction, and promoted decisions.
- Replaced stale v3-era framing and broad file inventory with schema-v4 decision seams and concrete consumers.

## Patterns named

- Strict reader, current writer.
- Read-normalize-write migration.
- Tri-state applicability policy.
- Monotone ordered reconciliation.
- Validate-before-reconcile orchestration.
- Host-aware factory.
- Explicit expensive choice, inherited effort.
- Evidence-sensitive roster resolution.
- Deterministic scaffold/orchestrator boundary.

## Dependencies surfaced

- Configuration upstream: base-layer default-plugin vocabulary and locally imported equipment manifest readers.
- Configuration downstream: onboarding, installer, init, reconcile, status, doc guard, build reconcile, and audit.
- Audit upstream: config model/depth policy, atomic I/O, shipped personas, and optional equipment/agent roster evidence.
- Audit downstream: audit CLI, with slug-error reuse by GC and doc migration.
- Cycle result: default plugins → config → audit; equipment is locally consulted by config/catalog; CLI and installer depend inward. No reverse domain import is present.

## Decisions promoted

- Treat config/onboarding as a platform kernel, not audit-owned behavior.
- Require explicit schema-v4 plugin applicability and preserve legacy ambiguity conservatively.
- Preserve ordered user declarations and durable opt-out through idempotent reconciliation.
- Keep tolerant migration helpers behind strict installer validation.
- Require an explicit audit model while sharing depth fallback.
- Preserve unknown versus known-empty roster evidence.
- Keep deterministic Python scaffolding below agent orchestration.
