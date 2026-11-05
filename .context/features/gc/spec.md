# Context-hygiene garbage collection

`confidence: EXTRACTED`

GC enumerates disposable proposal/audit workspaces and reports objective status,
completion, age and tracking signals. The active host judges usefulness and
obtains deletion confirmation. `context gc delete` is a dry run without `--yes`.
Source: `dummyindex/cli/gc.py:119`, `dummyindex/context/domains/gc/signals.py:38`,
`dummyindex/skills/gc/SKILL.md:1`.

Deletion guards validate the slug, reject sentinel containers, enforce realpath
containment, protect in-flight proposals and preserve untracked recoverability.
They then require knowledge closeout when material remains. Durable inbound
references, changed workspace hashes, interrupted closeout intents or missing
accepted text/fixtures block retirement. `force_partial` and `allow_untracked`
do not bypass this knowledge guard. Source: `dummyindex/context/domains/gc/delete.py:65`,
`dummyindex/context/domains/proposals/retirement.py:143`.

Accepted knowledge transfers into existing durable homes before retirement;
completed closed work may then be deleted without losing reusable fixtures or
pending live verification. Empty scaffolds without unique material retain the
existing GC path. Audit reports use the same predelete transfer boundary.
Source: `dummyindex/context/domains/proposals/closeout.py:30`, `dummyindex/context/domains/proposals/retirement.py:178`.

The commit throttle and session memo only nudge a sweep; they never delete or
classify work as obsolete. Source: `dummyindex/context/domains/gc/anchor.py:95`.
