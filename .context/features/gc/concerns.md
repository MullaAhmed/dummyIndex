# GC boundaries

- Completion/status tags are signals, not permission to discard unique knowledge.
  Only the active host/user decides usefulness; the CLI enforces bounded guards.
- Explicit deletion confirmation remains required. Code implementation and tests
  do not authorize deleting personal old repositories or unrelated documents.
- The reference scan detects literal paths and common split path construction.
  It cannot prove the absence of every dynamically constructed dependency.
- Containment follows symlinks/junctions. The shared OS lock serializes cooperating
  writers; unrelated processes can still create filesystem races.
- Off-git targets keep the existing recoverability fallback. Missing semantic
  context is handled through explicit review and a receipt, not automatic erasure.
