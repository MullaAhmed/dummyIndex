# Playbook — fix a bug

## 1. Reproduce first
- Re-state the bug in your own words. If the symptom is unclear, ask the user one surgical question.
- Find the smallest set of inputs that reproduce it.

## 2. Locate the suspected code
- Search `map/symbols.json` for the symptom's surface (the API, the CLI, the UI handler).
- Walk inward via call sites — `tree.json` gives you parent/child structure; for cross-file callers, grep is fine.

## 3. Write a failing test
- Locate the project's test file for that module via `tree.json` or `map/files.json`.
- Add a test that fails with the current code and passes with the fix. This becomes the regression test.

## 4. Make the minimal fix
- Smallest possible change. No drive-by refactors.
- Honor `conventions/naming.md` — even one-line additions.

## 5. Verify
- Run the project's test suite.
- Confirm the failing test now passes; confirm no other tests broke.

## 6. Re-index
- `dummyindex context rebuild --changed` refreshes the deterministic map (preserves curated feature docs). A bug fix rarely adds files, so this is usually enough; if the fix changed *how* a feature works, also update that feature's `spec.md`/`concerns.md` in-session or run the reconcile procedure (`council/65-reconcile.md`).

## Anti-patterns
- "Fix" by wrapping the symptom in a try/except — root cause it.
- Removing the failing assertion instead of fixing the underlying code.
- Reformatting unrelated lines in the same PR.
