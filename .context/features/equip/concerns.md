# Project equipment toolkit — concerns

confidence: INFERRED

## Remaining limits

- **Guidance is not measured obedience.** The shared skills require mandate and
  selected-policy propagation, but Python emits paths and routing metadata; it
  does not run the host's model. File/adapter tests cannot prove that a delegate
  followed Ponytail or improved task outcomes. Relevant sources:
  `dummyindex/cli/build_loop/waves.py` and
  `dummyindex/skills/build/SKILL.md`.
- **Apply is not a multi-file transaction.** Writes are atomic per file, native
  migration recovery is bounded, and optional adapter failures are reported.
  A later error can still leave canonical files or native settings already
  written. Inspect the registry and reported warnings before retrying
  (`dummyindex/cli/equip/dispatch.py:_apply_write`).
- **Missing does not mean declined.** Every template-backed specialist is still
  generated on apply. Deleting/removing one is not a durable opt-out; a later
  apply can recreate it. Refresh skips missing bodies
  (`dummyindex/context/domains/equip/generate/catalog.py:build_catalog`,
  `dummyindex/context/domains/equip/lifecycle/status.py:refresh`).
- **Stable names are lifecycle identities.** Renaming a project/stack can leave
  old records carried forward. A missing current render can be reported as
  unchanged; explicit removal may still be needed. Preservation is intentional,
  not evidence that those records are useful
  (`dummyindex/cli/equip/common.py:fresh_renders`,
  `dummyindex/context/domains/equip/lifecycle/status.py:refresh`).
- **Plugin inventory remains separate.** Registry status is not proof that a
  native marketplace plugin loaded, and installer defaults/user-scoped or
  externally installed skills need not be tracked here. Use plugin `verify`
  for the native registry. Existing marketplace identity, moving-source,
  shared-settings and managed-hook concerns remain outside this setup change;
  see `.context/features/install-surface/concerns.md` and
  `dummyindex/cli/equip/install.py` and
  `dummyindex/cli/equip/plugin_state.py`.
- **Native formatting can overlap user hooks.** Explicit Claude preparation
  preserves user hooks but does not deduplicate an equivalent formatter under
  another owner's sentinel (`dummyindex/context/domains/equip/generate/catalog.py:_format_hooks`,
  `dummyindex/context/domains/equip/wiring/hooks.py:wire_hooks`).

Canonical migration now preserves edited/evolved or unreadable legacy bodies,
refuses unsafe/foreign destinations and leaves edited native pointers alone.
Those protections do not authorize broad cleanup of old files or user settings.
