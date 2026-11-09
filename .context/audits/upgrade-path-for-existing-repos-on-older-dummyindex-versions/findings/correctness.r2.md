## correctness — round 2

- **data-integrity#2 cache-key collision** — **adjust: medium → high (general repos)**
  - **Evidence**
    - **Path-blind lookup.** The cache key is content-only (`pipeline/io/cache.py:L106-L126`), so a second byte-identical file is served the first file's path-bound payload (`pipeline/extract/__init__.py:L197-L203`).
    - **No repair afterwards.** `id_remap` cannot rebind that payload (`extract/__init__.py:L249-L257`), and identical canonical records then dedupe (`context/build/portable_graph.py:L186-L200`).
    - **Cold-run repro.** data-integrity's repro shows this happens on a cold first run, not only on cache reuse.
    - **Common in real repos:** vendored library copies, the same generated stubs in several services, monorepo template or cookiecutter copies, and duplicated fixtures.
    - **Silent loss.** Those files' symbols, call edges and `path:range` citations disappear, or are attributed to the wrong file. There is no warning, and `coverage.json` and `map/files.json` still list the file.
  - **Why I raised it.** I rated it medium because this repo's only non-empty case is one re-export twin (`context/output/__init__.py`). That is a property of this repo, not of the defect. Empty files remain harmless.
  - **Final: confirmed, high.**

- **correctness#1 junctions** — **hold: medium**
  - **Evidence**
    - **Stamp aliasing is real but not new.** The aliasing data-integrity describes is also true for a healthy symlink. The Claude stamp read at `installer/install/orchestrate.py:L212-L214` and `installer/repair.py:L204-L212` is the same physical `.agents` file in both cases, and that is by design: `OURS_HEALTHY` is reported as "linked -> .agents (current)" (`repair.py:L258-L266`).
    - **What the junction actually adds** is missing labelling: no "(linked)" suffix (`cli/check.py:L224-L228`), so an aliased row is presented as an independent copy. That is a reporting defect, not new data harm.
    - **Content is safe.** It stays fail-closed, because `sync_family` refuses link paths (`installer/ownership.py:L167-L168`).
    - **The proposed fix is a shape, not a severity change.** over-engineering's single shared predicate (`ownership._is_link` used at `family_write.py:L128`, `classify.py:L244`, `check.py:L267`) is the right fix, and adopting it does not change the impact.
  - **Final: confirmed, medium.**

- **over-engineering#2 tree.json compaction vs data-integrity dispute** — **concur with data-integrity on omitting defaults; partial on `indent=2`**
  - **Evidence: omitting defaults**
    - **Breaks the stub classifier.** `_mechanical_abstract` returns False when `confidence` is absent (`context/build/navigation_refresh.py:L36-L38`) and when `abstract` is absent (`actual = node.get("abstract", "")`, L56-L58).
    - **Consequence.** With those keys omitted, every stub becomes "annotated": obsolete mechanical text is carried forward and a mass `source-stale` label is applied (L133-L153).
    - **Second reader.** `enrich-plan` selects only `EXTRACTED` stubs (`context/domains/enrich.py:L98-L110`).
    - **Prerequisite.** The omission is only safe if every reader first defaults a missing key to `EXTRACTED` plus the derived template.
  - **Evidence: dropping `indent=2`**
    - **No correctness defect.** Every reader parses JSON (`navigation_refresh.py:L27-L33`), and compact output already shipped for `symbol-graph.json` in 0.37.
    - **Constraint 1.** Both writers must change together (`context/build/tree.py:L331`, `navigation_refresh.py:L154-L158`), or the layout flips between the full-build and refresh paths.
    - **Constraint 2.** It conflicts with the stated keep-merge-conflicts-visible policy (`context/build/runner.py:L362-L368`). That is a workflow cost, not a correctness issue.
  - **Final:** the default-omission part is **disputed**; the indent part is **confirmed with that constraint**.

- **correctness r1 tree.json lost-abstracts (2,822 INFERRED at `cfe6a13` → 0 at `376e06d`)** — **adjust: it is a dummyindex defect, not purely history**
  - **The 376e06d loss itself cannot be attributed.** It happened inside a squash, and v0.36.0's enriched refresh never wrote `tree.json` (v0.36.0 `enriched_refresh.py:L25`).
  - **Current code can still silently discard enrichment**
    - **The guard ignores the tree.** The "bias to preserve" guard `enriched_index_status` looks only at the feature taxonomy (`context/build/incremental.py:L305-L333`), never at `tree.json` INFERRED abstracts.
    - **Unguarded overwrite.** When features read as unenriched, both `rebuild --changed` (`incremental.py:L162-L192`) and install auto-init (`installer/install/project_init.py:L121-L128`) fall through to `build_all`. `build_all` overwrites the tree from scratch (`context/build/runner.py:L496`) with no carry-forward and no warning.
    - **Only the explicit path warns.** `rebuild --full` warns (`cli/rebuild.py:L68-L76`); the automatic paths do not.
  - **Nothing detects or restores the loss.** No check or refresh compares the INFERRED count against the previous or committed `tree.json`.
  - **Why the severity is low.** It needs an "enriched tree but unenriched features" state, and the historical event cannot be attributed.
  - **Final: confirmed, low.**
