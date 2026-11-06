# Proposal store and closeout

`confidence: EXTRACTED`

Proposals are disposable planning workspaces headed by `proposal.json`, with
`spec.md`, `plan.md`, and `checklist.md`. The deterministic CLI scaffolds them
and records related features/conventions; the active host authors the plan.
Source: `dummyindex/context/domains/proposals/store.py:70`, `dummyindex/context/domains/proposals/scan.py:24`.

Closeout explicitly reviews every workspace file hash and classifies accepted
lessons, decisions, evidence and fixtures or records a discard reason. Accepted
text appends to existing durable Markdown homes; fixtures copy into stable
`tests/` locations without overwriting different content. Paths, source hashes,
inbound durable references and destination preimages are checked before writes.
Source: `dummyindex/context/domains/proposals/closeout.py:31`, `dummyindex/context/domains/proposals/closeout.py:259`.

`context build --proposal S --closeout FILE` closes proposals;
`context gc closeout --kind audit --slug S --manifest FILE` applies the same
knowledge boundary to audits. Neither command deletes a workspace.
A compact receipt under `.context/gc/closeouts/` preserves the source revision,
reviewed inventory, accepted unit hashes, task receipts, explicit owned paths,
supersession reasons and independent pending live verification. States
`implemented`, `evaluated`, `applied`, and `verified` remain distinct.
Source: `dummyindex/cli/build_loop/dispatch.py:109`, `dummyindex/cli/gc.py:59`.

Named live-only checklist items move to pending verification; they do not keep
implemented work open. Accepted closeout evidence queues one bounded learning
event. A supplied structured reflection can use the ordinary exact-candidate
gate; absent reflection is handled by the active host, not an autonomous daemon.
Source: `dummyindex/context/domains/proposals/closeout.py:347`, `dummyindex/context/domains/proposals/closeout.py:195`.
