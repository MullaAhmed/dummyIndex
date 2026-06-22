# Equip — plan

`confidence: INFERRED`

## Where it lives

Two halves, split by the CLI boundary:

- **Wire layer** — `dummyindex/cli/equip/`: `dispatch.py` (verb router +
  apply/add-specialist), `discover.py` (discover/install), `verbs.py`
  (status/refresh/reset/remove/uninstall/patch), `plugin_state.py` (verify +
  declared-marketplace reads), `common.py` (flag parsing, root resolution,
  grounding-doc filtering). Each handler parses its own flags, calls the domain,
  prints, returns an exit code (`dispatch.py:20-29`).
- **Policy layer** — `dummyindex/context/domains/equip/`:
  - `models.py` / `enums.py` / `errors.py` / `constants.py` — data + alphabets.
  - `generate/` — `detect.py` (stack/toolchain), `catalog.py` (the decision),
    `adopt.py` (generate-vs-adopt coverage), `specialists.py` (templated
    specialist registry), `render.py` + `plan.py` (template fill), `proposal.py`
    (capability extraction).
  - `lifecycle/` — `hashing.py`, `manifest.py`, `status.py` (classify/status/
    refresh/reset/uninstall), `evolve.py` (patch seam), `remove.py`.
  - `plugins/` — `marketplace.py` (catalog model + seeds), `sources.py` (gh I/O),
    `discover.py` (match/rank), `install_plan.py`, `blast_radius.py`,
    `vendor.py`.
  - `wiring/` — `hooks.py`, `safety.py` (`is_safe_to_write`).

Manifest lives at `.context/equipment.json` (`EQUIPMENT_REL`); settings wiring
targets `.claude/settings.json`.

## Architecture in three sentences

A wire-only CLI handler parses flags and drives a pure policy pipeline —
`detect_stack` → `build_catalog` (which calls `resolve_coverage` to split
capabilities into generate-vs-adopt) → `render_generated_set` → `_apply_write`,
which writes files, wires hooks, and merges the manifest. All decisions are pure
functions over a `StackProfile` + `PreflightReport` + convention docs returning a
frozen `CatalogDecision`; the CLI boundary owns every read/write
(`catalog.py:1-21`, `adopt.py:81-144`). The dominant pattern is **hash-baselined
never-clobber**: every generated file records an `origin_hash`, and the
lifecycle compares disk-hash to baseline to decide PRISTINE (safe to
refresh/overwrite) vs user-owned (skip forever).

## Data model

`.context/equipment.json` — `EquipmentManifest{schema_version, items:
tuple[EquipmentItem]}` (`models.py:222-244`), SCHEMA_VERSION currently 4
(`dispatch.py:7`). Each `EquipmentItem` (`models.py:80-158`) carries `kind` /
`name` / `path` / `source` / `capabilities` / `grounded_in`, plus optional fields
that drive subsystems:

- `version` + `origin_hash` — set only on file-backed GENERATED/VENDORED items;
  the hash-baseline lifecycle (`classify_item`, `lifecycle/status.py:137-165`)
  keys on these. `version` is `MAJOR.MINOR.PATCH`; a patch-level > 0 marks
  *evolved* (sanctioned patches), which `apply`/`refresh` preserve
  (`status.py:120-135`, `evolve.py:25-70`).
- `invariants` — load-bearing convention substrings a generated specialist must
  keep verbatim; a user edit that drops one classifies as INVARIANT_BROKEN
  rather than silent CUSTOMIZED (`status.py:137-165`, `specialists.py:104-184`).
  Omitted from `to_dict` when empty so v3 manifests stay byte-identical
  (`models.py:129-132`).
- `marketplace` / `origin_repo` / `origin_ref` / `mechanism` — set only on
  MARKETPLACE/VENDORED items; record provenance. `origin_ref` is documented as a
  pinned commit sha and is deliberately left `None` for native plugins (the
  listing semver is never a git ref — `discover.py:580-583`).

`StackProfile` (`models.py:43-77`) is the eight-field toolchain derived
deterministically (no LLM) from `map/files.json` language counts + a raw-manifest
token scan (`detect.py:90-216`).

## Key decisions

- **Origin-hash baselining over a sentinel marker.** The sha256 of rendered bytes
  is the authority for ownership; the in-body `<!-- dummyindex:generated -->`
  sentinel is only a human marker (`hashing.py:1-18`, `status.py:6-23`). Equal ⇒
  ours, different ⇒ user owns it, absent ⇒ MISSING. This is the load-bearing
  invariant the whole refresh/reset/patch lifecycle rests on.
- **Manifest write is a MERGE, never a rebuild.** Records a run does not
  re-derive (marketplace/vendored/adopted/stale-generated) carry forward
  verbatim, so a plain `apply` never silently drops a prior plugin or specialist
  (`dispatch.py:381-400`, `:498-517`).
- **Generate-vs-adopt precedence** (`adopt.py:81-144`): forced caps generate
  first, then per proposal capability — project agent → generated template →
  registry specialist → generic implementer. A grounded template supersedes a
  registry adoption (a real specialist beats a manifest pointer).
- **Trust tiers + blast radius for plugins.** Trust comes from the seed
  list/discovery path, never the JSON, so it is unspoofable
  (`marketplace.py:43-64`, `install_plan.py:1-9`). Any untrusted source requires
  `--yes` regardless of a `runs_code=False` claim — declared surfaces are
  attacker-controlled (`install_plan.py:35-48`). Reserved seed names from a
  different repo are rejected as impersonation (`discover.py:57-59`, `:104-123`).
- **Stack-consistency gate.** A backend-only repo never adopts a Frontend
  Developer off plan-text keywords; the skip is surfaced, not silent
  (`catalog.py:49-57`, `adopt.py:132-138`, `dispatch.py:328-339`).
- **Patch seam as the only sanctioned evolution path.** `apply_patch` requires an
  exact-once `old→new` match, re-baselines the hash, and patch-bumps the version
  so the item stays PRISTINE while its content legitimately differs from a fresh
  render (`evolve.py:25-70`).

## Open questions

- The VENDOR install path is referenced as a later slice in `discover.py:8`; only
  the NATIVE enable path is wired in `run_install`. The vendor mechanism
  (`plugins/vendor.py`) exists and is exercised by tests — confirm whether
  `install` ever reaches it or whether vendoring is driven only by `apply`/
  adoption flows.
- `_needed_caps` (`discover.py:267-276`) is explicitly a "deliberately simple"
  auto-match stub; the richer gap analysis against the existing manifest is
  flagged as a fast-follow and not yet present.
