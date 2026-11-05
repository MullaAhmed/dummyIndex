# Build-loop implementation map

1. Parse checkbox state, stable IDs, gates/via tags and dependency groups:
   `dummyindex/context/domains/buildloop/checklist.py:82`, `dummyindex/context/domains/buildloop/models.py:49`.
2. Resolve the earliest incomplete wave and host-native capability route; emit
   one compact task envelope per item: `dummyindex/cli/build_loop/waves.py:484`.
3. Host execution supplies individual evidence. Receipt-aware check validates
   exact identity and scope before recording state and ticking the selected task:
   `dummyindex/context/domains/buildloop/receipts.py:16`.
4. Reconcile only owned edits, close the proposal with durable transfer/pending
   verification records, then process at most one accepted learning event:
   `dummyindex/context/reconcile_scope.py:13`,
   `dummyindex/context/domains/proposals/closeout.py:30`.

Tests: `tests/context/domains/test_build_stable_ids.py`,
`tests/context/domains/test_build_loop.py`, `tests/context/test_reconcile_scope.py`.
