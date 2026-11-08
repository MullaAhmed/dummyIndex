# GC implementation map

1. Enumerate candidates, gather signals, recommend:
   `dummyindex/context/domains/gc/enumerate.py:36`, `dummyindex/context/domains/gc/signals.py:38`,
   `dummyindex/context/domains/gc/recommend.py:18`.
2. Review accepted lessons, evidence, fixtures; repair durable dependencies.
   Run closeout for material workspaces before proposing retirement. `gc closeout --draft`
   seeds manifest: `dummyindex/cli/gc.py:66`, `dummyindex/context/domains/proposals/draft.py:49`.
3. After explicit confirmation, delete exactly the validated target through
   the guard ladder; receipts stay outside it:
   `dummyindex/context/domains/gc/delete.py:101`, `dummyindex/context/domains/proposals/retirement.py:169`.
4. Advance GC anchor separately (`gc stamp`): `dummyindex/context/domains/gc/anchor.py:147`.
   Reconciliation claims only explicitly owned `changed_paths` (`dummyindex/context/domains/proposals/closeout.py:353`).

Tests: `tests/context/domains/gc/test_delete.py`,
`tests/context/domains/test_closeout.py`, `tests/context/domains/test_closeout_draft.py`.
