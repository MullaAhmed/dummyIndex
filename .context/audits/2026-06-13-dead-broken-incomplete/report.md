# dummyindex full audit — 2026-06-13

Overnight autonomous audit + fix pass. Evidence-driven: mined the real BOS-Mono
sessions (where dummyindex was used in anger), confirmed each problem in code,
fixed with TDD, committed locally per cluster. **Nothing pushed.**

## TL;DR

- **Mined 34 BOS-Mono sessions + 4 live-state inspections → 339 issues → ~88
  confirmed defects** across 11 root-cause clusters.
- **13 fix commits**, all local. Test suite **1122 → 1545 passing** (+423 tests).
  A final cumulative cross-wave review (whole audit diff vs the pre-audit
  baseline) found 8 integration seams between the parallel waves — 2 HIGH (a
  legacy plugin record could leak into the build dispatch pool; a generated-doc
  template still called bare `rebuild` non-destructive) — all fixed in the 13th
  commit with regression tests.
- The two things you flagged as the worst pain are fixed:
  1. **The destructive `.context` footgun** — `install` / `rebuild` / `ingest`
     silently re-shattering a curated index into `community-N` stubs (it even
     happened on the frontend submodule, committed). Reproduced at HEAD, then
     guarded everywhere — including the subtle self-disarm where a once-shattered
     `INDEX.json` made the guard return "not curated" forever after.
  2. **The plugin manager** (your named "struggling with this") — discover
     ignoring the query/`--repo`, install unable to resolve a marketplace Claude
     already knows, manifests recorded as useless `kind: agent`/`version: null`,
     no post-install verification, wiring scattered between `settings.json` and
     `settings.local.json`.

## Your three asks

1. **Install skills/plugins/agents + a sources document/directory** — done.
   `docs/sources/installable-sources.md` is a verified catalog (34 sources, 18
   with native marketplaces, checked live via `gh`) with a documented promotion
   path into the code's `SEED_MARKETPLACES`. The audit also fixed two seed-drift
   bugs it surfaced (`anthropics/skills` is now a native marketplace, not a loose
   collection; `msitarzewski/agency-agents` is the reverse) and added 8 verified
   high-value seeds (superpowers, wshobson/agents, addyosmani, trailofbits, …).
   **Recommendation on a directory:** keep the catalog as the source of truth and
   the seed list in code; a new on-disk directory of vendored agents isn't needed
   — the marketplace + skills.sh + vendoring machinery already covers acquisition.
2. **Build/manage `.context` including updates** — the update story was the
   single largest source of pain and is now coherent: a clear two-layer contract
   (deterministic `rebuild --changed` refresh that never re-clusters a curated
   index, vs the read-only `reconcile` report → council enrichment →
   `reconcile-stamp`), the destructive paths refuse by default, drift no longer
   counts dummyindex's own files, a rebase-orphaned anchor reports honestly
   instead of a false all-clear, and the docs/skills now prescribe the correct
   (non-destructive) path instead of the destructive one.
3. **Wire/install/use specific plugins correctly** — see cluster C4 below; this
   was the most-broken surface and got the deepest fixes.

## The 11 clusters (what was wrong → what changed)

| # | Cluster | Worst symptom (from real sessions) | Fix commit |
|---|---------|-----------------------------------|-----------|
| C1 | Destructive rebuild | `install`/`rebuild`/`ingest` re-shatter a curated 14-feature taxonomy into 838 `community-N` stubs; a shattered `INDEX.json` permanently self-disarms the guard | `3b798f9` |
| C2 | Equip manifest | `equip apply` rebuilds `equipment.json` from scratch → silently drops plugin/vendored/specialist records | `941de86` |
| C3 | Reconcile/drift/gate | Tool's own files pollute drift forever; rebase-orphaned anchor gives a false all-clear; Stop gate blocks planning-only sessions | `205cc35` |
| C4 | Plugin manager | discover ignores query/`--repo`; install can't resolve a known marketplace; manifest entries useless for routing; no load verification | `941de86` |
| C5 | CLI help/safety | NO subcommand answered `--help`; bare `equip` ran a full apply when probed | `9183587` |
| C6 | Installer/versions | `install` dropped a user Stop hook; 4-layer version skew undetected; stale `.context` version stamp forever | `3b798f9` |
| C7 | Build routing | impl items never bound to the stack implementer (all → general-purpose); `— via` tags treated as hints; GATE items offered as dispatchable | `efc8e84` |
| C8 | Council/reality-check | 100%-false-positive "contradicted" runs from basename misresolution; `--demote` one-way; can't scope a recouncil | `6441a82` |
| C9 | Submodules/monorepo | preflight says "not a git repo" inside a submodule; no foreign-`.context` ownership guard | `4cff59b` |
| C10 | Skills/docs | documented remediations were destructive or nonexistent (`/dummyindex --recouncil`) | `e407f9e` |
| C11 | Output hygiene | generated `.context` trips pre-commit (whitespace/EOF/detect-secrets); inert `.tmpl` shipped into every repo | `7a9b1bd` |

## Method & rigour

- Every fix was written test-first (TDD); each wave was reviewed by the project's
  `python-reviewer` agent and its real findings fixed before commit (two
  cross-agent seam bugs were caught and fixed that way: `/dummyindex-build`
  sessions escaping the Stop gate, and a false "refreshed" hooks report).
- Durable anti-regression tests were added where a class of bug could recur: a
  CLI doc-sync test (help can't drift behind the verbs/schema), a skills-doc
  hygiene test (the destructive/nonexistent command strings can't return), and a
  manifest-merge test (foreign records must survive a re-apply).
- Full evidence corpus, per-cluster fix plans, and the running work log are under
  `docs/audits/2026-06-13-evidence/` and `docs/audits/2026-06-13-full-audit-log.md`.

## To actually get these fixes on your machine

The installed `dummyindex` CLI is a **copy** (the audit's install inspector found
it's currently a `pip --user` copy, not an editable install), so the repo fixes
are NOT live in your CLI until you reinstall. From the repo root:

```bash
uv tool install --force --editable /mnt/windows-ssd/Projects/memory/dummyindex
dummyindex --version            # confirm it matches the repo
dummyindex context check --versions   # new: diagnose any remaining skew
```

Then in the BOS-Mono repos, the new safe path: `dummyindex context status` to
see state read-only; nothing will re-shatter a curated index anymore.

## Open recommendations (not done — your call)

- **Dogfood `.context` on dummyindex itself.** dummyindex's own `.claude/CLAUDE.md`
  tells every session to read `.context/HOW_TO_USE.md`, but dummyindex has no
  `.context/`. Either build one (`dummyindex ingest` after reinstall — a large
  generated commit) or soften that CLAUDE.md line. Left for you because indexing
  is a big, opinionated artifact.
- **A few P2/P3 follow-ups** were deliberately deferred (e.g. `equip register`
  for local in-repo skills, cross-scope duplicate-install warnings, a
  reconcile-finish composite verb). They're listed in the per-wave agent reports
  captured in the work log.
