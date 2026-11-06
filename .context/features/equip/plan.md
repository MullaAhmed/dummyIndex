# Shared project capabilities and native discovery — plan

`confidence: INFERRED`

## Bounded context

Equip prepares and maintains project capability bodies plus the
`.context/equipment.json` registry. Canonical generated bodies live at
`.context/equipment/<name>.md`; optional Claude files are discovery pointers,
not another capability implementation
(`dummyindex/context/domains/equip/generate/catalog.py:113-143`,
`dummyindex/context/domains/equip/generate/adapters.py:18-42`).

The CLI owns preparation/lifecycle orchestration. Domain modules own stack
analysis, catalog decisions, rendering, hash classification and patches. Shared
host workflows execute the selected mandates; installer skill linking and native
plugin installation/settings trust remain separate boundaries. This feature
does not own an optimizer service or model-execution engine.

## Preparation pipeline and patterns

1. `run_apply` defaults to portable `agents` and resolves flags/root. Preparation
   reads prior equipment, preflight inventory, stack and conventions, then asks
   `build_catalog` for the core four, template-backed specialists, adoptions and
   formatter-hook intent (`dummyindex/cli/equip/dispatch.py:169-199`,
   `dummyindex/cli/equip/dispatch.py:257-345`,
   `dummyindex/context/domains/equip/generate/catalog.py:74-110`). This is a
   decision/render/write pipeline; the pure catalog does not mutate the project.
2. `render_generated_set` emits `(EquipmentItem, path, content)` triples. It
   removes native tool-permission metadata, uses actual-changed-path placeholders
   for shared formatting, and records reusable template identity separately from
   project bindings and rendered-body hashes
   (`dummyindex/context/domains/equip/generate/plan.py:29-145`).
3. Dry-run previews the same ownership decisions without writes. Apply preserves
   user-owned/evolved bodies, independently checks a new canonical destination,
   writes eligible files and merges prior records into the registry. Known-content
   native adapters reference canonical bodies; pristine legacy migration is the
   only path for replacing a recorded old native body
   (`dummyindex/cli/equip/dispatch.py:385-553`,
   `dummyindex/cli/equip/dispatch.py:560-687`,
   `dummyindex/context/domains/equip/generate/adapters.py:54-89`).

## Lifecycle and ownership decisions

**Hash-based ownership** is explicit: equal baseline means pristine; changed
content stays user-owned. Specialist invariant strings distinguish harmless
customization from an invariant alarm but authorize neither overwrite nor
rebaselining (`dummyindex/context/domains/equip/lifecycle/status.py:138-167`).
Manifest invariants are metadata and do not change rendered bytes; pristine
specialist templates must already contain them
(`dummyindex/context/domains/equip/generate/plan.py:50-62`,
`tests/context/domains/equip/test_equip_specialist_invariants.py:69-104`).

`apply_patch` is the exact-once learning seam: replace one occurrence, update
frontmatter/content and baseline/version, then persist the manifest. Refresh and
reset reuse `fresh_rendered`, the same detection/catalog/render route as apply;
evolved or user-owned bodies do not silently become fresh templates
(`dummyindex/context/domains/equip/lifecycle/evolve.py:26-71`,
`dummyindex/cli/equip/common.py:199-245`,
`dummyindex/context/domains/equip/lifecycle/status.py:217-357`).

Each file write can be atomic without making the whole operation transactional.
Apply restores converted legacy pointers on specified later required-write
failures; new canonical files, settings and the registry do not share one global
rollback. Keeping partial progress and warnings is the implemented tradeoff
(`dummyindex/cli/equip/dispatch.py:467-478`,
`dummyindex/cli/equip/dispatch.py:551-553`,
`dummyindex/cli/equip/dispatch.py:617-687`).

## Dependencies and feedback

Upstream are the context spine, conventions, detected project commands, prior
manifest and optional proposal capability requests. Downstream build dispatch
uses each recorded `role_path`, including a preserved legacy path
(`dummyindex/cli/build_loop/waves.py:320-336`). `capability_identity` reads actual
loaded bytes; qualification additionally requires a matching baseline, permitting
normalized legacy line endings
(`dummyindex/context/domains/equip/identity.py:26-56`).

Build/host learning may return an explicit patch to equip's lifecycle; this is
artifact feedback through the manifest/body pair, not proof a model obeyed the
mandate. Native adapters depend on that same body and never become a second
learning target. Recording capability/policy hashes establishes attributable
inputs, not measured agent-quality improvement.

## Verification seam

Adapter/shared-preparation tests cover migration, collisions and preservation:
`tests/context/domains/equip/test_equip_adapters.py` and
`tests/cli/equip/test_shared_preparation.py`. The specialist round trips distinguish
a deleted invariant from a cosmetic edit
(`tests/context/domains/equip/test_equip_specialist_invariants.py:121-155`).
`tests/context/domains/equip/test_capability_identity.py` covers loaded identity,
legacy newlines and lifecycle package metadata. The deterministic boundary checks
remain separate from host behavior or paid model experiments.
