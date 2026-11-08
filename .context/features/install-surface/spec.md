# Install surface

`confidence: CONFIRMED`

`dummyindex install` prepares the installed workflow family and, unless
`--skill-only` is selected, initializes the selected repository. Scope is
`user` or `project`; platform is `claude`, `agents`, or `both` (the Python
API uses the internal `codex` spelling).

## One workflow source

AUTO prepares the complete family under `.agents/skills/dummyindex*/`, even when
only Claude is selected. Claude discovery uses relative directory links where
available; otherwise each Claude family holds a small `SKILL.md` reference to
the canonical file, and companions resolve relative to it. No second workflow
implementation is generated. `--link` requires successful linking; `--copy`
retains full copies for compatibility. Selecting agents alone writes no Claude
configuration.

## Ownership and updates

Each real family has `.dummyindex-files.json`: per-file stock hashes,
layout, desired skill source digest, package source digest, and completion state.
A root Markdown companion ships in the owned family; edits stay preserved under
per-file ownership rules (`dummyindex/installer/install/family_write.py:47-53`, `tests/test_install_ownership.py:73-113`).
A version stamp is a version hint, never permission to overwrite arbitrary files.
Preparation refreshes absent files, exact current files, and files matching a
recorded stock baseline. Edited files and unknown companions stay; the old baseline is kept so later updates never adopt an edit as stock. An
incomplete family is reported, not described as successfully repaired.
Installation exits nonzero after safe independent work if required families stay incomplete; it never creates native aliases to missing canonical entries.

Legacy official 0.36.0 content is recognized by bounded fingerprints in
`dummyindex/installer/legacy_fingerprints.py`. Other ambiguous legacy content is
preserved for review. Converting a real family to a shared reference or link requires every file proven unchanged and no unknown paths.
Newer or unparseable stamps require `--force-downgrade`; this flag never overrides
ownership checks. Uninstall and dedupe remove only unchanged owned files or native
links; edited and unknown survivors stay.

`dummyindex check --versions` distinguishes version drift from source/content
drift. The update skill resolves its GitHub ref to an immutable commit before
installing, then checks CLI, workflow, and source identity. A matching version
alone does not establish a complete update.

## Project integration

Shipped shell scripts use LF on every checkout so Windows line endings cannot break Bash.

`dummyindex/installer/install/project_init.py` preserves a curated index while
refreshing derived maps. Claude-selected initialization wires managed
hooks/plugins; agents-selected initialization writes managed host guidance.
Equipment refresh runs for every selected host, honoring generated-body ownership; native hooks/plugins keep their platform guard. Managed PreToolUse
hooks match `Write|Edit|MultiEdit|Agent|Task|SendMessage`
(`dummyindex/context/hooks.py:258-279`, matcher `:260`).
`Agent`, `Task`, and `SendMessage` get only a warn-only language hint.
Re-install refreshes older matchers by sentinel.

Default plugin wiring calls `ensure_caveman_manual` when `caveman@caveman` is not
disabled (`dummyindex/context/default_plugins.py:358-369`, `:559-561`). It writes
`.caveman.json` as `{"defaultMode": "manual"}` unless that file or
`.caveman/config.json` exists or the root is the user home. Codex-only installs
skip it. `CAVEMAN_DEFAULT_MODE` overrides that file (`dummyindex/skills/skill.md:29`).

This feature owns placement and wiring; index, hook behavior, capability content,
and plugin policies stay with their features.
