# Shared project capabilities and native discovery — plan

`confidence: INFERRED`

## Bounded context

Equip prepares and maintains capability bodies plus `.context/equipment.json` registry. Canonical bodies: `.context/equipment/<name>.md`. Optional Claude files are discovery pointers, not another implementation (`dummyindex/context/domains/equip/generate/catalog.py:40`, `dummyindex/context/domains/equip/generate/adapters.py:18-42`).

CLI owns preparation and lifecycle orchestration. Domain modules own stack analysis, catalog decisions, rendering, hash classification and patches. Host workflows execute selected mandates; installer linking and plugin trust stay separate. No optimizer service or model-execution engine.

## Preparation pipeline and patterns

1. `run_apply` defaults to portable `agents` and resolves flags and root (`dummyindex/cli/equip/dispatch.py:176-224`). `_run_apply` reads prior equipment, stack and conventions. It asks `build_catalog` for core four, specialists and formatter-hook intent (`dummyindex/cli/equip/dispatch.py:280-422`, `dummyindex/context/domains/equip/generate/catalog.py:67-144`).
2. `render_generated_set` emits `(EquipmentItem, path, content)` triples. It strips native tool-permission metadata and records template identity apart from project bindings (`dummyindex/context/domains/equip/generate/plan.py:29-145`).
3. `source_rendered` swaps eligible triples before dry-run or apply (`dummyindex/cli/equip/source.py:274-357`). Pure policy: `plugins/sourcing.py`, `generate/sourced.py`. Network runs only via `discover._RUNNER`, so `--dry-run --source` still fetches. Limits: five SKILL.md fetches per channel per target, three GitHub searches per run.
4. Dry-run previews the same decisions without writes. Apply preserves user-owned and evolved bodies, and keeps pristine sourced bodies (`dummyindex/cli/equip/dispatch.py:423-486`, `dummyindex/cli/equip/dispatch.py:557-570`). It checks a new canonical destination independently and merges prior records into the registry. Only pristine legacy migration replaces a recorded old native body (`dummyindex/context/domains/equip/generate/adapters.py:54-89`). Apply then stores `--lesson-file` agent bodies (`dummyindex/cli/equip/dispatch.py:219-221`).

## Lifecycle and ownership decisions

**Hash-based ownership**: equal baseline means pristine; changed content stays user-owned. Specialist invariant strings distinguish harmless customization from invariant alarm, but authorize neither overwrite nor rebaselining (`dummyindex/context/domains/equip/lifecycle/status.py:143-173`). Manifest invariants are metadata; pristine templates must already contain them (`dummyindex/context/domains/equip/generate/plan.py:50-62`, `tests/context/domains/equip/test_equip_specialist_invariants.py:69-104`).

**Sourced items**: `is_sourced` (`dummyindex/context/domains/equip/lifecycle/status.py:138-140`) marks upstream bodies, not templates. Refresh never rewrites them (`status.py:269`). Reset clears origin fields (`status.py:355-362`).

`apply_patch` is the exact-once learning seam: replace one occurrence, update frontmatter/content and baseline/version, persist manifest. Refresh and reset reuse `fresh_rendered`, as apply does. Evolved or user-owned bodies never silently become fresh templates (`dummyindex/context/domains/equip/lifecycle/evolve.py:26-71`, `dummyindex/cli/equip/common.py:199-245`, `dummyindex/context/domains/equip/lifecycle/status.py:222-357`).

The specialist library (`lifecycle/library.py`) stores body and lesson separately. `reuse_capability` restores body to manifest path and re-baselines a recorded `origin_hash` (`dummyindex/context/domains/equip/lifecycle/library.py:191-216`). `reverify` returns `needs-reverify` on any changed body or grounding hash (`library.py:219-233`).

Each file write is atomic, not the operation (`dummyindex/context/domains/equip/lifecycle/status.py:352`). Apply restores converted legacy pointers only on later required-write failures. Canonical files, settings and registry have no shared rollback (`dummyindex/cli/equip/dispatch.py:519-530`, `dispatch.py:607-608`, `dispatch.py:719-721`).

## Dependencies and feedback

Upstream: context spine, conventions, project commands, prior manifest, proposal capability requests. Downstream build dispatch uses each recorded `role_path`, including a preserved legacy path (`dummyindex/cli/build_loop/waves.py:320-336`). It never assigns domain-dimension agents as build targets (`waves.py:183-185`). `capability_identity` hashes loaded bytes; qualification also accepts matching baseline with normalized newlines (`dummyindex/context/domains/equip/identity.py:31-56`).

Build/host learning returns explicit patches: artifact feedback, not proof a model obeyed the mandate. Adapters point at that body; never second learning target. Recorded capability/policy hashes are attributable inputs, not measured quality gains.

## Verification seam

Adapter and shared-preparation tests cover migration, collisions and preservation: `tests/context/domains/equip/test_equip_adapters.py` and `tests/cli/equip/test_shared_preparation.py`. Specialist round trips distinguish deleted invariant from cosmetic edit (`tests/context/domains/equip/test_equip_specialist_invariants.py:121-155`). `tests/context/domains/equip/test_capability_identity.py` covers loaded identity, legacy newlines and lifecycle package metadata. Library tests: `tests/context/domains/equip/test_equip_library.py` and `tests/cli/equip/test_equip_reuse.py`. Sourcing tests: `tests/cli/equip/test_equip_source_apply.py`, `tests/context/domains/equip/test_equip_sourcing.py` and `tests/context/domains/equip/test_equip_sourced.py`.
