# Playbook — refactor without behavior change

## 1. Set the boundary
- Define scope: one symbol, or one directory. Define what is not in scope.
- Write down the public surface that must not change.

## 2. Lock behavior with tests
- If the affected code lacks tests, add them before refactoring.
- Use `map/symbols.json` to find every entry point in scope.
- Tests must fail if behavior changes. That is the whole point.

## 3. Make the refactor in small, reversible steps
- Order: rename, then move, then extract, then reorganize.
- One commit per kind of change is easier to review.
- After each step, run tests. Stop at the first regression.

## 4. Honor conventions
- `conventions/naming.md` applies to new names the refactor introduces.
- This includes extracted helpers and renamed symbols.

## 5. Re-index after each substantive step
- `dummyindex context rebuild --changed` keeps the deterministic map current.
- It preserves curated feature docs and never re-clusters.
- If a refactor moved code across feature boundaries, run the reconcile procedure afterward.
- Invoke `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex. This keeps feature ownership accurate.
- The procedure ships inside that installed skill.

## 6. Verify the public surface
- Manually confirm each item in your "must not change" list still matches.

## Anti-patterns
- Sneaking behavior changes into a "refactor" PR.
- Renaming things en masse without checking call sites.
- Skipping the tests-first step.
