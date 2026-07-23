# Codex Guidance Architect Notes

## What I changed

- Defined the bounded context around instruction-file policy and managed lifecycle, excluding generic block mutation, configuration authoring, orchestration, indexing, and document discovery.
- Reorganized the plan around architecture, named patterns, upstream/downstream dependencies, cycle analysis, promoted decisions, and unresolved boundaries.
- Replaced broad implementation inventory with decision seams and consumers that explain why the module split exists.

## Patterns named

- Policy kernel.
- Trust-gated configuration overlay.
- Plan/apply split.
- Marker-bounded ownership.
- Fail-closed filesystem boundary.
- Bounded stale-resource discovery.
- Best-effort batch cleanup.

## Dependencies surfaced

- Upstream: stdlib/TOML compatibility and shared managed-block infrastructure.
- Downstream: installer, uninstall, init/bootstrap, onboarding host inference, file detection, document collection, reconcile filtering, and source-doc discovery.
- Cycle result: policy kernel → no project imports; lifecycle adapter → policy kernel + shared bootstrap; callers → kernel/adapter. No reverse import is present in the inspected source.

## Decisions promoted

- Preserve distinct project and global target-selection semantics.
- Place the Codex block first and validate its complete byte footprint before writing.
- Gate project config through explicit user trust.
- Preserve existing ownership during user auto-init refresh.
- Fail closed on unsafe targets and malformed active state while keeping batch cleanup best-effort.
