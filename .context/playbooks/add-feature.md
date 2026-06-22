# Playbook — add a feature

Use this when the user asks to add a new capability that doesn't exist yet (page, endpoint, component, job, integration).

## 1. Confirm it's new
- Grep `map/symbols.json` for similar names. If you find a near-match, this might be an **update** (see `update.md` if present) rather than an addition.
- Check `tree.json` for a directory that already groups this kind of thing.

## 2. Decide where it goes
- Mirror an existing feature's location and structure. Find a peer feature in `tree.json`.
- Honor `conventions/naming.md`. Match casing for files, classes, functions, and methods.

## 3. Test first
- If `tests/` exists, write a test in the mirrored path before touching production code.
- Use the same test framework the rest of the project uses (look for pytest, jest, vitest, etc. in `PROJECT.md` or `map/files.json`).

## 4. Implement
- Start from the mirrored peer feature; change identifiers and adapt logic.
- Wire imports / routes / exports the same way the peer does it.

## 5. Verify and re-index
- Run the project's test command (look in `PROJECT.md` entry points or scripts).
- `dummyindex context rebuild --changed` refreshes the deterministic map (symbols, files, tree) against your edits and preserves curated feature docs. **A new feature is also new code that belongs to no feature yet** — so after committing, run the reconcile procedure (`dummyindex context reconcile` → place/enrich → `dummyindex context reconcile-stamp`, see `council/65-reconcile.md`) so a feature owns the new files.

## Common pitfalls
- Adding a duplicate of something that already exists (always check `map/symbols.json` first).
- Naming inconsistent with `conventions/naming.md`.
- Forgetting the export / registration step — find the existing wiring file in `tree.json`.
