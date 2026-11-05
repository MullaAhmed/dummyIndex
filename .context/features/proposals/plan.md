# Proposal implementation map

1. Validate the slug, scaffold the four files, then apply consistency/routing
   without discarding user-owned metadata: `dummyindex/context/domains/proposals/store.py:44`,
   `dummyindex/context/domains/proposals/store.py:174`.
2. Host review produces one invocation manifest. Verify the complete inventory,
   accepted snippets, scoped destinations and surviving inbound references:
   `dummyindex/context/domains/proposals/retirement.py:58`, `dummyindex/context/domains/proposals/retirement.py:75`.
3. Preflight all writes, use the shared project writer lock, publish a pending
   intent before changes and the durable receipt last. Ordinary failures restore
   preimages; interrupted work remains GC-protected until explicit reviewed resume:
   `dummyindex/context/domains/proposals/closeout.py:410`, `dummyindex/context/domains/proposals/closeout.py:421`.
4. Release the writer lock before post-closeout learning. Record learning failure
   separately from the already committed closeout: `dummyindex/context/domains/proposals/closeout.py:179`.

Regression coverage: `tests/context/domains/test_closeout.py`.
Usage/schema: `docs/guide/closeout.md`.
