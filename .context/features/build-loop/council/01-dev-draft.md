# Build-loop implementation map — plan

`confidence: INFERRED`

## Where it lives

- `dummyindex/context/domains/buildloop/checklist.py:72-320` owns identity,
  parsing, wave selection, selector errors and locked atomic mutations.
- `dummyindex/context/domains/buildloop/models.py:49-56` defines the frozen
  `ChecklistItem` record: position, text, state, group, gate, via and `item_id`.
- `dummyindex/cli/build_loop/waves.py:484-572` maps the frontier to bounded
  dispatch entries; `dummyindex/context/domains/buildloop/envelopes.py:13-46`
  defines bounded task/result handoffs and evidence requirements.
- `dummyindex/context/domains/buildloop/receipts.py:21-96` validates exact
  completion bindings and writes `checks.json` before closing a box.

## Architecture in three sentences

The parser derives stable identity and dependency groups from Markdown, then
`next_wave` selects the first incomplete group. The CLI maps that group to
host-native routes and bounded handoffs; the host performs execution and supplies
evidence. Checking and skipping both use the shared selector and project lock,
while receipt-aware checking holds that lock across evidence recording and the
checkbox rewrite.

## Data and decisions

Stable IDs outlive positional edits; `index:N` remains an explicit compatibility
selector. Unique exact text matches win before substring matching, and ambiguity
never guesses. The release adds candidate details only to the substring error:
the first five parsed items are shown in document order, followed by an omitted
count when needed (`dummyindex/context/domains/buildloop/checklist.py:152-208`).

Receipt records bind the selected task text hash, current source commit,
artifact identities, execution state and required evidence. Disposable workspace
paths cannot stand in for durable evidence; conflicting `task_id`/`item_id`
values fail (`dummyindex/context/domains/buildloop/receipts.py:54-96`).

Reconciliation remains scoped to actual session edits, and proposal closeout
preserves unresolved verification separately from work completed
(`dummyindex/context/reconcile_scope.py:13-55`,
`dummyindex/context/domains/proposals/closeout.py:347-379`). Capability hashes and
delegation guidance are not evidence of model compliance or measured gains.

## Verification and open questions

`tests/context/domains/test_build_loop.py:894-927` pins candidate names and retry
guidance; `tests/context/domains/test_build_stable_ids.py` protects selectors and
identity. `tests/context/domains/test_handoff_envelopes.py` covers bounded
handoffs. The integration adds no selector mode or configurable candidate limit;
no additional behavior decision is required for this change.
