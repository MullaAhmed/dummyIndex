# Project equipment toolkit — spec

confidence: INFERRED

## Intent

Prepare the same project capabilities for every host, while preserving user
ownership across generation, refresh and learning. The registry is
`.context/equipment.json`; generated bodies live at
`.context/equipment/<name>.md`. Native discovery files reference those bodies
instead of carrying another implementation.

## Behavior

- `dummyindex context equip apply` prepares the implementer, tester, reviewer,
  verify capability and every undimensioned template-backed specialist.
  Dimensioned specialists (frontend, api, migration, ci) need a signal: stack
  evidence for frontend and api, otherwise a proposal or explicit ask
  (`dummyindex/context/domains/equip/generate/catalog.py:67-79`,
  `:100-144`). `--for-proposal` adds proposal capability grounding; unsupported
  capabilities can be adopted from existing agents. `add-specialist` and
  `--specialist` preserve their existing ordering and lifecycle behavior.
- The default platform is `agents`: no new Claude setup is created.
  `--platform claude` or `both` also requests thin Claude discovery pointers
  and the detected formatter hook. Existing pristine legacy helpers may become
  pointers during migration; edited or evolved legacy entries keep their paths.
- `apply --lesson-file F` and `patch --lesson-file F` store applied agent bodies
  with their validated lesson in the specialist library (`apply` only after a
  successful write). `equip reuse CAPABILITY_ID [--force]` restores a stored
  body; a locally edited target needs `--force`. Reuse reports `needs-reverify`
  when the body or a grounding file changed.
- `--dry-run` previews capabilities, native adapter actions and hook intent
  without writing. Bare `equip` is a usage error; verbless `equip --dry-run`
  remains a read-only preview. Applying requires an existing `.context/`.
- Both host workflows read the selected manifest `path` and pass its full
  mandate to a native delegate. A missing named agent or manifest never blocks
  generic delegation. Selected session policies, including Ponytail when
  exposed, are passed explicitly, never installed or assumed.
- Shared formatting instructions name actual changed paths. Only the native
  Claude formatter hook uses Claude's file-path environment variable.
- Implementer, tester, verifier and testing specialists keep the current
  deliverable during baseline investigation. Acceptance and affected checks run
  first; required checks stay mandatory. Baselines use a separate checkout or copy.

The implementation is `dummyindex/cli/equip/dispatch.py`,
`dummyindex/cli/equip/library_verbs.py`,
`dummyindex/context/domains/equip/generate/` and
`dummyindex/skills/equip/SKILL.md`, `dummyindex/skills/plan/SKILL.md` and
`dummyindex/skills/build/SKILL.md`.

## Ownership and lifecycle

`EquipmentItem` in `dummyindex/context/domains/equip/models.py` records source,
capabilities, grounding, optional specialist invariants, version and
`origin_hash`, plus plugin provenance. Optional `capability_id`, `package_version`,
`package_source` and `package_sha256` identify the reusable shipped template,
independent of project-specific names/paths. `dimension` (`procedure` or
`domain`) is set only on dimensioned specialists (`models.py:121`). Required
tools, triggers and qualification references accompany that identity;
`project_binding` holds stack, commands, framework and convention paths.
The schema remains v4. Apply carries forward unrelated plugins, adopted entries
and stale-named generated entries.

Specialist invariants are exact, slot-free literal substrings. Every pristine
render must contain every registered string
(`dummyindex/context/domains/equip/generate/specialists.py:66`;
`tests/context/domains/equip/test_equip_specialist_invariants.py:69`). The security
template retains `Never assert "secure" without the evidence to back it.`
verbatim (`dummyindex/context/domains/equip/generate/specialists.py:131`;
`dummyindex/skills/equip/templates/security-specialist-agent.md.tmpl:61`). The
Manifest invariants are metadata; they do not alter rendered bytes.

Recorded hashes own only their recorded paths; a canonical destination is
checked independently. Edited, unreadable and symlinked files are preserved.
A sentinel alone never authorizes replacing a canonical body. Native pointer
ownership uses decoded, newline-normalized text
(`dummyindex/context/domains/equip/generate/adapters.py:73-89`). Capability
attribution hashes raw bytes (`dummyindex/context/domains/equip/identity.py:36-49`).

- `status` reports tracked ownership states and missing plugin usage docs.
- `refresh` re-renders pristine, non-evolved bodies; user-owned and missing
  bodies are skipped. Broken specialist invariants remain visible.
- `patch --item NAME --from-file F` applies an exact-once old/new replacement,
  updates the baseline and bumps the patch version. This is the shared learning
  seam; native pointers are not learning targets.
- `reset NAME` restores the generated baseline. `remove NAME --delete-file`
  removes a file-backed entry. `uninstall` keeps user-owned bodies, removes
  pristine owned bodies and unchanged pointers, and removes tracked native wiring.

The specialist library (`dummyindex/context/domains/equip/lifecycle/library.py`)
stores body and lesson under `.context/equipment/library/`, indexed by
`library.json` (origin and grounding hashes; `library.py:111-134`). `_safe_id` rejects backslash, colon, NUL, leading slash
and `.`/`..` segments (`library.py:79-86`). `reuse_capability` also re-baselines
the manifest `origin_hash` (`library.py:191-216`).

## Native integrations and verification

Claude marketplace discovery, approved installation, vendoring, plugin `verify`
and usage playbooks remain available through `dummyindex/cli/equip/install.py`,
`dummyindex/cli/equip/discover.py` and `dummyindex/cli/equip/plugin_state.py`.
Their settings and trust rules stay separate from shared capability preparation.
Installer defaults and session hooks belong to
`.context/features/install-surface/spec.md`.

Equip no longer seeds trigger suites, scores descriptions or emits nags; user
files from that subsystem stay intact.
`capability_identity` returns the SHA256 of actual loaded bytes; qualification
also checks the recorded lifecycle baseline. A declared capability ID or trigger alone is not proof it was loaded or
useful. Library tests live in `tests/context/domains/equip/test_equip_library.py`
and `tests/cli/equip/test_equip_reuse.py`. Deterministic tests establish
ownership, path resolution, adapter behavior and reuse; they do not establish
model obedience or measured task-quality improvement.
