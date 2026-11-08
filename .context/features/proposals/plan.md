# Proposal implementation map

1. Validate slug, scaffold four files, apply consistency/routing without discarding user-owned metadata:
   `dummyindex/context/domains/proposals/store.py:44`,
   `dummyindex/context/domains/proposals/store.py:174`.
2. Host reviews the seeded manifest (`gc closeout --draft`, `dummyindex/context/domains/proposals/draft.py:49`).
   Verify inventory, accepted snippets, scoped destinations and surviving inbound references:
   `dummyindex/context/domains/proposals/retirement.py:58`, `dummyindex/context/domains/proposals/retirement.py:75`.
3. Preflight all writes under the shared writer lock, publish a pending intent
   first and the receipt last. Failures restore preimages:
   `dummyindex/context/domains/proposals/closeout.py:583`, `dummyindex/context/domains/proposals/closeout.py:594`.
4. Release the lock, then run learning. Failures persist to the event or
   `.context/gc/learning/{kind}-{slug}.failed.json`, apart from the closeout. Only `failed` exits 1 (`dummyindex/cli/gc.py:124`):
   `dummyindex/context/domains/proposals/closeout.py:54`, `dummyindex/context/domains/proposals/closeout.py:260`.

Tests: `tests/context/domains/test_closeout.py`,
`tests/context/domains/test_closeout_draft.py`, `tests/cli/test_closeout_exit_codes.py`.
Usage/schema: `docs/guide/closeout.md`.
