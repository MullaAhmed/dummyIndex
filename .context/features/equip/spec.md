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
  verify capability and every template-backed specialist. `--for-proposal`
  adds proposal capability grounding; unsupported capabilities can be adopted
  from existing agents. `add-specialist` and `--specialist` preserve their
  existing ordering and lifecycle behavior.
- The default platform is `agents`: no new Claude setup is created.
  `--platform claude` or `both` also requests thin Claude discovery pointers
  and the detected formatter hook. Existing pristine legacy helpers may become
  pointers during migration even without native extras; edited or evolved
  legacy entries keep their recorded paths.
- `--dry-run` previews capabilities, native adapter actions and hook intent
  without writing. Bare `equip` is a usage error; verbless `equip --dry-run`
  remains a read-only preview. Applying requires an existing `.context/`.
- Both host workflows read the selected manifest `path` and pass its full
  mandate to a native delegate. A missing named agent or manifest never blocks
  generic delegation. Selected session policies, including Ponytail when
  actually selected and exposed, are passed explicitly; they are not installed
  or assumed automatically.
- Shared formatting instructions name actual changed paths. Only the native
  Claude formatter hook uses Claude's file-path environment variable.
- Implementer, tester, verifier and testing specialists preserve the current
  deliverable during baseline investigation. Acceptance and affected checks run
  first; required checks remain mandatory, and broader investigation must fit
  the remaining budget. Baseline comparisons use a separate checkout or copy.

The implementation is `dummyindex/cli/equip/dispatch.py`,
`dummyindex/context/domains/equip/generate/` and
`dummyindex/skills/equip/SKILL.md`, `dummyindex/skills/plan/SKILL.md` and
`dummyindex/skills/build/SKILL.md`.

## Ownership and lifecycle

`EquipmentItem` in `dummyindex/context/domains/equip/models.py` records source,
capabilities, grounding, optional specialist invariants, version and
`origin_hash`, plus plugin provenance. Optional `capability_id`, `package_version`,
`package_source` and `package_sha256` identify the reusable shipped template,
independent of project-specific names/paths. Required tools, triggers and
qualification references accompany that identity; `project_binding` holds stack,
commands, framework and convention paths. Package versions use LF-normalized
template content so checkout line endings do not fork identity. The schema remains v4. Apply merges
records: unrelated plugins, adopted entries and stale-named generated entries
are carried forward rather than silently dropped.

Specialist invariants are exact, slot-free literal substrings. Every pristine
render must contain every registered string
(`dummyindex/context/domains/equip/generate/specialists.py:66`;
`tests/context/domains/equip/test_equip_specialist_invariants.py:69`). The security
template therefore retains `Never assert "secure" without the evidence to back it.`
verbatim (`dummyindex/context/domains/equip/generate/specialists.py:131`;
`dummyindex/skills/equip/templates/security-specialist-agent.md.tmpl:61`). The
invariant set is manifest metadata; recording it does not itself alter the
rendered body or its hash (`dummyindex/context/domains/equip/generate/plan.py:56`).

Recorded hashes own only their recorded paths. A canonical destination is
checked independently during migration. Edited, unreadable and symlinked
existing files are preserved; evolved bodies keep their version and content.
A sentinel alone does not authorize replacing a different canonical body.
Native pointer ownership compares decoded UTF-8 text with universal-newline
normalization, so an unchanged pointer remains recognized across LF/CRLF
checkout conversion. Migration additionally requires the recorded pristine
legacy hash (`dummyindex/context/domains/equip/generate/adapters.py:73-89`);
removal uses the same decoded-text comparison
(`dummyindex/context/domains/equip/generate/adapters.py:100-105`). Actual loaded
capability attribution separately hashes raw bytes
(`dummyindex/context/domains/equip/identity.py:36-49`).

- `status` reports tracked ownership states and missing plugin usage docs.
- `refresh` re-renders pristine, non-evolved bodies; user-owned and missing
  bodies are skipped. Broken specialist invariants remain visible.
- `patch --item NAME --from-file F` applies an exact-once old/new replacement,
  updates the baseline and bumps the patch version. This is the shared learning
  seam; native pointers are not learning targets.
- `reset NAME` deliberately restores the generated baseline. `remove NAME
  --delete-file` removes a file-backed entry. `uninstall` keeps user-owned
  bodies, removes pristine owned bodies and unchanged pointers, and removes
  tracked native wiring according to its existing lifecycle.

See `dummyindex/context/domains/equip/lifecycle/` and
`dummyindex/context/domains/equip/generate/adapters.py`.

## Native integrations and verification

Claude marketplace discovery, approved installation, vendoring, plugin `verify`
and usage playbooks remain available through `dummyindex/cli/equip/install.py`,
`dummyindex/cli/equip/discover.py` and
`dummyindex/cli/equip/plugin_state.py`. Their settings and trust rules remain
separate from shared capability preparation. Installer-managed defaults and
session hooks belong to `.context/features/install-surface/spec.md`; equip status is not a
complete inventory of those integrations.

Equip no longer seeds trigger suites, scores descriptions or emits evaluation
nags. Existing user files from that subsystem are left intact. Verification
uses actual project checks and inspected outcomes. `capability_identity` reads
actual loaded bytes and returns their SHA256; qualification additionally checks
the recorded lifecycle baseline (allowing a legacy checkout's newline conversion).
A declared capability ID or trigger alone is not proof it was loaded or useful. Deterministic tests establish
ownership, path resolution and adapter behavior; they do not establish model
obedience or measured task-quality improvement.
