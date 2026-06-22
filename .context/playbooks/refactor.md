# Playbook — refactor without behavior change

## 1. Set the boundary
- What's in scope (one symbol? a directory?). What's *not*.
- Write down the public surface that must not change.

## 2. Lock behavior with tests
- If the affected code lacks tests, add them *before* refactoring. Use `map/symbols.json` to find every entry point in scope.
- Tests should fail if behavior changes — that's the whole point.

## 3. Make the refactor in small, reversible steps
- Rename → move → extract → re-organize. One commit per kind of change is easier to review.
- After each step, run tests. Stop at the first regression.

## 4. Honor conventions
- `conventions/naming.md` applies to new names introduced by the refactor (extracted helpers, renamed symbols).

## 5. Re-index after each substantive step
- `dummyindex context rebuild --changed` — keeps the deterministic map honest as you move things around (it preserves curated feature docs, never re-clusters). If a refactor moved code across feature boundaries, run the reconcile procedure (`council/65-reconcile.md`) afterward so feature ownership stays accurate.

## 6. Verify the public surface
- For each item in your "must not change" list, manually confirm it still matches.

## Anti-patterns
- Sneaking behavior changes into a "refactor" PR.
- Renaming things en masse without checking call sites.
- Skipping the tests-first step.
