# Project equipment toolkit — spec

confidence: INFERRED

## Intent

Prepare the same capabilities for every host, preserving user ownership across generation, refresh and learning. Registry: `.context/equipment.json`; bodies: `.context/equipment/<name>.md`. Native discovery files reference bodies, not another implementation.

## Behavior

- `dummyindex context equip apply` prepares implementer, tester, reviewer, verify capability and every undimensioned template-backed specialist. Dimensioned specialists (frontend, api, migration, ci) need a signal: stack evidence (frontend, api), a proposal or explicit ask (`dummyindex/context/domains/equip/generate/catalog.py:67-79`, `:100-144`). `--for-proposal` adds grounding; existing agents can adopt unsupported capabilities. `add-specialist` and `--specialist` keep existing ordering and lifecycle.
- Default platform `agents` creates no Claude setup. `--platform claude` or `both` adds thin discovery pointers and the formatter hook. Pristine legacy helpers may become pointers during migration; edited or evolved entries keep paths.
- `apply --lesson-file F` and `patch --lesson-file F` store agent bodies with validated lessons in the specialist library (`apply` only after a successful write). `equip reuse CAPABILITY_ID [--force]` restores a stored body; a locally edited target needs `--force`. Reuse reports `needs-reverify` when the body or a grounding file changed.
- `--dry-run` previews capabilities, native adapter actions and hook intent without writing. Bare `equip` is a usage error; verbless `equip --dry-run` stays read-only. Applying requires an existing `.context/`.
- Both hosts pass selected manifest `path` mandates to native delegates; a missing agent or manifest never blocks generic delegation. Selected policies pass explicitly. Ponytail applies by default when exposed: Claude's plugin `SubagentStart` hook injects it; other hosts paste it. Never silently installed.
- Shared formatting instructions name changed paths. Only the native formatter hook uses the file-path environment variable.
- Implementer, tester, verifier and testing specialists keep current deliverable during baseline investigation. Acceptance and affected checks run first; required checks stay mandatory. Baselines use a separate checkout or copy.
- `apply --source [--yes]` swaps eligible template specialists for upstream skills. Order: seeds incl. ECC, skills.sh (`npx --no skills find`), GitHub (`dummyindex/cli/equip/source.py:313-317`). Only `skills/<name>/SKILL.md` counts; fetch pins a sha. `block:` codes always reject; `warn:` or untrusted needs `--yes`, run-wide (`dummyindex/context/domains/equip/plugins/sourcing.py:225-227`). Body: repo overlay plus verbatim upstream text, at the template path (`dummyindex/context/domains/equip/generate/sourced.py:52-68`). No `gh`: `source: gh unavailable — templates kept`.

Implementation: `dummyindex/cli/equip/dispatch.py`, `dummyindex/cli/equip/library_verbs.py`, `dummyindex/cli/equip/source.py`, `dummyindex/context/domains/equip/generate/`, `dummyindex/skills/equip/SKILL.md`, `dummyindex/skills/plan/SKILL.md` and `dummyindex/skills/build/SKILL.md`.

## Ownership and lifecycle

`EquipmentItem` in `dummyindex/context/domains/equip/models.py` records source, capabilities, grounding, optional specialist invariants, version and `origin_hash`, plus plugin provenance. Optional `capability_id`, `package_version`, `package_source` and `package_sha256` identify the reusable shipped template, independent of project names/paths. `dimension` (`procedure`/`domain`) marks only dimensioned specialists (`models.py:121`). Required tools, triggers, qualification references accompany that identity; `project_binding` holds stack, commands, framework, convention paths. The schema remains v4. Apply carries forward unrelated plugins, adopted entries, stale-named generated entries.

Specialist invariants are exact, slot-free literal substrings. Pristine renders must contain every registered string
(`dummyindex/context/domains/equip/generate/specialists.py:66`;
`tests/context/domains/equip/test_equip_specialist_invariants.py:69`). The security
template retains `Never assert "secure" without the evidence to back it.`
verbatim (`dummyindex/context/domains/equip/generate/specialists.py:131`;
`dummyindex/skills/equip/templates/security-specialist-agent.md.tmpl:61`).
Manifest invariants are metadata; they alter no rendered bytes.

Recorded hashes own only their recorded paths; a canonical destination is
checked independently. Edited, unreadable and symlinked files are preserved.
A sentinel alone never authorizes replacing a canonical body. Native pointer
ownership uses decoded, newline-normalized text
(`dummyindex/context/domains/equip/generate/adapters.py:73-89`). Capability
attribution hashes raw bytes (`dummyindex/context/domains/equip/identity.py:36-49`).

- `status` reports ownership states and missing plugin usage docs.
- `refresh` re-renders pristine, non-evolved bodies; user-owned, missing and sourced bodies are skipped. Broken specialist invariants remain visible.
- `patch --item NAME --from-file F` applies an exact-once old/new replacement, updates the baseline, bumps the patch version. Shared learning seam; native pointers are not learning targets.
- `reset NAME` restores the baseline and clears sourced origin fields. `remove NAME --delete-file` removes a file-backed entry. `uninstall` keeps user-owned bodies, removes pristine owned bodies and unchanged pointers, and removes tracked native wiring.
- Sourced items keep `source=generated` plus origin fields; `is_sourced` detects them (`dummyindex/context/domains/equip/lifecycle/status.py:138-140`). Plain `apply` keeps them, printing `(sourced, kept)` (`dummyindex/cli/equip/dispatch.py:557-570`).

The specialist library (`dummyindex/context/domains/equip/lifecycle/library.py`)
stores body and lesson under `.context/equipment/library/`, indexed by
`library.json` (origin and grounding hashes; `library.py:111-134`). `_safe_id` rejects backslash, colon, NUL, leading slash
and `.`/`..` segments (`library.py:79-86`). `reuse_capability` re-baselines `origin_hash` (`library.py:191-216`).

## Native integrations and verification

Marketplace discovery, approved installation, vendoring, plugin `verify`
and usage playbooks live in `dummyindex/cli/equip/install.py`,
`dummyindex/cli/equip/discover.py` and `dummyindex/cli/equip/plugin_state.py`.
Their settings and trust rules stay separate from shared preparation.
Installer defaults, session hooks: `.context/features/install-surface/spec.md`.

Removed trigger-suite seeding and scoring left user files intact.
`capability_identity` returns SHA256 of loaded bytes; qualification
also checks the recorded lifecycle baseline. A declared capability ID or trigger alone does not prove loading or usefulness. Deterministic tests establish
ownership, path resolution, adapter behavior and reuse, not model obedience or measured quality.
