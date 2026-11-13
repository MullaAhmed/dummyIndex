# Close completed work without losing its lessons

Proposals and audit workspaces are disposable. Accepted rules belong in existing feature/convention/capability documents. Reusable fixtures belong under `tests/`. Durable documents, skills, and tests must not depend on proposal or audit paths.

Use `dummyindex context build --proposal SLUG --closeout FILE` for a proposal.
For an audit, use `dummyindex context gc closeout --kind audit --slug SLUG --manifest FILE`.
`--json` returns the receipt.
Closeout transfers only explicitly reviewed content.
It never deletes the workspace.
Normal user-confirmed GC remains a separate step.

The invocation manifest is temporary evidence:

```json
{
  "state": "implemented",
  "reviewed_files": {"proposal.json": "SHA256", "checklist.md": "SHA256", "lesson.md": "SHA256"},
  "transfers": [{"kind": "lesson", "source": "lesson.md", "target": ".context/conventions/coding.md"}],
  "discarded": {},
  "pending_verification": [],
  "ownership": {"task_id": "task-ID", "changed_paths": ["src/parser.py"], "reconciled_paths": []}
}
```

`reviewed_files` must cover every current workspace file with its exact SHA256.
Every nonadministrative file must supply a transfer or an explicit `discarded` reason.
Transfers use `kind: lesson|decision|evidence|fixture`. Optional `content` selects an exact accepted source snippet.

Knowledge appends to an existing durable Markdown home.
Fixtures copy into `tests/`. A fixture cannot overwrite different content.
The command preflights scope, symlinks/junctions, references, and all transfers.

Keep production/browser/deployment verification outside implementation checklists.
For an existing live-only checkbox, add its `task_id` and a standalone description to `pending_verification`.
Closeout removes that checkbox. It retains the pending check in `.context/gc/closeouts/<kind>-<slug>.json`.

Remaining implementation items must be complete.
`disposition: abandoned|superseded` records intentional retirement without claiming implementation.
Use `state: planned` when nothing was implemented.

States `implemented`, `evaluated`, `applied`, and `verified` are distinct.
Evaluated or later states require content-bound `evidence: [{path, sha256}]`.
The active host remains responsible for executing and judging those checks.
Optional `source_commit` must match the current revision.
Ownership records only explicit changed paths.
Unrelated drift is not inherited work.

GC validates the compact receipt, workspace hashes, accepted text units, and fixture hashes.
Unrelated edits elsewhere in a convention do not invalidate a retained unit.
If a unit was intentionally replaced, rerun closeout with `superseded: {"unit-ID": "replacement reason"}`.
Changed workspaces, missing accepted units, or surviving inbound references block retirement.
Empty/abandoned scaffolds without unique material retain their existing GC behavior.

Build frontiers expose stable `task_id` values.
Use those instead of positions.

Repeated closeout retains unresolved live checks.
Remove one only through `resolved_verification: {ID: {state: "verified"|"discarded", reason: "...", evidence: [...]}}`.
The evidence must remain in a durable home.
A reused accepted transfer ID is rejected when its content differs.
Use a new ID and explicitly supersede the old one.

An optional `<!-- task:parser -->` marker keeps identity through wording changes.
Otherwise, identity comes from the item text.
Reordering or checking does not change it.
Ambiguous selectors fail.
`index:N` explicitly requests a positional legacy selector.

`build --check ID --receipt FILE` also validates `task_id`, `task_sha256` (SHA256 of displayed item text), `source_commit`, and state.
It also validates scoped artifact and evidence hashes.
It records the execution in `checks.json`, which closeout carries into the durable receipt.

A bare legacy checkbox carries no such verification claim.
Legacy `item_id`/`item_sha256` receipt fields remain readable.
Conflicting IDs are rejected.
`implemented` is a closeout state, not final verification.

An interrupted closeout leaves a compact pending intent and remains GC-protected.
Review the current workspace hashes and rerun with `resume_interrupted: true`.
The intent preserves pending live checks.
The durable receipt publishes last, and the OS writer lock releases after a process exits.
A present `learning_reflection` runs the exact gate after the closeout lock releases.
An absent one leaves one bounded event for the host.

Audits use reflection-only learning.
Finish `report.md` before hashing the workspace.
Then account for every file.
The `discarded` field records review disposition.
It does not delete anything.
Keep the manifest outside `.context/audits/`.

The reflection cites durable source and test files, never the temporary audit report.
The common learning path preserves authored convention text, updates one managed rule, and runs the named existing project tests.
A missing applicable test remains `evaluated`/`blocked` and leaves the convention alone.

```json
{
  "state": "implemented",
  "source_commit": "CURRENT_COMMIT",
  "reviewed_files": {"audit.json": "SHA256", "report.md": "SHA256", "findings/reviewer.md": "SHA256"},
  "transfers": [],
  "discarded": {
    "audit.json": "Administrative audit state; no durable lesson",
    "report.md": "Final report retained for the user; learning is cited to source and tests",
    "findings/reviewer.md": "Temporary review notes; confirmed lesson is captured below"
  },
  "learning_reflection": {
    "cue": "parsing tokens", "lesson": "use parse_token for whitespace normalization", "evidence": "src/parser.py:L1-L2", "confidence": "high",
    "verified": true,
    "target": ".context/conventions/coding.md",
    "rule_id": "parser-normalization",
    "expected_sha256": "CURRENT_CONVENTION_SHA256",
    "sources": ["src/parser.py", "tests/test_parser.py"],
    "tests": ["tests/test_parser.py"]
  }
}
```

## Lesson records and learning status

The `learning_reflection` above is one lesson object, not a list.
`cue`, `lesson`, and `evidence` are non-empty strings.
`confidence` is `low|medium|high`.
Optional `edits` rows need `component`, `change`, `verdict` (`helped|hurt|no_observed_effect|confounded`).

`body` is ignored for a lesson.
The rule becomes `When {cue}: {lesson}`.
Cite it via `sources`/`evidence`.
A pre-change reflection (with `body`, no lesson fields) still closes, warns once, and reports `legacy_shape`.

Learning status is `applied|evaluated|blocked|no_entry|pending|ignored|failed`, persisted in the learning event file, or `.context/gc/learning/<kind>-<slug>.failed.json` if failure precedes it.
Receipt bytes are never rewritten.
Re-running closeout retries after `failed`.
For `gc closeout`, `build --closeout`, and `evolve learning`, only `failed` exits non-zero.
`blocked` exits 0.
