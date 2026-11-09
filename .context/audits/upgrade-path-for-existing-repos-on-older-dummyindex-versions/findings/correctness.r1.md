## correctness — round 1

### correctness.md (own)

- correctness#1 junctions — **defend (it is a dummyindex bug), concede severity high→medium** — evidence:
  - **The trigger came from the user's environment, not from dummyindex.** `git grep -i "junction|mklink|CreateJunction"` finds nothing in `dummyindex/` at v0.36.0 or v0.37.0.
  - **Timestamps show a script made the junctions.** The `~/.agents/skills/dummyindex*` dirs were all created at 05-11-2026 18:00:02, which is a 0.36 install. The 10 `~/.claude/skills` junctions were created 2 minutes later (18:02:02→18:02:05) in **alphabetical** order (audit, build, equip, evolve, fleet, gc, plan, remember, update). That is not the installer's `_family_names()` order (`installer/link/families.py:L23-L24`: main, remember, plan, equip, build, audit, gc, fleet, update, evolve). So an external glob loop created them, most likely a user or agent working around missing symlink privilege.
  - **The defect is still dummyindex's.** Its own link predicates contradict each other. `ownership._is_link` recognizes reparse points (`installer/ownership.py:L63-L73`), while `classify._classify` uses only `S_ISLNK` (`installer/link/classify.py:L230-L249`) and `_install_skill_references` uses only `is_symlink()` (`installer/install/family_write.py:L128`).
  - **Consequences.** The install exits 1 on every run, and repair's promise to convert the copy "the next time" can never be kept (`installer/repair.py:L307-L326` vs `installer/link/create.py:L354-L361`).
  - **Why I concede severity.** The skill content is functionally correct, because the junction serves the freshly written `.agents` copy. The harm is a permanent exit 1, false source warnings and a halted update skill, not stale or lost content.
  - status: **open → confirmed (medium)**
- correctness#2 one-version legacy catalog — **defend** — the chain holds: `installer/legacy_fingerprints.py:L7` → `installer/ownership.py:L106-L116` → `ownership.py:L197-L202,L217,L234` → `installer/repair.py:L477-L481`. The rendered `__VERSION__` (`installer/common.py:L208`) guarantees a byte mismatch for every installed version ≤0.35. — status: **open → confirmed**
- correctness#3 empty companion dirs — **defend** — reproduced in the scratchpad (`installer/ownership.py:L207-L216` vs `L139-L142`). — status: **open → confirmed**
- correctness#4 editable PACKAGE_VERSION — **defend** — the venv `check --versions` reports false skew while its `running CLI source` hash equals the uv tool's (`installer/common.py:L11-L16`, `cli/check.py:L295-L357`). — status: **open → confirmed**
- correctness#5 meta stamp downgrade — **defend; also concur with data-integrity#4** — it is a sibling defect in the same `_refresh_meta`: `context/build/enriched_refresh.py:L298-L299` writes on `!=`, which contradicts L276-L278. — status: **open → confirmed**
- correctness#6 update-skill binary identity — **defend** — `skills/update/SKILL.md:L39,L79-L95,L114-L118,L163`. — status: **open → confirmed**
- correctness#7 PATH-shadow check — **defend** — reproduced: the same `.venv` binary was reported as shadowing itself (`.exe` suffix only), and the labels were inverted for the uv binary (`cli/check.py:L149-L166,L311-L344`). — status: **open → confirmed**
- correctness#8 no `.context/` retirement — **defend; merge with data-integrity#5, data-integrity#11 and over-engineering#7** — `cli/migrate.py:L35-L92` is reachable only from `cli/refresh.py:L36-L37`, and GC kind roots are proposals/audits only (`context/domains/gc/delete.py:L190-L194`). — status: **open → confirmed**
- correctness#9 `tokens.md` CRLF/no catalog — **defend** — `cmp` shows the file is byte-identical to the packaged copy, yet the manifest is `complete:false, files:{}` (`installer/common.py:L255-L265`). — status: **open → confirmed**
- correctness#10 unmarked `~/.claude/CLAUDE.md` registration and AGENTS.md workflow list — **defend; overlaps over-engineering#9** — `installer/install/orchestrate.py:L383-L395`, `context/output/agents_md.py:L44-L46`. — status: **open → confirmed**

### data-integrity.md

- data-integrity#1 orphan shards (`export/storage.py:L274-L286`) — **concur** — re-measured: 91 parts, 12 referenced by the manifest, 79 orphans totalling 73,171,940 B, and all 79 are git-tracked (`git ls-files … | wc -l` = 79). — status: **open → confirmed**
- data-integrity#2 cache-key collision (`pipeline/io/cache.py:L106-L126`) — **concur it is real; dispute severity high→medium** — evidence:
  - **It reproduces.** Re-verified against the current graph: 23 of 65 `__init__.py` files are missing from the symbol graph. They are the 22 empty ones plus `dummyindex/context/output/__init__.py`, which is a byte-twin of `context/domains/__init__.py`; the twin is present and `output/` is absent.
  - **The mechanism is as described.** The content-only key (`cache.py:L106-L126`) means `extract/__init__.py:L197-L203` serves file A's payload for file B. The `id_remap` (`L249-L257`) rebinds only the requesting path's own id.
  - **Why it matters less than "high".** In this repo the loss is files with no symbols plus one re-export twin. Real symbol and edge loss needs byte-identical non-trivial files (vendored copies, fixtures), and there is none here (one duplicate group in total). The issue is also outside the upgrade-path scope (`pipeline/io`).
  - status: **open → confirmed (medium)**
- data-integrity#3 unversioned cache (`pipeline/io/cache.py:L186-L208`) — **concur on the design; dispute impact for this upgrade** — `load_cached` checks only payload shape (`cache.py:L164-L183`). However `git diff --stat v0.36.0 v0.37.0 -- dummyindex/pipeline/` touches only `extract/__init__.py` (orchestration: `file_status`), `build/validate.py` and `io/detect.py`. No per-language extractor changed, so the 466 pre-tag entries are byte-equivalent for 0.36→0.37. The defect is latent, not active. — status: **open → confirmed (medium, latent)**
- data-integrity#4 meta stamped before the graph and catalog (`context/build/enriched_refresh.py:L154-L195`, `context/build/runner.py:L487-L489`) — **concur** — `write_meta` is the first write in `_write_all` (`runner.py:L488-L489`). The same ordering lets a failed install advance the repo stamp (`installer/install/orchestrate.py:L325-L344` runs before `L356-L361`). — status: **open → confirmed**
- data-integrity#5 curated install path runs no migrations (`context/build/enriched_refresh.py:L106-L110`) — **concur, narrowed** — evidence:
  - **What is true.** `ensure_context_gitignore`, `remove_legacy_enrich_plan` and `migrate_legacy_layout` are absent from the refresh path. They are called only at `context/build/runner.py:L483-L485` and `cli/refresh.py:L36-L37`.
  - **What is overstated ("runs none").** The curated install path does run three migrations: the legacy root-`CLAUDE.md` fold (`installer/install/project_init.py:L96-L101`, `reconcile_claude_md`), the config schema migration (`project_init.py:L343`, `_migrate_existing_config`) and the legacy hook scrub (`context/hooks.py:L506-L525`).
  - **No current harm in this repo.** `.context/.gitignore` already equals `_MANAGED_GITIGNORE_PATTERNS` (`runner.py:L343-L355`).
  - status: **open → confirmed (narrowed; merge with correctness#8)**
- data-integrity#6 symbol-graph format change with no version bump (`export/storage.py:L260-L268`) — **concur** — evidence:
  - `export/storage.py` does not exist at v0.36.0.
  - The v0.36.0 `graph_query/load.py:L64-L72` rejects anything without top-level `nodes`/`links`, whereas the current file starts with `{"counts":…,"format":"dummyindex-symbol-graph",…}`.
  - The meta gate checks only `schema_version > 1` (`context/build/meta.py:L14,L69-L73`).
  - status: **open → confirmed**
- data-integrity#7 lossy config round-trip (`context/domains/config.py:L614-L638`) — **concur** — `to_dict` emits a fixed key set with no extras (`config.py:L241-L260`). — status: **open → confirmed**
- data-integrity#8 fixed `.tmp` names and no build lock (`context/build/maps.py:L292-L296`) — **concur** — the `.tmp` name is fixed (`maps.py:L294`). No lock primitive is referenced in `context/build/`. `project_lock` exists only in `context/domains/evolve_promotion` and is used by GC delete (`context/domains/gc/delete.py:L80-L83`). — status: **open → confirmed**
- data-integrity#9 append-only cache — **concur** — `load_cached`/`save_cached` have no eviction (`pipeline/io/cache.py:L186-L240`). — status: **open → confirmed**
- data-integrity#10 evolve run dirs grow — **no independent check**; plausible from `context/domains/evolve.py:L917-L927`. — status: open
- data-integrity#11 `equipment-evals/` — **concur; duplicate of correctness#8 and over-engineering#7** — `domains/equip/lifecycle/manifest.py:L19-L21` is an orphaned comment for the deleted `EVALS_REL`. — status: **open → confirmed (merge)**
- data-integrity#12 experiment-notes is human-authored — **concur** — `.context/dummyindex-experiment-notes/README.md:L1-L4`. — status: **open → confirmed**

### over-engineering.md

- over-engineering#1 orphan shards — **concur** — same re-measurement as data-integrity#1 (`export/storage.py:L285`). — status: **open → confirmed**
- over-engineering#2 `tree.json` bloat and template abstracts (`context/build/tree.py:L324-L351`) — **concur on the current-state numbers and `indent=2`; refute the implication that the abstracts were never enriched** — evidence:
  - **Current state confirmed.** Re-counted: 6,504 nodes, all `EXTRACTED`, 0 non-template abstracts.
  - **History shows the abstracts were enriched and then lost.** The tree at `cfe6a13` had **2,822** `"confidence": "INFERRED"` abstracts (`70ac956`: 361). The count dropped to 0 at `376e06d` ("Chore/clean history", a squash including "deterministic backbone refresh, 14-feature recouncil"). This is curated-data loss that upgrading never restores.
  - **The current code would not cause that loss.** v0.36.0's enriched refresh never wrote `tree.json` (v0.36.0 `enriched_refresh.py:L25`, "preserves enriched abstracts"), and 0.37 added carry-forward (`context/build/navigation_refresh.py:L75-L153`). The loss therefore came from a full-build path; the root cause is not isolated because of the squash.
  - **Constraint on the proposed fix.** "Omit default-valued keys" must keep `abstract`/`confidence` readable by the carry-forward logic (`navigation_refresh.py:L133-L146`, `_mechanical_abstract`).
  - status: **open → confirmed (narrowed: the sizes stand; "never enriched" is refuted)**
- over-engineering#3 `council/` files unread after the run — **concur** — evidence:
  - **The only readers are inside the run.** The architect reads `01-dev-draft.md` (`skills/agents/architect.md:L93`). The deep critique reads `10-critiques.md` (`skills/council/40-critique.md:L45,L69`).
  - **There is no reader after the run.** Resume uses only `_council-log.json` (`skills/council/19-resume.md:L9`), which is already gitignored (`context/build/runner.py:L342`). The source-docs catalog only excludes these names (`context/domains/source_docs/refs.py:L107-L109`).
  - status: **open → confirmed**
- over-engineering#4 `coverage.json` YAGNI (`context/build/coverage.py:L35-L84`) — **dispute** — evidence:
  - **The audit missed an agent-facing reader.** The `HOW_TO_USE` template tells agents that `coverage.json` "accounts for indexed files, file-only navigation, unassigned source and excluded paths with reasons" (`context/output/instructions.py:L53`). The shipped `.context/HOW_TO_USE.md:L5` documents ownership, extraction status, exclusions and identity ambiguities.
  - **Trimming would break that contract.** Cutting the file to the 3 keys `cli/status.py:L74-L78` reads breaks a documented retrieval contract.
  - **A cut that is safe.** Compacting `indent=2` (`coverage.py:L84`) is a legitimate smaller cut.
  - status: **open → disputed**
- over-engineering#5 done proposals residue — **no view**. — status: open
- over-engineering#6 `docs.md`/`supporting.md` unread (`context/domains/features/docs.py:L31-L206`) — **dispute** — evidence:
  - **`docs.md` has readers.** It is a documented input to the council `/specify` stage (`skills/council/20-specify.md:L10`), the dev persona (`skills/agents/dev.md:L53`) and the main skill map (`skills/skill.md:L160`).
  - **`supporting.md` has readers.** Drift freshness counts it as a feature doc (`context/drift.py:L49-L59`, `_FEATURE_DOC_NAMES`), and the trivial-filter merge procedure consumes it (`skills/council/18-filter-trivial.md:L197-L215`).
  - **The deletion would break those workflows.** The noise-matching critique (`docs.py:L131-L136`) may still stand on its own.
  - status: **open → disputed**
- over-engineering#7 retired dirs (`cli/migrate.py:L1-L110`) — **concur on `equipment-evals/`; dispute bundling `dummyindex-experiment-notes/` into a tool-side retired-paths list** — the experiment-notes dir is user-authored (`.context/dummyindex-experiment-notes/README.md:L1-L4`), so a dummyindex registry must never delete it. Merge with correctness#8. — status: **open → confirmed (narrowed)**
- over-engineering#8 per-turn hook injection — **concur** — evidence:
  - **The paraphrase has drifted.** The per-turn text (`context/output/bootstrap.py:L78-L91`) has diverged from the static policy (`bootstrap.py:L33-L58`): "cap lists at five" exists only in the turn reminder.
  - **Two independent defects.** The drift is a correctness defect on top of the size issue.
  - status: **open → confirmed**
- over-engineering#9 duplicated static blocks and the `~/.claude/CLAUDE.md` registration (`context/output/agents_md.py:L34-L56`) — **concur** — consistent with correctness#10. This session's own context loaded `AGENTS.md` and `~/.claude/CLAUDE.md` but not `.claude/CLAUDE.md`. — status: **open → confirmed**
- over-engineering#10 `INDEX.md` unread (`context/output/docs.py:L49-L127`) — **dispute, narrowed** — evidence:
  - **No Python reader.** That part is right.
  - **The audit missed a reader.** The generated docs-specialist lists `.context/INDEX.md` in its `grounding_docs` (`context/domains/equip/generate/specialists.py:L156-L160`), and this repo's `.context/equipment.json:L146` records it under `grounded_in`.
  - **Deletion needs coordinated changes.** It requires changing the specialist template and an equip refresh; otherwise the grounding doc of a generated capability disappears.
  - status: **open → disputed**
- over-engineering#11 to #13 (`HOW_TO_USE` size, SessionStart memory/drift output, playbooks) — **no view**. — status: open
