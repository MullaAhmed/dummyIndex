# Project equipment toolkit — spec

`confidence: INFERRED`

## Intent

Prepare identical capabilities for every host. Keep user ownership across generation, refresh and learning. Registry: `.context/equipment.json`. Bodies: `.context/equipment/<name>.md`. Native discovery files reference bodies, not another implementation.

## Behavior

- `dummyindex context equip apply` prepares implementer, tester, reviewer, verify and every undimensioned template-backed specialist. Dimensioned specialists (frontend, api, migration, ci) need a signal: stack evidence (frontend, api), a proposal or explicit ask (`dummyindex/context/domains/equip/generate/catalog.py:67-79`, `:100-144`). `--for-proposal` adds grounding. Existing agents can adopt unsupported capabilities.
- Default platform `agents` creates no Claude setup. `--platform claude` or `both` adds thin discovery pointers and formatter hook. Pristine legacy helpers may become pointers during migration.
- `apply --lesson-file F` and `patch --lesson-file F` store agent bodies with validated lessons in the specialist library. `apply` stores only after successful write. `equip reuse CAPABILITY_ID [--force]` restores stored body. A locally edited target needs `--force`. Reuse reports `needs-reverify` when the body or grounding file changed.
- `--dry-run` previews capabilities, native adapter actions and hook intent without writing. Bare `equip` is a usage error. Verbless `equip --dry-run` stays read-only. Applying requires `.context/`. `add-specialist` and `--specialist` keep ordering and lifecycle.
- Both hosts pass selected manifest `path` mandates and policies explicitly to native delegates. Missing agent or manifest never blocks generic delegation. Ponytail applies by default when exposed: Claude's plugin `SubagentStart` hook injects it; other hosts paste it. Never silently installed.
- Shared formatting instructions name changed paths. Only native formatter hook uses file-path environment variable.
- Implementer, tester, verifier and testing specialists keep current deliverable during baseline investigation. Acceptance and affected checks run first; required checks stay mandatory (`dummyindex/skills/equip/templates/tester-agent.md.tmpl:44`, `dummyindex/skills/equip/templates/verify-skill.md.tmpl:36,49`). Baselines use a separate checkout or copy.
- `apply --source [--yes]` replaces eligible template specialists with upstream skills. Targets: templated specialists with dimension `None` or `procedure` (`dummyindex/cli/equip/source.py:235-250`). Channels run in order until one qualifies: seed marketplaces incl. ECC, skills.sh (`npx --no skills find`), GitHub (`dummyindex/cli/equip/source.py:313-317`).
- Only `skills/<name>/SKILL.md` counts. Fetch pins a commit sha. `block:` codes always reject. `warn:` codes or untrusted repos need `--yes`, run-wide (`dummyindex/context/domains/equip/plugins/sourcing.py:225-227`). Body: repo overlay (`dummyindex/skills/equip/templates/sourced-overlay.md.tmpl`) plus verbatim upstream text at template path (`dummyindex/context/domains/equip/generate/sourced.py:52-68`). No `gh`: `source: gh unavailable — templates kept`.

Implementation: `dummyindex/cli/equip/dispatch.py`, `dummyindex/cli/equip/library_verbs.py`, `dummyindex/cli/equip/source.py`, `dummyindex/context/domains/equip/generate/`, `dummyindex/skills/equip/SKILL.md`, `dummyindex/skills/equip/sourcing.md`, `dummyindex/skills/plan/SKILL.md` and `dummyindex/skills/build/SKILL.md`.

## Ownership and lifecycle

`EquipmentItem` in `dummyindex/context/domains/equip/models.py` records source, capabilities, grounding, optional specialist invariants, version and `origin_hash`, plus plugin provenance. Optional `capability_id`, `package_version`, `package_source` and `package_sha256` identify the reusable template, independent of project names/paths. Required tools, triggers and qualification references accompany that identity (`dummyindex/context/domains/equip/models.py:117-119`). `dimension` (`procedure`/`domain`) marks only dimensioned specialists (`models.py:121`). `project_binding` holds stack, commands, framework, convention paths. The schema remains v4 (`dummyindex/context/domains/equip/constants.py:14`). Apply carries forward unrelated plugins, adopted entries, stale-named generated entries.

Specialist invariants are exact, slot-free literal substrings. Pristine renders must contain each one (`dummyindex/context/domains/equip/generate/specialists.py:66`; `tests/context/domains/equip/test_equip_specialist_invariants.py:69`). The security template keeps `Never assert "secure" without the evidence to back it.` verbatim (`dummyindex/context/domains/equip/generate/specialists.py:131`; `dummyindex/skills/equip/templates/security-specialist-agent.md.tmpl:61`). Manifest invariants are metadata only.

Recorded hashes own only their recorded paths. Canonical destination is checked independently. Edited, unreadable and symlinked files are preserved. A sentinel alone never authorizes replacing canonical body. Native pointer ownership uses decoded, newline-normalized text (`dummyindex/context/domains/equip/generate/adapters.py:73-89`). Capability attribution hashes raw bytes (`dummyindex/context/domains/equip/identity.py:36-49`).

- `status` reports ownership states and missing plugin usage docs.
- `refresh` re-renders pristine bodies. User-owned, missing, evolved and sourced bodies are skipped (`dummyindex/context/domains/equip/lifecycle/status.py:269`). Broken specialist invariants remain visible.
- `patch --item NAME --from-file F` applies an exact-once old/new replacement, updates baseline and bumps patch version. Shared learning seam; native pointers are not learning targets.
- `reset NAME` restores the baseline. For sourced items it also clears origin fields and restores template invariants (`status.py:355-362`). `remove NAME --delete-file` removes file-backed entry. `uninstall` keeps user-owned bodies, removes pristine owned bodies and unchanged pointers, and tracked native wiring.
- Sourced items keep `source=generated` plus origin fields. `is_sourced` detects them (`dummyindex/context/domains/equip/lifecycle/status.py:138-140`). Plain `apply` keeps them, printing `(sourced, kept)` (`dummyindex/cli/equip/dispatch.py:458-471`, `dummyindex/cli/equip/dispatch.py:557-570`). Upstream change only reports `needs-reverify` (`dummyindex/cli/equip/source.py:253-271`).

Specialist library (`dummyindex/context/domains/equip/lifecycle/library.py`) stores body and lesson under `.context/equipment/library/`, indexed by `library.json` (origin and grounding hashes; `library.py:111-134`). `_safe_id` rejects backslash, colon, NUL, leading slash and `.`/`..` segments (`library.py:79-86`). `reuse_capability` re-baselines `origin_hash` (`library.py:191-216`).

## Native integrations and verification

Marketplace discovery, approved installation, vendoring, plugin `verify` and usage playbooks live in `dummyindex/cli/equip/install.py`, `dummyindex/cli/equip/discover.py` and `dummyindex/cli/equip/plugin_state.py`. Installer defaults, session hooks: `.context/features/install-surface/spec.md`.

Removed trigger-suite seeding and scoring left user files intact. `capability_identity` returns SHA256 of loaded bytes; qualification also checks recorded lifecycle baseline. A declared capability ID or trigger alone does not prove loading or usefulness. Deterministic tests establish ownership, path resolution, adapter behavior and reuse, not model obedience or quality.
