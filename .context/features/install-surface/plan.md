# Install surface implementation

`confidence: CONFIRMED`

- `dummyindex/installer/args.py` parses scope, platform, link/copy, downgrade,
  dedupe, and initialization flags. `dummyindex/installer/common.py` provides
  shared host paths, rendering, command preparation, and version comparison.
- `dummyindex/installer/install/orchestrate.py` validates destination chains,
  plans scoped repairs, prepares the canonical family, dispatches existing link
  machinery or native references, handles requested dedupe, and initializes the
  project through `dummyindex/installer/install/project_init.py`.
- `dummyindex/installer/install/family_write.py` declares complete package file
  sets and renders thin Claude references. `dummyindex/installer/ownership.py`
  implements per-file ownership, source identity, safe refresh, and removal.
  `dummyindex/installer/legacy_fingerprints.py` is the one-version migration
  catalog; arbitrary historical versions are deliberately not inferred.
- `dummyindex/installer/link/` retains link classification, capability probing,
  rename-aside recovery, and dangling-link cleanup. Real directory conversion
  requires byte-level pristine ownership before any destructive replacement.
- `dummyindex/installer/repair.py` discovers installed roots and isolates repair
  failures. `dummyindex/installer/uninstall.py` shares ownership-aware removal;
  unknown companions and edited survivors are never recursively swept.
- `dummyindex/cli/check.py` reports source drift separately from semantic version
  drift. `dummyindex/skills/update/SKILL.md` specifies immutable commit resolution
  and the same verification contract for host-driven updates.

Runtime coverage is in `tests/test_install_ownership.py`, `tests/test_install.py`,
`tests/test_install_repair.py`, `tests/test_install_link.py`, and
`tests/test_install_link_primitives.py`; CLI version/source checks are covered by
`tests/cli/test_check_versions.py`. Tests use isolated HOME/USERPROFILE and never
prepare the user's actual installed families.
