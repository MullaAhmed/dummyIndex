# Close completed work without losing its lessons

Proposals and audit workspaces are disposable. Accepted rules belong in existing
feature/convention/capability documents; reusable fixtures belong under `tests/`.
Durable documents, skills and tests must not depend on proposal or audit paths.

Use `dummyindex context build --proposal SLUG --closeout FILE` for a proposal,
or `dummyindex context gc closeout --kind audit --slug SLUG --manifest FILE`.
`--json` returns the receipt. Closeout transfers only explicitly reviewed content;
it never deletes the workspace. Normal user-confirmed GC remains a separate step.

The invocation manifest is temporary evidence, not another setup subsystem:

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
Every nonadministrative file must supply a transfer or an explicit `discarded`
reason. Transfers use `kind: lesson|decision|evidence|fixture`; optional `content`
selects an exact accepted source snippet. Knowledge appends to an existing durable
Markdown home; fixtures copy into `tests/` and cannot overwrite different content.
The command preflights scope, symlinks/junctions, references and all transfers.

Keep production/browser/deployment verification outside implementation checklists.
For an existing live-only checkbox, add its `task_id` and a standalone description
to `pending_verification`; closeout removes that checkbox and retains the pending
check in `.context/gc/closeouts/<kind>-<slug>.json`. Remaining implementation items
must be complete. `disposition: abandoned|superseded` records intentional retirement
without claiming implementation; use `state: planned` when nothing was implemented.

States `implemented`, `evaluated`, `applied`, and `verified` are distinct.
Evaluated or later states require content-bound `evidence: [{path, sha256}]`.
The active host remains responsible for executing and judging those checks.
Optional `source_commit` must match the current revision. Ownership records only
explicit changed paths; unrelated drift is not inherited work.

GC validates the compact receipt, workspace hashes, accepted text units and fixture
hashes. Unrelated edits elsewhere in a convention do not invalidate a retained unit.
If a unit was intentionally replaced, rerun closeout with
`superseded: {"unit-ID": "replacement reason"}`. Changed workspaces, missing accepted
units, or surviving inbound references block retirement. Empty/abandoned scaffolds
without unique material retain their existing GC behavior.

Build frontiers expose stable `task_id` values. Use those instead of positions.

Repeated closeout retains unresolved live checks. Remove one only through
`resolved_verification: {ID: {state: "verified"|"discarded", reason: "...", evidence: [...]}}`;
the evidence must remain in a durable home. Reusing an accepted transfer ID with
different content is rejected; use a new ID and explicitly supersede the old one.
An optional `<!-- task:parser -->` marker keeps identity through wording changes;
otherwise identity comes from the item text. Reordering or checking does not change it.
Ambiguous selectors fail; `index:N` explicitly requests a positional legacy selector.

`build --check ID --receipt FILE` additionally validates `task_id`, `task_sha256`
(SHA256 of displayed item text), `source_commit`, state, and scoped artifact/evidence
hashes. It records the execution in `checks.json`, which closeout carries into the
durable receipt. A bare legacy checkbox carries no such verification claim. Legacy `item_id`/`item_sha256` receipt fields remain readable; conflicting IDs are rejected. The shared delegation envelope also uses running/blocked states; implemented is a closeout/receipt state, not a claim of final verification.

An interrupted closeout leaves a compact pending intent and remains GC-protected. Review the current workspace hashes and rerun with `resume_interrupted: true`; the intent preserves pending live checks. The durable receipt publishes last, and the OS writer lock releases after a process exits. An optional `learning_reflection` invokes the existing exact gate after the closeout lock is released; an absent reflection leaves one bounded event for the active host.

Audits use reflection-only learning. Finish `report.md` before hashing the
workspace, then account for every file; `discarded` records review disposition
and does not delete anything. Keep the manifest outside `.context/audits/`.
The reflection cites durable source and test files, never the temporary audit
report. The common learning path preserves authored convention text, updates
one managed rule, and runs the named existing project tests. A missing
applicable test remains `evaluated`/`blocked` and leaves the convention alone.

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
    "verified": true,
    "target": ".context/conventions/coding.md",
    "rule_id": "parser-normalization",
    "body": "Use parse_token for whitespace normalization; see src/parser.py:L1-L2 and tests/test_parser.py:L1-L4.",
    "expected_sha256": "CURRENT_CONVENTION_SHA256",
    "sources": ["src/parser.py", "tests/test_parser.py"],
    "tests": ["tests/test_parser.py"]
  }
}
```
