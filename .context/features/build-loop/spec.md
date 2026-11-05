# Build checklist, identity and scoped completion

`confidence: EXTRACTED`

Dispatch batches are capped at eight items and 65,536 serialized bytes. Each
task/result handoff carries a stable task ID and at most 8,192 bytes. Selected
policy and capability references bind their actual loaded content hashes.

The CLI exposes the earliest incomplete dependency wave. The active host runs
independent items, judges their outcomes, and updates checklist state. Capability
routing and shared task envelopes are data for native delegation, not evidence
that a tool was installed, invoked or obeyed.
Source: `dummyindex/cli/build_loop/waves.py:1`, `dummyindex/skills/build/SKILL.md:1`.

Each parsed item has a stable identity: an explicit `<!-- task:ID -->` marker or
an item-text hash. Reordering/checking/skipping does not change identity.
External task/result payloads use `task_id`; `item_id` remains a legacy receipt
alias and conflicting identities are rejected. Ambiguous text/numeric selectors
fail; `index:N` explicitly requests a positional legacy selector.
Source: `dummyindex/context/domains/buildloop/checklist.py:70`, `dummyindex/context/domains/buildloop/checklist.py:150`.

`build --check ID --receipt FILE` binds task text, source commit, scoped artifact
hashes and outcome evidence before storing a per-task execution state in
`checks.json`. A legacy checkbox alone is unverified. Proposal closeout carries
these compact records outside the disposable workspace.
Source: `dummyindex/context/domains/buildloop/receipts.py:16`, `dummyindex/context/domains/buildloop/receipts.py:42`.

Closeout distinguishes implementation from evaluation/application/verification;
live deployment/browser checks are tracked separately. Reconciliation belongs
only to actual session-edited paths and their owning features. Unknown subagent
edit counts or unrelated stale roots produce advisory output, not a demand to
repair every discovered index. Source: `dummyindex/context/domains/proposals/closeout.py:352`,
`dummyindex/context/reconcile_scope.py:13`,
`dummyindex/context/reconcile_gate.py:346`.
