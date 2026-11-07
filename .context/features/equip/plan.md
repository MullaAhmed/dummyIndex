# Shared project capabilities and native discovery — plan

`confidence: INFERRED`

Paths drop the leading `dummyindex/` (except `tests/`, `.context/`,
`pyproject.toml`); `equip/` stands for `context/domains/equip/`.

## Where it lives

- **Domain core:** `equip/generate/` decides and renders
  (`equip/generate/catalog.py:58-121`, `equip/generate/plan.py:24-120`, pointers
  `equip/generate/adapters.py:18-106`); `equip/lifecycle/` classifies and mutates
  (`equip/lifecycle/status.py:62-408`, `equip/lifecycle/evolve.py:23-68`).
- **CLI shell:** apply/write/merge `cli/equip/dispatch.py:143-679`; shared
  re-render `fresh_rendered` `cli/equip/common.py:190-230`.
- **Not this boundary:** plugin discover/install/verify (`cli/equip/install.py`,
  `equip/plugins/`, own settings/trust rules); skill linking (`install-surface`).
- **Upstream:** `.context/` spine, preflight, proposal capabilities
  (`cli/equip/dispatch.py:263-296`); `write_text_atomic`; `wire_hooks`.
- **Downstream:** build routing emits manifest `path` as `role_path`
  (`cli/build_loop/waves.py:197,282-295`); `task_binding` binds it via
  `capability_identity` (`context/domains/buildloop/envelopes.py:76-107`); evolve
  promotion re-baselines bodies (`context/domains/evolve_gate.py:254-325`);
  reinstall runs `fresh_rendered` + `refresh`
  (`installer/install/project_init.py:164-192`).
- **Cycles:** `cli ↔ installer` (`dummyindex/cli/equip/dispatch.py:48`;
  `installer/install/project_init.py:174`, lazy) and `generate ↔ lifecycle` are
  package-level only: `dummyindex/installer/common.py:11` imports just `..versioning`, and
  `generate` imports just the leaf `equip/lifecycle/hashing.py`.

## Architecture in three sentences

**Functional core, imperative shell:** `_run_apply` reads prior manifest,
preflight, stack and conventions once, then calls the pure `build_catalog`
("Pure; no I/O", `dummyindex/context/domains/equip/generate/catalog.py:67`) and write-free
`render_generated_set`, which returns `(EquipmentItem, rel_path, content)` triples
(`cli/equip/dispatch.py:231-319`). `_apply_write` gates each target through
**hash-baselined ownership** (`equip/lifecycle/status.py:123-162`), writes
bodies, does a **merge-forward registry write**, and last writes
**discovery-pointer adapters** (`cli/equip/dispatch.py:450-655`). Refresh/reset
re-enter via `fresh_rendered`, "the single render path"
(`equip/generate/plan.py:3-5`), so they compare against what apply would write.

## Data model

- `.context/equipment.json` = `EquipmentManifest` v4 (`dummyindex/context/domains/equip/constants.py:13`);
  unknown enums raise `EquipError`, never overwrite
  (`equip/lifecycle/manifest.py:21-44`). Bodies at `.context/equipment/<name>.md`
  (`dummyindex/context/domains/equip/generate/catalog.py:26`); pointers only for generated items there
  (`equip/generate/adapters.py:18-30`).
- `EquipmentItem` (`equip/models.py:72-108`) keeps four field groups apart:
  ownership (`path`, `version`, `origin_hash`, `invariants`); package identity
  (`PACKAGE_FIELDS`, `equip/identity.py:10-19`) and `project_binding`, both
  stamped at `equip/generate/plan.py:94-117`; plugin provenance
  (`equip/models.py:97-100`).
- `origin_hash` hashes decoded text (`equip/lifecycle/hashing.py:17-19`,
  `equip/lifecycle/status.py:135-140`); byte-faithful `write_text_atomic` keeps it
  stable (`context/domains/atomic_io.py:70-79`). `capability_identity` returns
  raw-byte SHA256, accepting either form (`equip/identity.py:36-44`). No
  transaction spans files.

## Key decisions

- **Decided** a recorded hash owns only its recorded path, because a sentinel or
  old baseline must not claim a foreign destination: user-owned bodies are never
  rewritten or re-baselined (`equip/lifecycle/status.py:149-162`,
  `cli/equip/dispatch.py:460-474`); a new destination is checked independently
  (`cli/equip/dispatch.py:496-510`).
- **Decided** invariants are manifest metadata only, because in-body they would
  shift `origin_hash` (`equip/generate/plan.py:37-39`); they refine a user-owned
  verdict, never authorize overwrite (`equip/lifecycle/status.py:142-146`).
- **Decided** evolution = exact-once patch + patch-level bump, so the body stays
  PRISTINE yet is never re-rendered (`equip/lifecycle/status.py:106-120`,
  `cli/equip/dispatch.py:475-485`). Only `reset` discards evolution or user edits
  (`equip/lifecycle/status.py:303-333`). Evolve promotion is a second writer under
  the same rule (`context/domains/evolve_gate.py:306-322`).
- **Decided** native files are pointers: "Keep workflow and policy text
  exclusively in the canonical file" (`equip/generate/adapters.py:33-42`); a
  legacy body migrates only on an exact recorded-hash match
  (`equip/generate/adapters.py:80-86`, `cli/equip/dispatch.py:532-554`).
- **Decided** the manifest write merges, never rebuilds, so no record silently
  drops (`cli/equip/dispatch.py:423-425,606-628`).
- **Decided** partial progress over rollback: files precede hooks "so malformed
  settings never blocks them" (`dummyindex/cli/equip/dispatch.py:581`); restore reverts only
  converted legacy pointers (`cli/equip/dispatch.py:437-448,521-523,630-635`).

## Open questions

- **Junction guard:** duplicated `_has_symlink_parent`
  (`equip/generate/adapters.py:45-51`, `cli/equip/dispatch.py:682-688`) needs
  `is_junction` (3.12+), so on 3.10/3.11 (`pyproject.toml:13`) a Windows junction
  parent passes; fail-closed `is_link` (`context/domains/atomic_io.py:16-34`)
  serves only `context/build/upgrade.py`.
- **Newlines:** ownership compares decoded text (`equip/generate/adapters.py:75`)
  but `_matches_content` compares raw bytes (`cli/equip/dispatch.py:691-695`), so
  a CRLF copy of our own body at a new path is skipped as foreign.
- **Layering:** `cli/` should be wire-only
  (`.context/conventions/folder-organization.md:30-36`), yet write/preserve/merge
  policy sits in `cli/equip/dispatch.py:410-679` (783-line file), and
  `fresh_rendered` in `cli/` forces the installer→cli edge.
- **Private import:** `context/domains/evolve_gate.py:260` imports equip's
  `_bump`; public re-baseline seam?
