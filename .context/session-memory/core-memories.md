# Core memories

## 2026-08-25 | Never re-run the deterministic backbone over a curated index

After the initial council setup, NEVER regenerate the deterministic backbone
over the curated taxonomy — no bare `context rebuild`, no `rebuild --full`, no
raw `build_all` without bootstrap on an enriched repo. It re-clusters the
curated feature dirs into anonymous `community-N` stubs and clobbers
`features/INDEX.json` (observed live: 29 curated features → 92 stubs, working
tree, 2026-08-25; recovery was `git checkout -- .context/`). The only legal
refresh paths are:

- `dummyindex context rebuild --changed` (non-destructive: preserves taxonomy
  + enrichment)
- `context refresh-indexes`
- the reconcile procedure (`context reconcile` → place/enrich →
  `reconcile-stamp`) for folding committed code into the curated docs

When a raw rebuild has already clobbered the worktree, restore from git
(`git checkout -- .context/`) before any further council/reconcile work.
