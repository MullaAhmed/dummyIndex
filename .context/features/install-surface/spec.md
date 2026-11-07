# Install surface — spec

`confidence: INFERRED`

## Intent

One command places the dummyindex workflow family where Claude Code and Agent
Skills hosts discover it, upgrades an earlier install without taking ownership
of user edits, and wires the current repository. Reruns are idempotent: only
provably package-owned content is refreshed, everything else is preserved, and
an incomplete result is reported rather than called success.

## User-visible behavior

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

## Contracts

- `install(*, scope="user", project_dir=None, skill_only, no_onboarding,
  defaults, no_default_plugins, no_superpowers, platform="both", dedupe=None,
  force_downgrade, link_mode=LinkMode.AUTO) -> None`; bools default False and
  `platform` spells agents as `codex` (`dummyindex/installer/install/orchestrate.py:47-364`).
- `parse_install_args(args)` returns the positional 10-tuple `(scope,
  project_dir, skill_only, no_onboarding, defaults, no_default_plugins,
  platform, dedupe, force_downgrade, link_mode)` (`dummyindex/installer/args.py:85-216`), unpacked
  at `dummyindex/__main__.py:282-307`.
- `uninstall(*, scope="user", project_dir=None, platform="both") -> None`
  (`dummyindex/installer/uninstall.py:20-121`).
- `VersionOrder(str, Enum)` (`OLDER|EQUAL|NEWER|UNKNOWN`, renders as its value),
  `parse_version(value) -> tuple[int, ...] | None`,
  `compare_versions(stamp, package_version) -> VersionOrder`
  (`dummyindex/versioning.py:13-62`); `_parse_version` / `_compare_stamp` are the same
  objects (`dummyindex/installer/common.py:363-364`).
- `sync_family(directory, files, *, family, version, layout="full",
  force_downgrade=False) -> InstallFilesResult(written, removed, preserved,
  complete)` (`dummyindex/installer/ownership.py:149-241`).
- `_auto_init_project(project_root, *, no_default_plugins, no_superpowers,
  platform, codex_guidance_owner, force_downgrade) -> bool`, False only when the
  import, build, or refresh raises (`dummyindex/installer/install/project_init.py:20-161`).

## Examples

`dummyindex install --scope project --dir repo` on a curated repo:

1. Repair refreshes stale owned copies; `_install_skill_family` syncs
   `.agents/skills/dummyindex*`; AUTO links or references `.claude/skills/<family>`
   (`dummyindex/installer/install/orchestrate.py:175-271`).
2. `refresh_deterministic_artifacts` retires v0.36 `.context/equipment-evals/`
   suites and prints 5 `removed` lines, `… and 3 more removed`, and one `backed up
   to .context/_doc_backups/retired/0.37.0/equipment-evals/<edited>` line
   (`tests/test_install.py:2373-2407`).
3. `CLAUDE.md`, Codex guidance, hooks, default plugins, and equipment run; `Done.
   Open Claude Code + Codex in <repo> and run:` follows.

If the symbol-graph write fails, install still finishes, prints `version stamp
not advanced`, and leaves `meta.dummyindex_version` unchanged
(`tests/test_install.py:2410-2447`).
