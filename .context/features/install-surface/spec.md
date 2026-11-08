# Install surface

`confidence: CONFIRMED`

`dummyindex install` prepares the installed workflow family and, unless
`--skill-only` is selected, initializes the selected repository. Scope remains
`user` or `project`; platform remains `claude`, `agents`, or `both` (the Python
API uses the internal `codex` spelling). Project config, user guidance,
plugins, hooks, and curated feature ownership keep their merge rules.

## One workflow source

AUTO prepares the complete family under `.agents/skills/dummyindex*/`, including
when only Claude is selected. Claude discovery uses existing relative directory
links where available. If links are unavailable, each Claude family contains a
small `SKILL.md` reference to the canonical file; companion instructions are read
relative to that canonical file. No second workflow implementation is generated.
`--link` requires linking to succeed; `--copy` explicitly retains full copies for
compatibility. Selecting agents alone does not write Claude configuration.

## Ownership and updates

Each real family has `.dummyindex-files.json`, containing per-file stock hashes,
layout, desired skill source digest, package source digest, and completion state.
A root Markdown companion ships in the same owned family; edits stay preserved
under the per-file ownership rules (`dummyindex/installer/install/family_write.py:47-53`, `tests/test_install_ownership.py:73-113`).
A version stamp is a version hint, never permission to overwrite arbitrary files.
Preparation refreshes absent files, exact current files, and files matching a
recorded stock baseline. Edited files and unknown companions remain in place;
the old baseline is retained so subsequent updates never adopt an edit as stock.
An incomplete family is reported, not described as successfully repaired.
Installation exits nonzero after safe independent work if required families remain
incomplete, and it never creates native aliases to a missing canonical entry.

Legacy official 0.36.0 content is recognized by the bounded fingerprints
in `dummyindex/installer/legacy_fingerprints.py`. Other ambiguous legacy content
is preserved for review. Conversion of a real family to a shared reference or
link requires every existing file to be proven unchanged and no unknown paths.
Newer or unparseable stamps require `--force-downgrade`; this flag never overrides
ownership checks. Uninstall and dedupe remove only unchanged owned files or
native links, leaving edited and unknown survivors.

`dummyindex check --versions` distinguishes version drift from source/content
drift. The update skill resolves its requested GitHub ref to an immutable commit
before installation and checks CLI, workflow, and source identity afterwards.
A matching version alone does not establish a complete update.

## Project integration

Shipped shell scripts use LF on every checkout so Windows line endings cannot
break Bash execution.

`dummyindex/installer/install/project_init.py` preserves a curated index while
refreshing derived maps. Claude-selected initialization wires existing managed
hooks/plugins; agents-selected initialization writes the existing managed host
guidance. Equipment refresh runs for every selected host and continues to honor
generated-body ownership; native hooks/plugins retain their platform guard. Managed PreToolUse hooks match `Write|Edit|MultiEdit`;
re-install refreshes an older `Write` matcher; the citation guard covers all three
(`dummyindex/context/hooks.py:246-248`, `:275`). This feature owns placement and wiring; index, hook behavior, capability content,
and plugin policies stay with their features.
