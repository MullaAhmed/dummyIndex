# Proposal store and closeout

`confidence: EXTRACTED`

Proposals are disposable planning workspaces headed by `proposal.json`, with
`spec.md`, `plan.md`, and `checklist.md`. CLI scaffolds them; the active host
authors the plan. Source: `dummyindex/context/domains/proposals/store.py:70`.

Closeout reviews every file hash and classifies accepted lessons,
decisions, evidence and fixtures, or records a discard reason. Accepted text
appends to existing durable Markdown homes; fixtures copy into stable `tests/`
locations without overwriting different content. Paths, hashes, inbound
references and destination preimages are checked before writes.
Source: `dummyindex/context/domains/proposals/closeout.py:59`, `dummyindex/context/domains/proposals/closeout.py:594`.

`context build --proposal S --closeout FILE` and `context gc closeout --kind audit`
apply the same knowledge boundary. Neither deletes a workspace. Only a `failed`
learning state exits 1; `blocked` and `pending` exit 0.
Source: `dummyindex/context/domains/proposals/closeout.py:37`, `dummyindex/cli/gc.py:124`, `dummyindex/cli/build_loop/dispatch.py:228`.

A compact receipt under `.context/gc/closeouts/` keeps source revision and
reviewed inventory. It also keeps unit hashes, task receipts, owned paths,
supersession reasons and pending verification. `implemented`, `evaluated`,
`applied` and `verified` stay distinct.

Live-only checklist items move to pending verification; they do not keep
implemented work open. Learning runs after the writer lock releases, only with
transfers or a reflection. A settled status is reused; `failed` or `pending`
retries. A reflection must pass `validate_lesson` before any write. Templates
forbid live-testing steps; `live-ok` marks false positives.
Source: `dummyindex/context/domains/proposals/closeout.py:88`, `dummyindex/context/domains/proposals/closeout.py:150`, `dummyindex/context/domains/proposals/store.py:229`.
