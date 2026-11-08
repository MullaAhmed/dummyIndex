# Install surface — spec

`confidence: INFERRED`

`dummyindex install` prepares the workflow family and, unless `--skill-only` is set, initializes the repository. Scope is `user` or `project`. Platform is `claude`, `agents`, or `both`. The Python API spells agents `codex`.

One command places the dummyindex workflow family where Claude Code and Agent
Skills hosts discover it, upgrades an earlier install without taking ownership
of user edits, and wires the current repository. Reruns are idempotent: only
provably package-owned content is refreshed, everything else is preserved, and
an incomplete result is reported rather than called success.

AUTO prepares the complete family under `.agents/skills/dummyindex*/`, even when only Claude is selected. Claude uses relative directory links where available. Otherwise each Claude family holds a small `SKILL.md` reference to the canonical file, and companions resolve relative to it. No second workflow is generated. `--link` requires successful linking. `--copy` writes full copies. Selecting agents alone writes no Claude skills, hooks, or plugins.

- **Flags** are listed in `dummyindex/installer/args.py:10-50`. `codex` is a
  deprecated alias for `agents`, warned once per process; `--link --copy` and
  `--link --platform agents` exit 2 (`dummyindex/installer/args.py:189-201`).
- **One workflow source.** Unless `--copy`, a Claude selection also prepares the
  canonical `.agents/skills/dummyindex*/` family. Claude discovers it through
  relative directory links or, when AUTO cannot link, a thin `SKILL.md` naming
  the canonical file, whose companions resolve from its own directory
  (`dummyindex/installer/install/family_write.py:93-119`). `--link` fails instead of falling back; `--copy`
  writes full native copies. No native reference is written if the canonical
  `SKILL.md` is missing (`dummyindex/installer/install/orchestrate.py:87-89`,
  `213-271`). Selecting agents alone writes no Claude skills, commands, hooks,
  or plugins; it only folds a dummyindex-generated legacy `CLAUDE.md`
  (`dummyindex/installer/install/project_init.py:143-151`).
- **Ownership.** A file is rewritten only when absent, already current, or equal
  to its recorded baseline. Edited files and unknown companions survive and keep
  the old baseline; unhashed legacy content is provable only against the
  official 0.36.0 fingerprints. A real Claude family becomes a reference only
  when every file is pristine; uninstall and dedupe delete only proven-unchanged
  files (`dummyindex/installer/ownership.py:100-116`, `189-217`, `263-299`;
  `dummyindex/installer/install/family_write.py:135-144`).
- **Stamps are hints.** A family stamped newer or unparseable is preserved unless
  `--force-downgrade`, which never bypasses per-file hashes (`dummyindex/installer/ownership.py:171-178`).
  Comparison is dotted-integer only; `v`-prefixed, pre-release, empty, or
  `unknown` values are `UNKNOWN`, never `OLDER` (`dummyindex/versioning.py:32-62`).
- **Exit status.** After dedupe, commands, registration, and project init, an
  incomplete family prints `error: partial installation; …` and exits 1
  (`dummyindex/installer/install/orchestrate.py:340-345`).
- **Project init** (git repo, no `--skill-only`). A curated index gets a
  deterministic refresh with no re-cluster; `--force-downgrade` also lets it
  lower a newer `meta.dummyindex_version`. Any other index full-builds. Both
  paths print the layout migration: up to 5 `removed` paths then `… and N more
  removed`, `backed up to .context/…`, and `warning: migration …`. The refresh
  also prints, per failed required artefact, `warning: <artifact> failed
  (<error>); version stamp not advanced — fix the cause, then run `dummyindex
  context rebuild --changed``
  (`dummyindex/installer/install/project_init.py:65-81`, `113-130`;
  `dummyindex/context/build/upgrade.py:577-615`). A held-back stamp is a
  warning, not an exit code. Host guidance, Claude-only hooks and default
  plugins, and the equipment refresh follow (`dummyindex/installer/install/project_init.py:88-111`).
- **Verification.** `dummyindex context check --versions` reports source drift
  apart from version skew (`dummyindex/cli/check.py:231-268`); the update skill
  installs one resolved immutable commit (`dummyindex/skills/update/SKILL.md:69-79`).

Each real family has `.dummyindex-files.json`: per-file stock hashes, layout, desired skill source digest, package source digest, and completion state.
Owned families ship root Markdown companions. Edits stay preserved under per-file rules (`dummyindex/installer/install/family_write.py:47-53`, `tests/test_install_ownership.py:73-113`).
A version stamp is a hint, never permission to overwrite files.
Preparation refreshes absent files, exact current files, and files matching a stock baseline. Edited files and unknown companions stay. The old baseline stays, so updates never adopt an edit as stock.
An incomplete family is reported, not called repaired.
Installation exits nonzero after safe work if required families stay incomplete. It never creates native aliases to missing canonical entries.

Legacy official 0.36.0 content is recognized by bounded fingerprints in `dummyindex/installer/legacy_fingerprints.py`. Other ambiguous legacy content stays preserved. Converting a real family to a shared reference or link requires every file proven unchanged and no unknown paths.
Newer or unparseable stamps need `--force-downgrade`, which never overrides ownership checks. Uninstall and dedupe remove only unchanged owned files or native links. Edited and unknown survivors stay.

`dummyindex check --versions` distinguishes version drift from source and content drift. The update skill pins an immutable commit, then checks CLI, workflow, and source identity. A matching version alone does not establish a complete update.

`dummyindex install --scope project --dir repo` on a curated repo:

Shipped shell scripts use LF, so Windows line endings cannot break Bash.

`dummyindex/installer/install/project_init.py` preserves a curated index while refreshing derived maps. Claude-selected initialization wires managed hooks and plugins. Agents-selected initialization writes managed host guidance. Equipment refresh runs for every selected host, honoring generated-body ownership. Native hooks and plugins keep their platform guard. Refresh keeps upstream-sourced items (`dummyindex/context/domains/equip/lifecycle/status.py:269`).
Managed PreToolUse hooks match `Write|Edit|MultiEdit|Agent|Task|SendMessage` (`dummyindex/context/hooks.py:258-279`, matcher `:260`).
`Agent`, `Task`, and `SendMessage` get only a warn-only language hint.
Re-install refreshes older matchers by sentinel. Managed Stop hook adds async `context evolve evidence` (`dummyindex/context/hooks.py:230`).

Default plugin wiring runs only for Claude selections (`dummyindex/installer/install/project_init.py:111-116`). Reviewed defaults are `superpowers`, `caveman`, `i-have-adhd`, and `ponytail` (`dummyindex/context/default_plugins.py:166-208`).
Wiring calls `ensure_caveman_manual` when `caveman@caveman` is not disabled (`dummyindex/context/default_plugins.py:358-369`, `:559-561`). It writes `.caveman.json` as `{"defaultMode": "manual"}` unless that file or `.caveman/config.json` exists or the root is the user home. `CAVEMAN_DEFAULT_MODE` overrides that file (`dummyindex/skills/skill.md:29`).

This feature owns placement and wiring. Index, hook, capability, and plugin policy belong elsewhere.
