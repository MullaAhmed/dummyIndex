# Build checklist, identity and scoped completion — spec

`confidence: INFERRED`

## Intent

Expose the earliest incomplete wave. Preserve each task's identity. Distinguish a checked box from evidence the selected work was executed.

The active host executes and judges tasks. The CLI supplies bounded dispatch records and validates explicit completion evidence.

## User-visible behavior

Wave dispatch returns at most eight items and 65,536 serialized bytes. It reports full group size and marks omitted items as `truncated`. A single oversized item fails instead of emitting an incomplete record (`dummyindex/cli/build_loop/waves.py:484-542`). Task/result envelopes are limited to 8,192 bytes. A verified envelope requires evidence references (`dummyindex/context/domains/buildloop/envelopes.py:10-46`). Capability routing and hashes describe native delegation inputs, not proof that a tool ran. Unticked live or production-testing items lacking `<!-- live-ok: reason -->` make `build --next` and `--next-wave` exit 2 (`dummyindex/cli/build_loop/waves.py:446`, `dummyindex/context/domains/buildloop/checklist_lint.py:27`).

Checklist items use an explicit `<!-- task:ID -->` marker or a text-derived identity. Reordering, checking, and the normal skip annotation preserve that identity (`dummyindex/context/domains/buildloop/checklist.py:72-129`). Selectors resolve stable IDs first. They support `index:N` for an explicit zero-based position. They reject conflicting numeric labels. They prefer a unique exact text match over substring matches. Empty or ambiguous selectors fail before mutation. An ambiguous substring error lists up to five `index: text` candidates. It names any remaining count and says `retry with an index`. Stable-ID and numeric ambiguity keep separate errors (`dummyindex/context/domains/buildloop/checklist.py:152-208`).

`build --check ID --receipt FILE` records validated task text, source commit, artifact identities and outcome evidence in `checks.json`. It runs before checking the box. External records use `task_id`. Legacy `item_id` remains accepted only when it does not conflict. A checkbox without a receipt is unverified (`dummyindex/context/domains/buildloop/receipts.py:21-96`).

Build guidance forwards remaining budgets and preserves the working deliverable. It runs acceptance and affected checks first. Baseline comparisons run in a separate copy. This is host guidance, not a measured claim of agent-quality improvement. Closeout keeps pending verification distinct. Reconciliation attributes only session-owned edits (`dummyindex/context/reconcile_scope.py:13-55`, `dummyindex/context/domains/proposals/closeout.py:333-362`).

## Contracts

- `parse_checklist(path: Path) -> tuple[ChecklistItem, ...]` parses checkbox state, dependency groups, gate/via tags and stable IDs (`dummyindex/context/domains/buildloop/checklist.py:84-129`).
- `next_wave(items: tuple[ChecklistItem, ...]) -> tuple[ChecklistItem, ...]` returns unchecked items in the first unfinished group. All done returns `()` (`dummyindex/context/domains/buildloop/checklist.py:132-143`).
- `flip_item(path: Path, key: int | str) -> ChecklistItem` checks one item idempotently. `skip_item(path: Path, key: int | str, reason: str) -> ChecklistItem` requires a nonempty reason. It refuses an already closed item. Both serialize cooperating writers through the project lock (`dummyindex/context/domains/buildloop/checklist.py:245-320`).
- `check_with_receipt(path: Path, key: str, receipt_path: Path) -> ChecklistItem` validates and records evidence under the same lock (`dummyindex/context/domains/buildloop/receipts.py:21-51`).

## Example

Given `Build parser <!-- task:parser -->` and `Build renderer <!-- task:renderer -->`, selecting `Build` fails. It lists both indices and leaves the checklist unchanged. `parser` selects the stable task ID. `index:1` selects the second position. Pinned by `tests/context/domains/test_build_loop.py:894-927`.
