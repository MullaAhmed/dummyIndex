# Build checklist, dispatch and completion — plan

`confidence: INFERRED`

## Bounded context

This feature owns Markdown task identity, dependency-wave selection, equipment
routing and completion receipts. It emits work for the active host; it does not
execute agents or decide whether their reported work is correct.

| Boundary | Source |
|---|---|
| Parse IDs, groups and selectors; mutate checklist under the project lock | `dummyindex/context/domains/buildloop/checklist.py:72-320` |
| Select an equipment capability for ordinary task text | `dummyindex/context/domains/buildloop/mapping.py:335-387` |
| Translate gates, via tags and capability choices into dispatch records | `dummyindex/cli/build_loop/waves.py:239-348` |
| Bound task/result envelopes and bind actual capability/policy bytes | `dummyindex/context/domains/buildloop/envelopes.py:10-127` |
| Validate and record completion before checking the box | `dummyindex/context/domains/buildloop/receipts.py:21-96` |

## Control flow and patterns

1. **Parse and select.** `parse_checklist` derives `ChecklistItem` records;
   `next_wave` returns unfinished items in the first unfinished group. Explicit
   wave headings permit parallel work; a flat checklist remains serial
   (`dummyindex/context/domains/buildloop/checklist.py:84-143`,
   `dummyindex/context/domains/buildloop/models.py:49-56`). The parser trusts the
   authored grouping; it does not infer file independence.
2. **Dispatch records, host execution.** The CLI resolves routing, chooses at
   most eight frontier items, attaches handoffs and drops trailing entries until
   the payload fits 65,536 bytes. It reports `group_total` and `truncated`; a
   single oversized record fails. Each handoff separately caps its serialized
   content at 8,192 bytes (`dummyindex/cli/build_loop/waves.py:484-542`,
   `dummyindex/context/domains/buildloop/envelopes.py:13-46`). A gate remains
   main-session work even when an agent tag is present
   (`dummyindex/cli/build_loop/waves.py:266-292`).
3. **Record before closing.** `check_with_receipt` holds the same lock as plain
   check/skip, validates task text, source commit and current artifact bytes,
   writes `checks.json`, then flips the checkbox. The two files are ordered
   writes, not a transaction: a receipt may survive a failed checkbox rewrite
   (`dummyindex/context/domains/buildloop/receipts.py:21-51`).

## Dependencies and feedback

Upstream inputs are proposal/checklist Markdown, routing metadata and the equip
manifest. `task_binding` reads the selected capability body and optional policy
files; the host consumes their recorded identities and `role_path`
(`dummyindex/context/domains/buildloop/envelopes.py:49-127`,
`dummyindex/cli/build_loop/waves.py:320-336`). Downstream completion receipts
return to the same checklist, forming an artifact feedback loop rather than an
agent-execution import cycle. The lock is reused from the sibling evolution
promotion domain (`dummyindex/context/domains/buildloop/checklist.py:295-320`).
Proposal closeout/reconciliation are adjacent lifecycle consumers, not owned
execution engines; their implementation stays outside this bounded context.

## Decisions and tradeoffs

- Stable explicit IDs survive text edits; fallback IDs hash the original task
  text. `index:N` remains a deliberate positional escape hatch. Unique exact
  text wins before substring matching, and conflicting numeric labels fail
  instead of guessing (`dummyindex/context/domains/buildloop/checklist.py:72-81`,
  `dummyindex/context/domains/buildloop/checklist.py:152-208`).
- Candidate errors show five items in document order plus an omitted count,
  keeping broad selectors useful without dumping the checklist
  (`dummyindex/context/domains/buildloop/checklist.py:191-202`).
- Receipts distinguish implementation from evaluated/applied/verified work;
  the latter states require evidence. Evidence cannot live in disposable
  proposal/audit/cache directories. Identity checks establish matching bytes,
  not model compliance or task-quality gains
  (`dummyindex/context/domains/buildloop/receipts.py:54-96`).

## Verification seam

`tests/context/domains/test_build_loop.py:894-927` protects candidate reporting;
`tests/context/domains/test_build_stable_ids.py:22-222` covers identity, numeric
ambiguity and cooperating writers. `tests/context/domains/test_handoff_envelopes.py:8-29`
protects policy identities, envelope limits and evidence requirements. This
release changes substring-error detail, not selector modes or wave semantics.
