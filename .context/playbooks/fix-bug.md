# Playbook — fix a bug

## 1. Reproduce first
- Re-state the bug in your own words. If the symptom is unclear, ask the user one surgical question.
- Find the smallest set of inputs that reproduce it.

## 2. Locate the suspected code
- Search `map/symbols.json` for the symptom surface: the API, the CLI, or the UI handler.
- Walk inward via call sites. `tree.json` gives parent and child structure. For cross-file callers, grep is fine.

## 3. Write a failing test
- Locate the project's test file for that module via `tree.json` or `map/files.json`.
- Add a test that fails on the current code and passes with the fix. This becomes the regression test.

## 4. Make the minimal fix
- Smallest possible change. No drive-by refactors.
- Honor `conventions/naming.md`, even for one-line additions.

## 5. Verify
- Run the project's test suite.
- Confirm the failing test passes now. Confirm no other tests broke.

## 6. Re-index
- `dummyindex context rebuild --changed` refreshes the deterministic map. It preserves curated feature docs.
- A bug fix rarely adds files, so this is usually enough.
- If the fix changed how a feature works, update that feature's `spec.md` or `concerns.md` in-session.
- Or run the reconcile procedure: invoke `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex. The procedure ships inside that installed skill.

## Anti-patterns
- Root-cause the bug. Do not wrap the symptom in a try/except.
- Do not remove the failing assertion instead of fixing the underlying code.
- No reformatting of unrelated lines in the same PR.
