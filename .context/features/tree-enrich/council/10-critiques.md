# Tree abstract enrichment — raw critiques (deep)

## Data integrity

_Line numbers are from the working tree; `map/symbols.json` still holds HEAD ranges. `dummyindex/skills/council/22-parallel-dispatch.md` is catalogued `high`; `52-tree-enrich.md`, `skill.md` and `00-overview.md` are `low`, so they are context only._

- `dummyindex/context/domains/enrich.py:198-218`, `dummyindex/context/domains/council_batch.py:221-222`, `:282-284` — stage 5 (`CouncilStage.TREE`) produces one dev unit per feature, and `dummyindex/skills/council/22-parallel-dispatch.md:12-22` dispatches up to `--cap 8` of them in one message (`dummyindex/context/domains/fleet.py:400-401` also sizes the stage per feature), yet `apply_updates` reads the whole 5.2 MB, 6,445-node `tree.json` (`:207`) and replaces it (`:217`) with no lock or generation check, so a unit whose apply lands between another unit's read and `replace` loses its abstracts after its CLI has already printed `updated N`; every unit's `enrich-plan` also races on the shared `cache/_enrich_plan.json`, and this breaks the high-confidence doc's claim that each feature "writes only to its own `features/<id>/` tree" (`22-parallel-dispatch.md:3-5`) — make TREE one global unit or have the conductor run applies one at a time, and hold an exclusive lockfile from read to `replace` in `apply_updates`/`write_plan`.
- `dummyindex/context/domains/enrich.py:259-273`, `:161-163` — node IDs contain no line numbers (for example `enrich_build_plan`), so they survive edits, and `_apply` sets `INFERRED` and removes `source-stale` on any ID that currently exists, even one the plan never listed, while the plan records only `generated_at` (no tree hash, no per-node `range`/`stub_abstract`); so if `rebuild --changed` flags a node between plan and apply (`dummyindex/context/build/navigation_refresh.py:150-153`), an abstract written against the old source clears the flag, and this is happening in this run: `tree.json` still has `build_plan`@93 and `_count_nodes`@256 against 86 and 247 in the working tree, and because `range` holds only a start line (`dummyindex/context/build/tree.py:232-233`), line 256 now points into the body of `_collect_ids` — store the `tree.json` sha256 and each node's `range`/`stub_abstract` in the plan, and have `enrich-apply --plan` skip and report IDs whose current values differ or that the plan never listed.
- `dummyindex/context/build/navigation_refresh.py:104-117`, `dummyindex/context/domains/enrich.py:109-125` — `tree.json` has 8 node_ids that each appear on two identical nodes (`rebuild_run`, `dispatch_run_apply`, `incremental_is_enriched_index`, `models_from_dict__89f54e67883c2417`, …), both at HEAD (6,659 nodes) and in the working tree (6,445 nodes); `build_plan` lists each of these IDs twice in its batch and `_apply` writes both copies, but `refresh_tree` keeps an annotation only when the ID count and the `(kind, path, title)` count are both 1, so these 16 nodes go back to stubs on every `rebuild --changed` and are planned and paid for again on every run — dedupe `child_ids` in `_build_file`/`_build_symbol` (`dummyindex/context/build/tree.py:200-205`, `:235-240`), and until then have `refresh_tree` match duplicate pairs by `(node_id, range)`.
- `dummyindex/cli/enrich.py:104-106`, `dummyindex/context/domains/enrich.py:264-273` — the payload check accepts `""` and whitespace-only abstracts and `_apply` stores them as `INFERRED`; `build_plan` never selects those nodes again (`:109-113`), and `refresh_tree` carries forward any node that is not `EXTRACTED` as annotated (`dummyindex/context/build/navigation_refresh.py:36-38`, `:133-145`), so one blank value from a subagent leaves the node with an empty abstract until its source file next changes, and an echoed stub (`Function X at path:N.`) is likewise kept as `INFERRED`, so its `:N` is never refreshed again — beside the `str -> str` check, exit 2 on empty or whitespace values and on values that equal the node's current stub.
- `dummyindex/context/domains/enrich.py:179-181`, `:215-217` — both writes call `write_text` on a fixed `<name>.tmp` and then `replace` it, unlike `_replace_bytes` (`dummyindex/context/domains/atomic_io.py:37-67`: unique temp file, 6× `PermissionError` retry, cleanup), so parallel applies share one `tree.json.tmp`, a Windows reader holding `tree.json` makes `replace` raise (a traceback and exit 1, the same code as unknown IDs) and leaves a 5.2 MB `.context/tree.json.tmp` that `git check-ignore` confirms is not ignored, and text-mode `write_text` on Windows turns all 108,341 LF line endings into CRLF, which the next `refresh_tree` (`write_text_atomic`, `dummyindex/context/build/navigation_refresh.py:154-158`) turns back, changing every line wherever `core.autocrlf` is not `true` — use `write_text_atomic` for both writes.
- `dummyindex/context/domains/enrich.py:264-267`, `:109-113` — (prior bullet, re-verified) when an `INFERRED` node receives the abstract it already has, it skips the update block, so its `source-stale` label survives and planning selects it again on every run, and an empty `updated` list does not prove that stale labels were cleared — when a known ID carries `source-stale`, drop the label even if text and confidence match, and count the node as updated.
- `dummyindex/cli/enrich.py:40`, `dummyindex/context/build/upgrade.py:433-445`, `:115-121` — `run_plan` throws away the `LayoutMigration` result, so `enrich-plan` deletes or backs up committed retired paths and drops `errors` such as "backup failed, left in place" without printing anything; this working tree shows all 9 committed `equipment-evals/*.suite.json` as `D` with no `_doc_backups/retired/` folder (all 9 pass `_is_starter_suite` at HEAD, so nothing was lost here, but a user-edited suite would move into the gitignored `_doc_backups/` without notice), and the managed `.gitignore` merge is a plain read followed by `write_text`, which is unsafe with the parallel units in the first bullet — print `format_migration_report(migration)` (`dummyindex/context/build/upgrade.py:618`) as the build callers do, exit non-zero when `errors` is non-empty, and use `write_text_atomic` for the merge.
- `dummyindex/context/domains/enrich.py:131-136`, `:236-244`, `:207`, `:215-217` — unbounded reads: `build_plan` walks the entire tree again for each in-file symbol (5,822 symbols × 6,445 nodes; measured here at 2.2 s, a 3.3 MB plan and 554 batches), and applying one batch at a time (docstring `:3-5`) parses and rewrites the full 5.2 MB tree for each batch, about 2.9 GB written per deep run and one more lost-update window from the first bullet each time — build a `path -> file node_id` dict once in `build_plan`, and let `enrich-apply` take several batch files in one call.

### Resolved since last review

- None. Both prior bullets were re-verified at their shifted lines: prior #1 (no lock or generation check, `enrich.py:214-226`) is split into the first two bullets at `:198-218`, and prior #2 (an identical abstract keeps `source-stale`, `:271-282`) is the sixth bullet at `:264-267`.

## Security

- `dummyindex/context/domains/enrich.py:176-181`, `:215-217` — **High.** `write_plan` and `apply_updates` write a fixed sibling (`_enrich_plan.json.tmp`, `tree.json.tmp`) with `Path.write_text`. That call follows a pre-existing link, and `mkdir(parents=True, exist_ok=True)` (`:178`) accepts a linked `cache/`. `.context/` is committed by design, so a cloned repo can plant either name as a link (POSIX checkouts create the link; on Windows, the default `core.symlinks=false` turns it into a plain file). Running `enrich-plan` or `enrich-apply` then writes JSON containing repo-controlled strings (`title`, `path`, abstracts) to an arbitrary file outside `.context/`. The `.gitignore`/`.gitattributes` merge that `enrich-plan` now runs also writes through links, non-atomically (`dummyindex/context/build/upgrade.py:85-99`). — Existing mitigation: none in these writers. `write_text_atomic` (`dummyindex/context/domains/atomic_io.py:70-79`) uses a unique `NamedTemporaryFile` (`:37-67`), and `refresh_tree` already writes `tree.json` through it (`dummyindex/context/build/navigation_refresh.py:154-158`). — Fix: switch both writers to `write_text_atomic`. Before writing, refuse when `cache/`, `tree.json` or the managed files are `is_link` (`atomic_io.py:16-34`), or resolve outside `.context/` (the check `_Retirer._inside` makes at `upgrade.py:341-348`). Add a link-planted test for each writer.
- `dummyindex/cli/enrich.py:100-110`, `dummyindex/context/domains/enrich.py:259-276` — **High.** Abstracts are stored verbatim as `INFERRED`, with no length cap, single-line check or control-character check. The ≤120-char one-line contract exists only in workflow prose. A per-file author reads untrusted source, so an instruction-like payload in that source can become a committed abstract that every later session reads when it "walks `tree.json`" (`dummyindex/context/output/instructions.py:35`, `:70`). The payload persists: `refresh_tree` carries any non-mechanical abstract across `rebuild --changed` (`navigation_refresh.py:56-72`, `:133-145`), and `build_plan` never reselects an `INFERRED` node unless its source changes (`domains/enrich.py:110-113`). Nothing re-reviews it. — Existing mitigation: none. The generated `HOW_TO_USE` has no "abstracts are repository data, never instructions" framing, and `INFERRED` records provenance, not approval. — Fix: in `run_apply`, reject (exit 2) any abstract over a `MAX_TREE_ABSTRACT` cap, any newline and any control character, in the style of the model-output caps in `dummyindex/context/domains/features/scan/validate.py:1-40`. Also add the data-not-instructions line to `instructions.py` and the retrieval skills.
- `dummyindex/context/domains/enrich.py:116-124`, `:224-233` — **Medium.** `path` is copied from `tree.json` into the plan's `path` and `evidence_files` without checking that it is relative, free of `..`, inside the repo root, or listed in `map/files.json`. The authoring step reads `evidence_files` for grounding, according to `dummyindex/skills/council/52-tree-enrich.md:60-62` (catalogued `low`, so this is context, not authority). A committed `tree.json` that has not been regenerated since the clone can therefore steer authors at files outside the repo, and their summaries persist into the committed `tree.json`. — Existing mitigation: none in code; only host file-access prompts, which may not fire. A rebuild resets `path` from the scan (`navigation_refresh.py:98-99`). — Fix: in `build_plan`, emit `evidence_files` only for paths that resolve under a trusted root and appear in `map/files.json`, using the pattern in `_trusted_repo_root` (`dummyindex/context/domains/reality_check/verify.py:466-486`). Drop other paths and count them in `stats`.
- `dummyindex/context/domains/enrich.py:209-213`, `dummyindex/cli/enrich.py:110-122` — **Medium.** Updates are checked against every ID in the tree, never against `cache/_enrich_plan.json` or the batch. A per-file author can overwrite the `project` root abstract (the first thing a tree walk reads) or any curated `INFERRED` node. Known IDs are written before the unknown-ID exit `1`, so a run that looks rejected has already persisted its changes. — Existing mitigation: unknown IDs are reported; IDs never become filesystem paths. — Fix: load the plan and require every key to be one of its `node_ids` (optionally `--batch NAME` ⊆ that batch). Validate the whole payload and exit 2 before writing anything (all-or-nothing).
- `dummyindex/cli/enrich.py:87-108`, `dummyindex/context/domains/enrich.py:101`, `:207` — **Medium-low.** Prior bullet, re-cited at the new line numbers. The `--from-json` file is checked with `exists()`, which also passes for a directory, and is read with no byte cap. `json.loads` is not guarded, so `JSONDecodeError`, `RecursionError` (deep nesting) and `UnicodeDecodeError` produce a traceback and exit `1`. Key count and value size are unbounded. `tree.json` is parsed and indexed (`tree["root"]`, `node["kind"]`, `node["node_id"]`) without shape validation, so a corrupt committed tree crashes both verbs. — Existing mitigation: the `str -> str` shape check (`cli/enrich.py:101-108`). — Fix: use `is_file()`, cap `stat().st_size` before reading, and catch `(OSError, UnicodeDecodeError, ValueError, RecursionError)` to exit 2, as `_is_starter_suite` does (`upgrade.py:263-267`). Cap the key count at the plan's node count, and check the minimal tree shape before walking it.
- `dummyindex/cli/enrich.py:37` — **Medium-low.** The `LayoutMigration` returned by `migrate_context_layout` (`upgrade.py:501-552`) is discarded. A nominal "plan" verb therefore silently deletes byte-exact starter suites and moves `graph/` and edited `equipment-evals/` files into the gitignored `_doc_backups/`, where they disappear from the next commit without notice. It also swallows the containment refusals (`upgrade.py:380`, `:401`), the only signal that a planted link was found. — Existing mitigation: `_Retirer` never follows links, backs up before deleting unproven files and refuses linked backup parents (`upgrade.py:313-459`); the migration runs only after `build_plan` succeeds (`cli/enrich.py:28-37`). — Fix: print `format_migration_report(migration)` (`upgrade.py:577-615`) to stderr, as `dummyindex/cli/rebuild.py:142-144` already does, and warn when `errors` is non-empty.
- `dummyindex/cli/enrich.py:115-121` — **Low.** Unknown IDs, which are model-authored keys, are printed raw and without limit. A `\u001b` escape in the JSON decodes to a real control character, which reaches the operator's terminal, and the conducting session reads that stderr back, making it a second injection channel. A payload of 10⁵ bogus keys floods that context. — Existing mitigation: none. — Fix: print `ascii(nid)` and cap the list with an "… and N more" line, reusing `_capped_lines` (`upgrade.py:562-574`).
- `dummyindex/cli/enrich.py:59-73`, `:87-89` — **Low.** `--from-json` accepts any path with no ownership or containment check. The feature's own example hand-off is `/tmp/abstracts.json`: a predictable name in a world-writable directory. On a shared POSIX host, another local user can create or swap that file between the host's write and `enrich-apply`, and their abstracts are persisted. — Existing mitigation: none. — Fix: have the workflow write the payload to a unique name under `.context/cache/`, and have `run_apply` warn when the file sits outside the project root or is not owned by the current user.

### Resolved since last review

- None. Both prior Security bullets still hold and are folded into bullets 2 and 5 at the new line numbers. The comment edits moved the cited lines (for example, `apply_updates` is now `:198`). `map/symbols.json` still has the old lines (`write_plan` at 185 vs 176 live, `apply_updates` at 207 vs 198, `format_migration_report` at 618 vs 577), so the code is authoritative here. `52-tree-enrich.md` and `skill.md` are catalogued `low` and are used only as context.

## Product surface

`dummyindex/skills/council/52-tree-enrich.md` and `dummyindex/skills/skill.md` are catalog
`low` (`.context/source-docs/INDEX.json`); every citation of them below is the shipped
instruction surface, never authority on behavior — behavior claims are checked in code.

- **Running council stage 5 for several features** — `_units_for_feature` emits one
  `dev` unit per feature at `CouncilStage.TREE`, and the loop dispatches every unit
  in one message with the `agents/dev.md` persona inlined
  (`dummyindex/context/domains/council_batch.py:213-222`,
  `dummyindex/skills/council/22-parallel-dispatch.md:10-24`, catalog `high`);
  `dummyindex/skills/agents/dev.md` has no tree-enrich, `enrich-plan` or
  `enrich-apply` instruction. `enrich-plan`/`enrich-apply` take no feature
  (`dummyindex/cli/enrich.py:12-51`, `dummyindex/cli/enrich.py:54-123`), so nothing
  assigns a unit a feature-scoped node subset. The procedure instead describes one
  architect (standard) or one dev per `file_subtree` (deep), with the conductor
  merging and applying (`52-tree-enrich.md:39-76`), and has no per-feature stage-5
  `council-log` step — no mapping between the two dispatch shapes exists. If units do
  run the verbs, each apply replaces the whole `tree.json` through a fixed
  `tree.json.tmp` (`dummyindex/context/domains/enrich.py:205-217`). At HEAD no
  `_council-log.json` holds a stage-5 entry and all 6445 nodes are `EXTRACTED`.
- **Choosing light mode** — `active_stages` appends `TREE` in every mode unless
  `--no-tree-enrich` (`dummyindex/context/domains/council_batch.py:62-77`,
  `dummyindex/cli/council_batch.py:105`), and `is_stage_complete` is `False` for a
  stage with no log entry (`dummyindex/context/domains/council.py:163-180`) — a
  conductor following "light skips" (`dummyindex/skills/skill.md:334`,
  `dummyindex/skills/council/52-tree-enrich.md:41`) without logging `skipped` per
  feature keeps receiving stage-5 units and `batch.complete` stays false. Both `low`
  docs also state the opposite (`dummyindex/skills/skill.md:339-340`,
  `dummyindex/skills/council/52-tree-enrich.md:11-12`); code and
  `22-parallel-dispatch.md:28-30` (`high`) win. Neither doc names the `skipped` status.
- **Reading exit 1 from `enrich-apply`** — exit `1` means either "known IDs written,
  `tree.json` replaced, some IDs unknown" (`dummyindex/context/domains/enrich.py:209-218`,
  `dummyindex/cli/enrich.py:110-122`) or "nothing written, `JSONDecodeError`
  traceback" (`dummyindex/cli/enrich.py:100`). The traceback path covers truncated JSON
  and a UTF-8 BOM (read as `encoding="utf-8"`; probe: `Unexpected UTF-8 BOM (decode
  using utf-8-sig)`) when the mapping is written with Windows PowerShell 5.1 `Out-File`
  (BOM by default) rather than the `Write` the procedure names (`52-tree-enrich.md:67`); a
  directory passes the `exists()` check (`:87`) and crashes in `read_text` — only the
  shape error has a message and exit `2` (`:101-108`). The unknown-ID warning cannot
  tell a typo from an ID renamed by a rebuild: apply never reads the plan or its
  `generated_at` (`dummyindex/context/domains/enrich.py:161-163`), only current-tree
  membership (`:209-211`).
- **Authoring the skeleton a retrieval walk reads first** — the `structure` batch
  holds only project/dir nodes (`dummyindex/context/domains/enrich.py:126-130`; probe:
  70 nodes) although `dummyindex/skills/skill.md:334-335` says it includes files; each
  of the 553 file heads is `node_ids[0]` of its own `file_subtree` batch
  (`dummyindex/context/domains/enrich.py:128-130`, `:147-154`). All 70
  project/dir nodes carry `evidence_files: []` because `_walk` yields no file for them
  (`dummyindex/context/domains/enrich.py:123`, `:224-233`), yet authors are told to read
  `evidence_files` and keep the stub wording when evidence is thin
  (`dummyindex/skills/council/52-tree-enrich.md:60-64`); that stub is
  `Directory at <path>/ (N immediate children).` (`dummyindex/context/build/tree.py:177-180`).
  Symbol `range` is `[start, start]` (`dummyindex/context/build/tree.py:232-233`;
  5822/5822), a start line, not a span.
- **Reconciling after a one-line edit** — `refresh_tree` adds `source-stale` to an
  annotated node when any changed path is at or under its `path`, and the project
  node (`path "."`) matches every change (`dummyindex/context/build/navigation_refresh.py:125-132`,
  `:150-153`); symbols share their file's `path`, so one edit re-queues the file, every
  annotated symbol in it, each ancestor dir and the project. For a stale `INFERRED`
  node, `stub_abstract` carries the prior prose (`dummyindex/context/domains/enrich.py:122`);
  "keep the stub's wording" (`dummyindex/skills/council/52-tree-enrich.md:63-64`) then
  yields an identical abstract, which `_apply` skips without clearing `source-stale`
  (`dummyindex/context/domains/enrich.py:264-273`), so the node reports no update and
  every later plan reselects it (`:110-113`). A zero update count does not mean stale
  labels cleared.
- **Deep mode on this repo** — read-only `build_plan` over the working-tree
  `tree.json`: 6445 stub nodes, 554 batches (1 `structure` + 553 `file_subtree`, max
  130 nodes), 5822 symbols. Per `dummyindex/skills/council/52-tree-enrich.md:43`,
  `:72-73` that is 553 dev dispatches and 553 full read-serialize-replace cycles of
  `tree.json`, which also run for `{}` or an identical mapping
  (`dummyindex/context/domains/enrich.py:205-217`) — the doc's "no-op" is no-op in
  content only. The CLI prints `batches: 554` without splitting batch kinds
  (`dummyindex/cli/enrich.py:46-50`). `estimate_run` counts the tree stage as one unit
  per feature in every mode, counts symbol stubs in standard/light, and hardcodes
  `tree_enrich=True` (`dummyindex/context/domains/fleet.py:414-435`), so it understates
  deep fan-out and estimates stage 5 for `--no-tree-enrich` runs. Each in-file stub
  triggers a root-down DFS for its file node (`dummyindex/context/domains/enrich.py:131-136`,
  `:236-244`; probe: 2.27 s), repeated by `estimate_run` (`fleet.py:424`).
- **Duplicate node IDs and file-batch names** — the working-tree `tree.json` holds 8
  IDs twice under the same file parent (e.g. `rebuild_run`); children are built once
  per hierarchy edge without dedupe (`dummyindex/context/build/tree.py:82-87`, `:200-205`).
  `stubs: 6445` therefore covers 6437 distinct IDs (`dummyindex/context/domains/enrich.py:158`),
  and `_apply` appends per matching node: `{"rebuild_run": …}` returns
  `['rebuild_run', 'rebuild_run']` and prints `updated 2 abstract(s)`
  (`dummyindex/context/domains/enrich.py:259-276`, `dummyindex/cli/enrich.py:111-114`).
  Batch `name` is the file basename and a batch carries no path
  (`dummyindex/context/domains/enrich.py:37-43`, `:128-130`, `:147-154`): 51 names repeat
  (`__init__.py` × 64), so keying deep-mode progress or the per-file `dev-pick`
  (`dummyindex/skills/council/52-tree-enrich.md:56-58`) on batch name collides.
- **Running `enrich-plan` to check remaining work** — every call first runs
  `migrate_context_layout` (`dummyindex/cli/enrich.py:37`): merges managed
  `.gitignore`/`.gitattributes`, deletes the legacy root `_enrich_plan.json`, retires
  `equipment-evals/` and `graph/` (unedited starter suites deleted, others backed up
  under `_doc_backups/retired/<version>/`) (`dummyindex/context/build/upgrade.py:300-307`,
  `:501-552`). The returned `LayoutMigration` is discarded, though
  `format_migration_report` (`dummyindex/context/build/upgrade.py:577-615`) exists and
  `rebuild` prints it (`dummyindex/cli/rebuild.py:138-145`); help says only "Emit
  .context/cache/_enrich_plan.json (work-list)" (`dummyindex/cli/help.py:108`). Removals,
  backups and step errors go unreported, and each replan overwrites the plan file.

### Resolved since last review

- None. All five prior bullets re-verified at `0634bfd` and kept: unknown-ID partial
  success and malformed JSON merged into bullet 3, light mode into bullet 2,
  whole-tree rewrite per apply into bullet 6, identical-prose stale no-op into bullet 5.
- Audit trail (doc vs code; code wins): `plan.md`/`spec.md` line citations drifted with
  the comment-shortening pass — `dummyindex/cli/enrich.py` `run_plan` `:12-51` (cited
  `:12-54`), `run_apply` `:54-123` (`:57-126`), `json.loads` `:100` (`:103`);
  `dummyindex/context/domains/enrich.py` `build_plan` `:86-173` (`:93-182`),
  `apply_updates` `:198-218` (`:207-227`), `_apply` `:259-276` (`:268-285`);
  `migrate_context_layout` `dummyindex/context/build/upgrade.py:501-552` (`:542-593`);
  `active_stages` `dummyindex/context/domains/council_batch.py:62-77` (`:65-80`).
  `52-tree-enrich.md` and `skill.md` are catalog `low` (`.context/source-docs/INDEX.json`)
  and contradict themselves on light mode; cited above only as the instruction surface.

## Cross-review

### Confirmed (6/6 HIGHs, each re-read at its cited range)

- **Concurrent stage-5 applies lose abstracts** — `dummyindex/context/domains/enrich.py:198-218` reads, mutates and replaces `tree.json` through a fixed `tree.json.tmp` with no lock; `dummyindex/context/domains/council_batch.py:213-222` emits one stage-5 `dev` unit per feature, and `dummyindex/skills/council/22-parallel-dispatch.md:12-22` dispatches up to `--cap 8` in one message. Latent today: no `_council-log.json` has a stage-5 entry, and all 6,445 nodes are `EXTRACTED`.
- **Apply wipes post-plan `source-stale`** — `enrich.py:259-276` clears the label on any current ID, whether or not the plan listed it, and the plan stores only `generated_at` (`:161-163`).
- **8 duplicate IDs lose abstracts every rebuild** — 8 IDs (`dispatch_run_apply`, `rebuild_run`, `incremental_is_enriched_index`, `models_from_dict__89f54e67883c2417`, `render_render_markdown`, `models_from_dict__075ec295a335459b`, `evolve_experiments_run_experiment`, `test_skills_doc_hygiene_plan_skill`) each appear on 2 nodes with the same location, so neither carry-over branch at `dummyindex/context/build/navigation_refresh.py:104-117` fires. The root cause is that `_assemble` appends children per hierarchy edge without deduping them (`dummyindex/context/build/tree.py:82-87`).
- **Temp writes follow planted links** — `enrich.py:176-181`, `:215-217` call `Path.write_text` on fixed names. `.context/` is committed, and `git check-ignore` does not match `.context/tree.json.tmp`. `cache/` is ignored (`.context/.gitignore:3`), but neither rule stops a force-added commit. On Windows, the default `core.symlinks=false` makes the vector a plain file.
- **Persisted abstracts can be injected** — `dummyindex/cli/enrich.py:100-108` checks only `str -> str`. `_apply` stores the value verbatim (`enrich.py:268`), `refresh_tree` carries it across rebuilds (`navigation_refresh.py:133-145`), `build_plan` never reselects it (`enrich.py:110-113`), and HOW_TO_USE points sessions at `tree.json` (`dummyindex/context/output/instructions.py:35`, `:70`).
- **No doc tells a stage-5 dev unit what to do** — `dummyindex/skills/agents/` contains no `enrich`/tree-enrich instruction (grep), `enrich-plan`/`enrich-apply` take no feature (`dummyindex/cli/enrich.py:12-51`, `:54-123`), and `52-tree-enrich.md:49-76` describes a global conductor phase with no `council-log` step.

### Refuted / softened

- Nothing refuted outright.
- Database #2's claim that the bug is "happening in this run" is **softened**: the live evidence is only range drift (`tree.json` has `enrich_build_plan`@93 and `enrich_count_nodes`@256, while the live code has them at 86 and 247). No node carries `source-stale`, because `refresh_tree` adds the label only `if changed and annotated` (`navigation_refresh.py:150`) and nothing is annotated.
- Database #7 cites `format_migration_report` at `upgrade.py:618`. That line comes from the stale `map/symbols.json`; the function is at `:577` in the live code.

### Merged

- **LayoutMigration discarded** — database #7, security #6 and product #8 → Data #5. Security #6's swallowed link refusals are part of it.
- **Identical prose keeps `source-stale`** — database #6, product #5 and the prior concerns, plus product #5's stale cascade from a single edit → Data #4.
- **Duplicate IDs** — database #3 and product #7 → Data #3. The batch-name collision stays separate as Product #6.
- **Fixed `.tmp` / CRLF / stray file** — database #5 → Data #6. Its link-follow angle → Security #1; the two bullets share one fix.
- **Payload content checks** — database #4 (blank, echoed stub) and security #2 (length cap, newline, control characters) → Security #2.
- **Parse and shape robustness** — security #5 and product #3 (BOM, truncation, directory input) → Security #4, with the exit-code semantics kept in Product #3.
- **Unplanned IDs** — database #2 (skip unlisted IDs) and security #4 (keys ⊆ plan) → Data #2 and Security #3. Security #7 (raw unknown-ID printing) is folded into Security #3.
- **Whole-tree rewrite per apply and unbounded `build_plan` walk** — database #8 and product #6 → Product #5.

### Flagged (conflicts between fixes)

- **Data #1 and Product #1 are coupled.** Fixing the doc gap by telling per-feature units to run the verbs *activates* the race. Order the fixes this way: units return JSON only, the conductor applies serially, then the lock is added.
- **`write_text_atomic` does not fix the lost update.** It removes the shared tmp, the link-follow on the tmp, the CRLF rewrite and the stray file. The read→`replace` window still needs a lock. It also writes into a linked `cache/` (`NamedTemporaryFile(dir=path.parent)`, `dummyindex/context/domains/atomic_io.py:46-52`), so the parent `is_link` check is still required.
- **A whole-tree sha256 check breaks per-batch apply.** A generation check on the whole tree fails every apply after the first in deep mode (`52-tree-enrich.md:72-73`). Check per node (`range`, `stub_abstract`) instead.
- **Rejecting stub echoes conflicts with two other behaviours.** It conflicts with the doc's "keep the stub's wording" (`52-tree-enrich.md:63-64`). It also conflicts with re-confirming identical prose on stale nodes (Data #4), because a stale `INFERRED` node's `stub_abstract` is its prior prose. Limit the rejection to `_mechanical_abstract` matches on `EXTRACTED` nodes, and tell authors to omit nodes whose evidence is thin.
- **"Skip and report" (database) conflicts with "all-or-nothing exit 2" (security).** Reject the whole payload for invalid or unplanned keys, and use skip-and-report only for plan-listed IDs that drifted.
- **Recorded decisions reversed.** Keys ⊆ plan reverses plan.md's "unknown IDs reported, not rejected", and Data #4 reverses "apply is idempotent per node". Record both reversals in `plan.md`. Keys ⊆ plan also needs a single plan per run, which parallel `enrich-plan` calls currently overwrite (Data #1).
