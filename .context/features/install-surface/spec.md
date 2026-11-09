# Install surface

`confidence: CONFIRMED`

`dummyindex install` prepares the workflow family and, unless `--skill-only` is set, initializes the repository. Scope is `user` or `project`. Platform is `claude`, `agents`, or `both`. The Python API spells agents `codex`.

## One workflow source

AUTO prepares the complete family under `.agents/skills/dummyindex*/`, even when only Claude is selected. Claude uses relative directory links where available. Otherwise each Claude family holds a small `SKILL.md` reference to the canonical file, and companions resolve relative to it. No second workflow is generated. `--link` requires successful linking. `--copy` writes full copies. Selecting agents alone writes no Claude skills, hooks, or plugins.

## Ownership and updates

Each real family has `.dummyindex-files.json`: per-file stock hashes, layout, desired skill source digest, package source digest, and completion state.
Owned families ship root Markdown companions. Edits stay preserved under per-file rules (`dummyindex/installer/install/family_write.py:47-53`, `tests/test_install_ownership.py:73-113`).
A version stamp is a hint, never permission to overwrite files.
Preparation refreshes absent files, exact current files, and files matching a stock baseline. Edited files and unknown companions stay. The old baseline stays, so updates never adopt an edit as stock.
An incomplete family is reported, not called repaired.
Installation exits nonzero after safe work if required families stay incomplete. It never creates native aliases to missing canonical entries.

Legacy official 0.36.0 content is recognized by bounded fingerprints in `dummyindex/installer/legacy_fingerprints.py`. Other ambiguous legacy content stays preserved. Converting a real family to a shared reference or link requires every file proven unchanged and no unknown paths.
Newer or unparseable stamps need `--force-downgrade`, which never overrides ownership checks. Uninstall and dedupe remove only unchanged owned files or native links. Edited and unknown survivors stay.

`dummyindex check --versions` distinguishes version drift from source and content drift. The update skill pins an immutable commit, then checks CLI, workflow, and source identity. A matching version alone does not establish a complete update.

## Project integration

Shipped shell scripts use LF, so Windows line endings cannot break Bash.

`dummyindex/installer/install/project_init.py` preserves a curated index while refreshing derived maps. Claude-selected initialization wires managed hooks and plugins. Agents-selected initialization writes managed host guidance. Equipment refresh runs for every selected host, honoring generated-body ownership. Native hooks and plugins keep their platform guard. Refresh keeps upstream-sourced items (`dummyindex/context/domains/equip/lifecycle/status.py:269`).
Managed PreToolUse hooks match `Write|Edit|MultiEdit|Agent|Task|SendMessage` (`dummyindex/context/hooks.py:258-279`, matcher `:260`).
`Agent`, `Task`, and `SendMessage` get only a warn-only language hint.
Re-install refreshes older matchers by sentinel. Managed Stop hook adds async `context evolve evidence` (`dummyindex/context/hooks.py:230`).

Default plugin wiring runs only for Claude selections (`dummyindex/installer/install/project_init.py:111-116`). Reviewed defaults are `superpowers`, `caveman`, `i-have-adhd`, and `ponytail` (`dummyindex/context/default_plugins.py:166-208`).
Wiring calls `ensure_caveman_manual` when `caveman@caveman` is not disabled (`dummyindex/context/default_plugins.py:358-369`, `:559-561`). It writes `.caveman.json` as `{"defaultMode": "manual"}` unless that file or `.caveman/config.json` exists or the root is the user home. `CAVEMAN_DEFAULT_MODE` overrides that file (`dummyindex/skills/skill.md:29`).

This feature owns placement and wiring. Index, hook, capability, and plugin policy belong elsewhere.
