# Project equipment toolkit — implementation

confidence: INFERRED

## Source map

| Path under `dummyindex/` | Responsibility |
|---|---|
| `context/domains/equip/generate/detect.py` | Detect stack and portable project commands. |
| `context/domains/equip/generate/catalog.py`, `specialists.py`, `adopt.py` | Decide generated capabilities, specialist coverage and adoption. |
| `context/domains/equip/generate/plan.py`, `render.py` | Render canonical bodies and create their hash-baselined records. |
| `context/domains/equip/generate/adapters.py` | Preview/write/remove exact-byte-owned native discovery pointers. |
| `context/domains/equip/identity.py` | Read package/binding identity and actual guidance bytes before qualification. |
| `context/domains/equip/lifecycle/` | Manifest, classification, refresh/reset/patch/remove/uninstall. |
| `cli/equip/dispatch.py` | Apply, safe legacy migration, optional native extras and manifest merge. |
| `cli/equip/verbs.py` | Status and lifecycle command boundaries. |
| `cli/build_loop/waves.py` | Emit the selected capability's `role_path` for delegation. |
| `skills/equip/SKILL.md`, `skills/plan/SKILL.md`, `skills/build/SKILL.md` | Shared host orchestration, verification and selected-policy propagation. |

## Preparation flow

1. `run_apply` normalizes the selected platform (default `agents`) and resolves
   the project. `_run_apply` reads the prior manifest, preflight inventory,
   detected stack, convention paths and optional proposal capabilities.
2. `build_catalog` decides generation/adoption/hooks; `render_generated_set`
   produces `(EquipmentItem, relative_path, content)` triples. Generated paths
   are canonical and their shared bodies omit native tool-permission metadata.
   Formatter placeholders require actual named changed paths at execution time.
3. `_apply_dry_run` reports the same native ownership decisions without writes.
   `_apply_write` independently checks the source baseline and new destination,
   preserves modified/evolved legacy records and writes eligible canonical
   bodies atomically. Only proven pristine legacy native bodies become pointers.
4. Apply merges generated, adopted, hook and prior records into the existing
   registry. Native extras are requested explicitly. Pointer warnings remain
   visible; migration recovery restores converted legacy bodies when a later
   required write fails. There is no transaction covering every file/settings
   write; see `concerns.md`.

The renderer and registry remain the existing lifecycle seams. No parallel
Codex capability implementation or new optimizer/evaluation service is added.
Installer skill-family linking remains owned by `installer/`; native plugin
policy remains owned by the existing plugin/settings modules.

## Use and learning

Build's deterministic mapper chooses a capability and returns its recorded
`role_path`, including a preserved legacy path. The host reads that body and
passes its mandate, task scope, grounding, verification expectations and any
actually selected session policies to a callable native agent or generic
fallback. The CLI supplies routing metadata; the host performs delegation and
verification.

A durable correction uses
`dummyindex/context/domains/equip/lifecycle/evolve.py:apply_patch` through `equip patch`.
The replacement must match exactly once; the write updates content, version and
hash together. Refresh and reset reuse the same detect/catalog/render path
through
`dummyindex/cli/equip/common.py:fresh_rendered`, so learned bodies remain distinct
from fresh template output. Refresh/reset update source-package metadata from the
same render, without rebasing edited or evolved bodies. Existing manifests with
no package identity remain readable and make no invented package claim.

## Checks

- `tests/context/domains/equip/test_equip_adapters.py`: pointer ownership,
  preview, invalid UTF-8 and symlink refusal.
- `tests/cli/equip/test_shared_preparation.py`: canonical/default preparation,
  explicit native extras, migration collisions and lifecycle preservation.
- `tests/context/domains/equip/test_equip.py`,
  `tests/context/domains/equip/test_equip_specialists.py`,
  `tests/context/domains/equip/test_equip_e2e.py`: portable commands, generated coverage and the full
  hash-owned lifecycle.
- `tests/context/domains/test_build_loop.py`: canonical and preserved legacy
  mandate paths through both dispatch verbs.
- `tests/test_skills_doc_hygiene.py`: shared workflow and policy instructions.

No model-dependent run is required by these deterministic checks.

Package identity and two-project reuse are exercised by
`tests/context/domains/equip/test_capability_identity.py`, including changed-body
rejection, legacy CRLF loading and refresh/reset source metadata.
