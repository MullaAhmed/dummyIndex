# Install surface implementation

`confidence: CONFIRMED`

- `dummyindex/context/installer/args.py` parses scope, platform, link/copy, downgrade,
  dedupe, and initialization flags. `dummyindex/context/installer/common.py` provides
  shared host paths, rendering, command preparation, and version comparison.
- `dummyindex/context/installer/install/orchestrate.py` validates destination chains
  and plans scoped repairs. It prepares the canonical family, dispatches link
  machinery or native references, and handles requested dedupe. Initialization
  runs through `dummyindex/context/installer/install/project_init.py`.
- `dummyindex/context/installer/install/family_write.py` declares complete package file
  sets and renders thin Claude references. `dummyindex/context/installer/ownership.py`
  implements per-file ownership, source identity, safe refresh, and removal.
  `dummyindex/context/installer/legacy_fingerprints.py` is the one-version migration
  catalog; arbitrary historical versions are deliberately not inferred.
- `dummyindex/context/installer/link/` retains link classification, capability probing,
  rename-aside recovery, and dangling-link cleanup. Real directory conversion
  requires byte-level pristine ownership before any destructive replacement.
- `dummyindex/context/installer/repair.py` discovers installed roots and isolates repair
  failures. `dummyindex/context/installer/uninstall.py` shares ownership-aware removal;
  unknown companions and edited survivors are never recursively swept.
- `dummyindex/context/cli/check.py` reports source drift separately from semantic version
  drift. `dummyindex/skills/update/SKILL.md` specifies immutable commit resolution
  and the same verification contract for host-driven updates.

Runtime coverage is in `tests/test_install_ownership.py`, `tests/test_install.py`,
`tests/test_install_repair.py`, `tests/test_install_link.py`, and
`tests/test_install_link_primitives.py`; CLI version/source checks are covered by
`tests/context/cli/test_check_versions.py`. Tests use isolated HOME/USERPROFILE and never
prepare the user's actual installed families.
