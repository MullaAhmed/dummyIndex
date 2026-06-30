# Equip — plan

`confidence: INFERRED`

## Bounded context

Equip owns one thing: turning a repo's `.context/` spine into a project-tuned
Claude Code toolkit on disk, then keeping that toolkit honest as it evolves. It
spans two packages split by a hard CLI boundary — **all reads/writes live in
`cli/equip/`; the domain under `context/domains/equip/` is pure**. Out of scope:
ingest/indexing (consumed read-only via `map/files.json` + convention docs), the
build skill (a downstream consumer of the manifest), and proposal authoring
(consumed via `--for-proposal`).

## Where it lives

Two halves, split by the CLI boundary:

- **Wire layer — `dummyindex/cli/equip/`** (parses flags, does every read/write,
  prints, returns exit codes):
  - `dispatch.py` (verb router + `apply` / `add-specialist`; `run`,
    `dispatch.py:96-134`).
  - `discover.py` (`discover` only — collection enumeration + ranking + the
    impersonation guard; ~375 lines). Owns the module-level `_RUNNER` seam.
  - `install.py` (`install` — native enable **and** the VENDOR skill path;
    `run_install` + record/wire helpers; reaches the runner via
    `discover._RUNNER` so the test monkeypatch surface is one source of truth).
  - `verbs.py` (status / refresh / reset / remove / uninstall / patch).
  - `plugin_state.py` (`verify` + declared-marketplace reads).
  - `common.py` (flag parsing, root resolution, grounding-doc filtering).
- **Policy layer — `dummyindex/context/domains/equip/`** (pure functions over
  frozen inputs; no I/O):
  - `models.py` / `enums.py` / `errors.py` / `constants.py` — frozen data,
    closed alphabets, typed error hierarchy, alphabets.
  - `generate/` — `detect.py` (stack/toolchain), `catalog.py` (the decision),
    `adopt.py` (generate-vs-adopt coverage), `specialists.py` (templated
    registry + invariants), `render.py` + `plan.py` (template fill),
    `proposal.py` (capability extraction), `gaps.py` (capability-gap analysis:
    `required(stack, proposal) − covered(manifest)`, pure/deterministic).
  - `lifecycle/` — `hashing.py`, `manifest.py`, `status.py` (classify / status /
    refresh / reset / uninstall, 420 lines), `evolve.py` (patch seam),
    `remove.py`.
  - `plugins/` — `marketplace.py` (catalog model + seed trust list),
    `sources.py` (gh I/O — the one impure module here: catalog fetch +
    `resolve_ref` (HEAD→sha), `list_skills` (collection enumeration), ref-pinned
    `fetch_file`), `discover.py` (match/rank), `install_plan.py`,
    `blast_radius.py`, `vendor.py` (`stamp_vendored` / `vendored_item` — now
    driven by `cli/equip/install.py`'s VENDOR branch).
  - `wiring/` — `hooks.py`, `safety.py` (`is_safe_to_write`).

Manifest lives at `.context/equipment.json` (`EQUIPMENT_REL`); settings wiring
targets `.claude/settings.json`. `equip install` also writes a third surface —
the committed `.context/config.json` `wired` list (declared intent) — via
`_write_back_wired` (`install.py`), upserting the matching `WiredEntry`
keyed on `<plugin>@<marketplace>`. `config.wired` is the declared desired set;
`equipment.json` is the render/lifecycle manifest; they are reconcilable on that
shared key and never merged. Write-back is project/local scope only and
skip-with-warning when no committed config exists.

## Architecture in three sentences

A wire-only CLI handler parses flags and drives a pure policy pipeline —
`detect_stack` → `build_catalog` (which calls `resolve_coverage` to split
capabilities into generate-vs-adopt) → `render_generated_set` → `_apply_write`,
which writes files, wires hooks, and merges the manifest. All decisions are pure
functions over a `StackProfile` + `PreflightReport` + convention docs returning a
frozen `CatalogDecision`; the CLI boundary owns every read/write
(`catalog.py:60-91`, `adopt.py:81-144`). The dominant pattern is **hash-baselined
never-clobber**: every generated file records an `origin_hash`, and the lifecycle
compares disk-hash to baseline to decide PRISTINE (safe to refresh/overwrite) vs
user-owned (skip forever).

## Patterns (named at path:range)

- **Hash-baselining (ownership oracle)** — `lifecycle/hashing.py:16-18`
  (`content_hash`) + `lifecycle/status.py:137-165` (`classify_item`). The sha256
  of rendered bytes is the sole authority for ownership. This is the load-bearing
  invariant every other lifecycle op rests on.
- **Manifest MERGE-never-rebuild** — `dispatch.py:381-400`, `:498-517`
  (`_apply_write`). A run carries forward every record it did not re-derive.
- **Generate-vs-adopt precedence ladder** — `adopt.py:81-144` (`resolve_coverage`);
  the proposal loop is `:120-141`, forced-cap bypass `:113-118`. Ordering: forced
  (templated) → project agent → generated template → registry specialist →
  generic implementer.
- **Stack-consistency gate** — `adopt.py:134-138` (inside `resolve_coverage`,
  `stack_frontend` guard) + `catalog.py:49-57` (`profile_has_frontend`); CLI
  surfacing at `dispatch.py:328-339`.
- **Trust-tier + blast-radius approval gate** — `install_plan.py:35-48`
  (`_plan_one`); the gate itself is `:42` (`requires_approval = not
  candidate.trusted`). Trust is sourced from the seed list / discovery path
  (`marketplace.py:49-64`, `SEED_MARKETPLACES`), never from candidate JSON.
- **Reserved-name impersonation guard** — `discover.py:57-59`
  (`_RESERVED_NAME_REPOS`) + the drop at `discover.py:104-123` (`_collect`
  rejects a catalog claiming a reserved name from the wrong repo).
- **Patch seam (sanctioned evolution)** — `evolve.py:25-70` (`apply_patch`):
  exact-once `old→new`, atomic write, re-baseline `origin_hash`, patch-bump
  version so the item stays PRISTINE while content legitimately differs.
- **Native-vs-vendor install mechanism** — `install_plan.py:37-39`: a candidate
  from a loose collection is `VENDOR` (copied via `plugins/vendor.py`);
  everything else is `NATIVE` (enabled via settings keys).
- **Safe-write guard** — `wiring/safety.py:1-33` (`is_safe_to_write`): the
  three-state ABSENT / OURS / USER-FILE check gating every file write.

## Data model

`.context/equipment.json` — `EquipmentManifest{schema_version, items:
tuple[EquipmentItem]}` (`models.py:222-244`), SCHEMA_VERSION currently 4
(`dispatch.py:7`). Each `EquipmentItem` (`models.py:80-158`) carries `kind` /
`name` / `path` / `source` / `capabilities` / `grounded_in`, plus optional fields
that drive subsystems:

- `version` + `origin_hash` — set only on file-backed GENERATED/VENDORED items;
  the hash-baseline lifecycle (`classify_item`, `status.py:137-165`) keys on
  these. `version` is `MAJOR.MINOR.PATCH`; a patch-level > 0 marks *evolved*
  (sanctioned patches), which `apply`/`refresh` preserve (`status.py:120-135`,
  `evolve.py:25-70`).
- `invariants` — load-bearing convention substrings a generated specialist must
  keep verbatim; a user edit that drops one classifies as INVARIANT_BROKEN rather
  than silent CUSTOMIZED (`status.py:137-165`, `specialists.py:104-184`). Omitted
  from `to_dict` when empty so v3 manifests stay byte-identical
  (`models.py:129-132`).
- `marketplace` / `origin_repo` / `origin_ref` / `mechanism` — set only on
  MARKETPLACE/VENDORED items; record provenance. `origin_ref` is documented as a
  pinned commit sha and is deliberately left `None` for native plugins (the
  listing semver is never a git ref — `discover.py:580-583`).

`StackProfile` (`models.py:43-77`) is the eight-field toolchain derived
deterministically (no LLM) from `map/files.json` language counts + a raw-manifest
token scan (`detect.py:90-216`).

## Dependencies

- **Upstream (equip consumes):** `map/files.json` + convention docs from ingest
  (read-only, via `detect_stack`); `PreflightReport` (`preflight/models.py`);
  proposal text under `.context/proposals/` (via `proposal.py`, only when
  `--for-proposal`); `context/domains/atomic_io.write_text_atomic` (every write).
- **Downstream (consumes equip):** the build skill reads `.context/equipment.json`
  to dispatch tuned agents; `.claude/settings.json` consumers (the format hook);
  the generated `.md` agents/skills under `.claude/`.
- **Cross-cutting / impure leaf:** `plugins/sources.py` is the only domain module
  doing I/O (gh calls), deliberately isolated so the rest of `plugins/` stays
  pure and testable with a fake runner.
- **Cycles:** none observed — the CLI layer depends on the domain, never the
  reverse; `lifecycle/evolve.py` imports `status._bump` / `is_lifecycle_managed`
  (same package, downward).

## Key decisions (decided X because Y)

- **Decided origin-hash baselining over a sentinel marker** because a sentinel is
  forgeable and the rendered-bytes sha256 is not. Equal ⇒ ours, different ⇒ user
  owns it, absent ⇒ MISSING; the in-body `<!-- dummyindex:generated -->` sentinel
  is a human marker only (`hashing.py:1-18`, `status.py:6-23`).
- **Decided the manifest write is a MERGE, not a rebuild** because a plain `apply`
  must never silently drop a prior plugin or specialist a run did not re-derive
  (`dispatch.py:381-400`, `:498-517`).
- **Decided forced caps generate before the project-agent preference** because an
  explicit `add-specialist` (or a carried-forward applied specialist) is an
  intentional ask that should beat an incidentally-covering project agent — but a
  grounded template still supersedes a registry adoption, since a real specialist
  beats a manifest pointer (`adopt.py:81-144`).
- **Decided trust comes from the seed list / discovery path, never the JSON**
  because declared surfaces are attacker-controlled, so trust must be unspoofable
  (`marketplace.py:49-64`, `install_plan.py:1-9`). Hence any untrusted source
  requires `--yes` regardless of a `runs_code=False` claim (`install_plan.py:35-48`).
- **Decided reserved seed names from a foreign repo are rejected** because a
  catalog claiming `anthropics/skills`' name from another repo is impersonation
  (`discover.py:57-59`, `:104-123`).
- **Decided a backend-only stack never adopts a Frontend Developer off plan-text
  keywords**, and the skip is surfaced not silent, because plan prose mentioning
  "UI" must not contaminate a FastAPI repo's toolkit (`catalog.py:49-57`,
  `adopt.py:132-138`, `dispatch.py:328-339`).
- **Decided the patch seam is the only sanctioned evolution path** because it
  re-baselines the hash and patch-bumps the version, keeping the item PRISTINE
  while its content legitimately diverges from a fresh render — any other edit
  classifies as USER_MODIFIED (`evolve.py:25-70`).

## Open questions

Both prior open questions are now **resolved** (proposal `equip-auto-vendor-skills`):

- **VENDOR install path — now wired.** `run_install` lives in `cli/equip/install.py`
  (extracted from `discover.py` to hold the split threshold) and branches on
  `pi.mechanism is VENDOR`: `_run_vendor_install` resolves the collection repo's
  HEAD to a **pinned commit sha** (`sources.resolve_ref`), fetches the skill's
  `SKILL.md` at that sha (`fetch_file(ref=…)`), stamps it (`vendor.stamp_vendored`),
  writes it to `.claude/skills/<name>/SKILL.md` under the never-clobber guard, and
  records a VENDORED item (`vendor.vendored_item`, `origin_ref=sha`,
  `mechanism=vendor`). `_collect_catalogs` now enumerates `is_collection` seeds
  (`_collection_catalog` → `sources.list_skills`) instead of skipping them, so a
  collection skill is an installable candidate. A path-safety guard rejects a
  separator/traversal skill name.
- **`_needed_caps` — now manifest-aware.** It delegates to the pure
  `generate/gaps.py:capability_gaps` (`required(stack, proposal) − covered(manifest)`,
  deterministic `Capability` order). Proposal-scoped *specialist* gaps are threaded
  in by the plan-time caller; the build loop emits a `missing_capability` signal on
  a true specialist fallback (`cli/build_loop/waves.py`).

Remaining (unchanged): the **native** install path still records `origin_ref=None`
(moving-HEAD) — see `concerns.md`; only the vendor path pins a sha so far.
