# Playbook — add a feature

Use this when the user asks for a new capability not present yet (page, endpoint, component, job, integration).

## 1. Confirm it's new
- Grep `map/symbols.json` for similar names. If a near-match exists, treat it as an **update**, not an addition (see `update.md` if present).
- Check `tree.json` for a directory that already groups this kind of thing.

## 2. Decide where it goes
- Mirror an existing feature's location and structure. Find a peer feature in `tree.json`.
- Honor `conventions/naming.md`. Match casing for files, classes, functions, and methods.

## 3. Test first
- If `tests/` exists, write a test in the mirrored path. Do this before touching production code.
- Use the same test framework as the rest of the project. Look for pytest, jest, vitest, etc. in `PROJECT.md` or `map/files.json`.

## 4. Implement
- Start from the mirrored peer feature. Change identifiers and adapt logic.
- Wire imports, routes, and exports the same way the peer does.

## 5. Verify and re-index
- Run the project's test command. Find it in `PROJECT.md` entry points or scripts.
- `dummyindex context rebuild --changed` refreshes the deterministic map (symbols, files, tree) against your edits. It preserves curated feature docs.
- **A new feature is new code that belongs to no feature yet.** After committing, run `dummyindex context reconcile`.
- Then invoke `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex to place and enrich.
- Then run `dummyindex context reconcile-stamp` so a feature owns the new files.
- The reconciliation procedure ships inside that installed skill, not under `.context/playbooks/`.

## Common pitfalls
- Adding a duplicate of something that already exists. Always check `map/symbols.json` first.
- Naming inconsistent with `conventions/naming.md`.
- Forgetting the export or registration step. Find the existing wiring file in `tree.json`.
