# GC implementation map

1. Enumerate workspace candidates and gather objective signals:
   `dummyindex/context/domains/gc/enumerate.py:36`, `dummyindex/context/domains/gc/signals.py:38`.
2. Review accepted lessons/evidence/fixtures, repair durable dependencies and
   invoke shared closeout for material workspaces before proposing retirement:
   `dummyindex/cli/gc.py:59`.
3. After explicit user confirmation, delete exactly the validated target through
   the guard ladder; generated receipts remain outside it:
   `dummyindex/context/domains/gc/delete.py:65`, `dummyindex/context/domains/proposals/retirement.py:143`.
4. Advance the GC throttle anchor separately; reconciliation is scoped to source
   work actually owned by this session: `dummyindex/context/domains/gc/anchor.py:126`.

Tests: `tests/context/domains/gc/test_delete.py`,
`tests/context/domains/test_closeout.py`.
