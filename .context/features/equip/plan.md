# Shared project capabilities and native discovery — plan

`confidence: INFERRED`

## Bounded context

Equip prepares and maintains project capability bodies plus the
`.context/equipment.json` registry. Canonical generated bodies live at
`.context/equipment/<name>.md`; optional Claude files are discovery pointers,
not another capability implementation
(`dummyindex/context/domains/equip/generate/catalog.py:40`,
`dummyindex/context/domains/equip/generate/adapters.py:18-42`).

The CLI owns preparation/lifecycle orchestration. Domain modules own stack
analysis, catalog decisions, rendering, hash classification and patches. Host
workflows execute selected mandates; installer linking and plugin trust stay
separate. This feature
does not own an optimizer service or model-execution engine.

## Preparation pipeline and patterns

1. `run_apply` defaults to portable `agents` and resolves flags/root. Preparation
   reads prior equipment, preflight inventory, stack and conventions, then asks
   `build_catalog` for the core four, undimensioned and signalled dimensioned
   specialists, adoptions and formatter-hook intent
   (`dummyindex/cli/equip/dispatch.py:169-199`,
   `dummyindex/cli/equip/dispatch.py:257-345`,
   `dummyindex/context/domains/equip/generate/catalog.py:67-144`). The pure
   catalog does not mutate the project.
2. `render_generated_set` emits `(EquipmentItem, path, content)` triples. It
   strips native tool-permission metadata and records template identity apart
   from project bindings and body hashes
   (`dummyindex/context/domains/equip/generate/plan.py:29-145`).
3. Dry-run previews the same ownership decisions without writes. Apply preserves
   user-owned/evolved bodies, independently checks a new canonical destination,
   writes eligible files and merges prior records into the registry. Known-content
   native adapters reference canonical bodies; pristine legacy migration is the
   only path for replacing a recorded old native body
   (`dummyindex/cli/equip/dispatch.py:385-553`,
   `dummyindex/cli/equip/dispatch.py:560-687`,
   `dummyindex/context/domains/equip/generate/adapters.py:54-89`). Non-dry apply
   then stores `--lesson-file` agent bodies (`dispatch.py:204-215`,
   `dispatch.py:709-711`).

## Lifecycle and ownership decisions

**Hash-based ownership** is explicit: equal baseline means pristine; changed
content stays user-owned. Specialist invariant strings distinguish harmless
customization from an invariant alarm but authorize neither overwrite nor
rebaselining (`dummyindex/context/domains/equip/lifecycle/status.py:138-167`).
Manifest invariants are metadata; pristine templates must already contain them
(`dummyindex/context/domains/equip/generate/plan.py:50-62`,
`tests/context/domains/equip/test_equip_specialist_invariants.py:69-104`).

`apply_patch` is the exact-once learning seam: replace one occurrence, update
frontmatter/content and baseline/version, then persist the manifest. Refresh and
reset reuse `fresh_rendered`, the same detection/catalog/render route as apply;
evolved or user-owned bodies do not silently become fresh templates
(`dummyindex/context/domains/equip/lifecycle/evolve.py:26-71`,
`dummyindex/cli/equip/common.py:199-245`,
`dummyindex/context/domains/equip/lifecycle/status.py:217-357`).

The specialist library (`lifecycle/library.py`) stores body and lesson separately.
`reuse_capability` restores a body to its manifest path and re-baselines a
recorded `origin_hash` (`library.py:191-216`). `reverify` returns
`needs-reverify` on any changed body or grounding hash (`library.py:219-233`).

Each file write is atomic, not the operation. Apply restores converted legacy
pointers only on specified later required-write failures; canonical files,
settings and the registry have no shared rollback
(`dummyindex/cli/equip/dispatch.py:467-478`,
`dispatch.py:551-553`, `dispatch.py:617-687`).

## Dependencies and feedback

Upstream: context spine, conventions, project commands, prior manifest,
proposal capability requests. Downstream build dispatch uses each recorded
`role_path`, including a preserved legacy path
(`dummyindex/cli/build_loop/waves.py:320-336`), and never assigns
domain-dimension agents as build targets (`waves.py:183-185`).
`capability_identity` hashes loaded bytes; qualification also accepts a matching
baseline with normalized newlines
(`dummyindex/context/domains/equip/identity.py:26-56`).

Build/host learning returns explicit patches: artifact feedback, not proof a
model obeyed the mandate. Adapters point at that body; never a second learning
target. Recorded
capability/policy hashes are attributable inputs, not measured quality gains.

## Verification seam

Adapter/shared-preparation tests cover migration, collisions and preservation:
`tests/context/domains/equip/test_equip_adapters.py` and
`tests/cli/equip/test_shared_preparation.py`. The specialist round trips distinguish
a deleted invariant from a cosmetic edit
(`tests/context/domains/equip/test_equip_specialist_invariants.py:121-155`).
`tests/context/domains/equip/test_capability_identity.py` covers loaded identity,
legacy newlines and lifecycle package metadata. Library tests live in
`tests/context/domains/equip/test_equip_library.py` and
`tests/cli/equip/test_equip_reuse.py`. Deterministic boundary checks stay separate
from host behavior or paid model experiments.
