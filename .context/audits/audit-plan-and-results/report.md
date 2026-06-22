# Audit report — the `outstanding-audit-fixes` plan & the audit results it derives from

**Subject:** `.context/proposals/outstanding-audit-fixes/{plan,spec,checklist}.md` (unimplemented — no checklist box ticked) + the audit `.context/audits/make-sure-there-is-no-docs-drift-context-vs-code-no-dead-cod/report.md`.
**Panel:** correctness, security, architecture, data-integrity, tests.
**Mode:** deep — Round 0 (independent) → Round 1 (rebuttal, converged via concessions) → adversarial refutation pass (2 targeted skeptics). **Model:** opus-4.7.
**Grounding:** every claim verified against the **current post-`c574d41`/`d7d2e74` source** — the code wins.

## Executive summary

The plan is **structurally strong and mostly accurate** — correct wave/file disjointness, clean `paths.py` layering, honest best-effort scoping, and it correctly identifies genuinely-outstanding work (hyperedge sort, the clustering GATE, P2, the four trust-boundary confinements, the atomic confidence mirror) without re-proposing what `c574d41` already fixed. But it ships **6 confirmed HIGH defects** that would cause an as-written implementation to fail, plus a GATE decision input that the plan's own gate-condition got wrong.

- **Confirmed:** 19 findings — **6 high, 9 medium, 4 low/info** — plus ~14 recorded confirmations where the plan is right.
- **Headline risks:** (1) the **cache trust-channel model is inverted** and its obvious remedy silently breaks a *documented* user opt-out; (2) the **read-time symlink guard has no anchor** in its in-scope file; (3) **Task 12's scope is incomplete** (can't thread bytes without two unlisted files); (4) **three acceptance tests are false-passes or non-constructible as written** (the `/etc/passwd:1` proof string is grammar-rejected; the P2 read-counter can't discriminate at the method level; the GATE strategy-(b) Leiden-spy is vacuous with graspologic absent); (5) **GATE strategy (c) is breaking** — feature-grouping re-reads the committed `community`.
- **Unresolved disputes:** none on substance. Two findings (Task 9, Task 12) carry a **one-notch severity dissent** (architecture HIGH vs correctness MEDIUM), noted inline.
- **Refutation pass:** overturned the round-1 *remedy* for the cache finding (made it sharper) and **failed to refute** the GATE-(c)-breaking finding (hardened it). All 6 HIGHs survived two skeptics where applicable.
- **On the audit results:** the report's findings were accurate when written and `c574d41` correctly resolved most; a couple of its citations are now stale (informational — it's read-only history), and `3d7d539`'s "C2/C3 resolved" commit message **overstates C2** (single-backend only).

---

## Confirmed findings (ranked by severity)

### HIGH — fix before implementing

- **F1 · Task 3a — the cache "trust-channel split" rests on an inverted model, and the obvious remedy silently breaks a documented user opt-out.** · `dummyindex/context/build/common.py:130-141`, `dummyindex/pipeline/io/cache.py:47-57`
  The plan (plan.md:15, spec.md:30) says "confine only the `DUMMYINDEX_CACHE_DIR` env-var read; `cache_dir_override` keeps working via the trusted `cache_root` channel." **False in both directions:** `cache_dir_override` *sets the env var* (`common.py:134`), and `cache_dir()` reads the env var **with precedence over** the threaded `root` (`cache.py:51-55` returns in the `if override:` branch before `root` is consulted) — so confining the env var is exactly what blocks the override, and `cache_root` is discarded whenever the env var is set. Both acceptance bullets (spec.md:48) rest on this non-existent mechanism. **Refutation pass result:** the round-1 fallback remedy ("just confine inside `cache_dir()`, silently fall back, never raise") is *also* wrong — `DUMMYINDEX_CACHE_DIR` is a **documented user-facing opt-out** (`cache.py:47-49` "put the cache **anywhere**"; `CHANGELOG.md:1095-1096`,`:1069` "Set `DUMMYINDEX_CACHE_DIR` to opt out … still wins over the default"), so silent confinement quietly disables a published workflow. Data-integrity angle: the cache key is source-hash-only with no repo identity (`cache.py:60-77`), so a mis-confined/shared dir risks **cross-repo cache bleed**.
  *Fix:* rework the trust model — re-route `cache_dir_override` off the raw env var onto a trusted in-process channel and confine only the **ambient** `DUMMYINDEX_CACHE_DIR`, **or** declare an intentional breaking change and update the docstring + CHANGELOG. Honor `test_cache_env_var_is_restored`'s "silently fall back, never raise" constraint. Re-derive both acceptance bullets. *(The plan's stated justification — "leave `cache_root` unconfined so out-of-repo override works" — is moot for the two internal callers, both in-repo: `runner.py:109`, `enriched_refresh.py:100`; the real constraint is the user-facing override.)*

- **F2 · Task 4a — the read-time symlink-containment guard has no anchor in its only in-scope file.** · `dummyindex/pipeline/extract/__init__.py` (cited `:268-293`)
  Task 4a says "containment-check leaf targets … **at read time** (just before `read_bytes`/`_read_text_safely`)" but `extract/__init__.py` contains **zero** byte-read sites (grep-clean); `:268-293` is the `collect_files` `os.walk` *path-discovery* loop. The real reads are `generic.py:42` (extractor) and `cache.py:38` (cache-hash, via `load_cached` at `extract/__init__.py:163`) — and `generic.py` is **Task 12's** file in a later wave. So the guard as scoped either forces an out-of-scope edit or collides with Task 12.
  *Fix (panel-converged):* place the containment filter at **`collect_files` leaf emission** (`extract/__init__.py:289-293`) — the single chokepoint covering *both* read sinks, staying in Task 4's only file — and **drop the "at read time / TOCTOU-robust" wording** (this is walk-time; a post-enumeration symlink swap is a residual the plan must acknowledge), or explicitly fold a read-sink gate into Task 12's `generic.py`.

- **F3 · Task 12 — scope is incomplete; it cannot thread the extractor's bytes within its declared file list.** · `.context/proposals/outstanding-audit-fixes/plan.md:35,46`
  To "thread the bytes the extractor already read," `extract()` (which returns only `{nodes,edges}`, `extract/__init__.py:90-95`/`244-249`) and `structure.py:120,52` must be edited to carry bytes through — **neither is in Task 12's list** (`references.py`+`generic.py`+`incremental.py`). The wave rationale "Task 12 shares the `extract/__init__.py` read seam" is also factually wrong (`references.py` doesn't import `pipeline.extract`). The wave-3-after-wave-2 gate still makes it **physically safe** (no parallel collision) — so this is "can't meet its own acceptance," not "corrupts parallel work." *(Severity: architecture HIGH on implementability; correctness MEDIUM since the wave gate covers safety. Rendered HIGH, scoped to implementability.)*
  *Fix:* add `pipeline/extract/__init__.py` + `pipeline/build/structure.py` to Task 12's scope; correct the rationale to "edits `extract/__init__.py` (same file as Task 4) → serialize after Wave 2."

- **F4 · Task 7 acceptance — two headline proof strings are grammar-rejected, so the named test is a FALSE PASS.** · `.context/.../spec.md:65`, `checklist.md:29` vs `dummyindex/context/domains/reality_check/extract.py:32-34`
  `_FILE_LINE_RE` requires a `.ext` (1–6 alnum) before `:line`. Empirically (3 auditors): `` `/etc/passwd:1` `` and `` `../../../../etc/passwd:1` `` **never match** → never become claims → never reach `_resolve_cited_path` or the `Path.open` sink (`verify.py:144`). A test asserting "`Path.open` never called for `/etc/passwd:1`" **passes against unpatched code** — proving nothing. The real reachable surface is **extension-bearing** escapes (`` `../../secrets.env:1` ``, `` `/tmp/x.json:1` ``, `` `/etc/cron.d/evil.sh:1` ``).
  *Fix:* re-spec the acceptance proof strings to extension-bearing escapes; keep one extensionless control explicitly labelled "grammar-rejected, not confinement-rejected." *(The underlying vuln — F-confirm Task 7a/b/d — is real and the fix is sound; this is a test-vacuity defect. Calibration: the read is a line-**count** oracle, low absolute severity for a local tool — but the false-pass test is a genuine plan defect.)*

- **F5 · Task 12 acceptance — the P2 read-counter spy is not constructible as named.** · `.context/.../spec.md:77`
  The spec names three distinct reads — "`Path.read_bytes`, `Path.read_text`, the hash reader" — but `generic.py:42` (extractor) and `cache.py:38` (hash reader) are the **same method** `Path.read_bytes`, and the excluded `--changed` hash (`incremental.py:341`→`cache.py:38`) is *also* `Path.read_bytes`. A method-level spy cannot discriminate them or "exclude the `--changed` hash."
  *Fix:* re-word to a **path-keyed** counter (`defaultdict[Path,int]`, assert `counts[f] <= 2` per source path), or have Task 12 introduce one named `read_source_bytes(path)` seam every consumer calls.

- **F6 · Task 6 GATE strategy (b) acceptance — "spy asserts Leiden never called" is vacuous in the test env.** · `.context/.../spec.md:62` vs `dummyindex/analysis/cluster.py:35`
  `graspologic` is **absent** in the venv (`find_spec` → None) and Leiden is imported inside a local `try/except ImportError`; with the backend absent the import already raises and falls to Louvain, so "Leiden never called" passes **for the wrong reason**, proving nothing about the committed path.
  *Fix:* if (b) is chosen, pin graspologic-present in CI + monkeypatch `leiden` and assert non-invocation **under a present backend**; otherwise prefer strategy (a), whose fail-fast half is env-robust.

### HIGH — GATE decision input

- **F7 · Task 6 GATE strategy (c) "exclude `community`" is a BREAKING change, not a pure omission.** · `dummyindex/context/build/runner.py:182-187`, `dummyindex/export/graph.py:29-31`, `dummyindex/context/domains/features/builder.py:76` — **survived adversarial refutation**
  `runner.py:182-187` **re-reads the just-written `symbol-graph.json` from disk** (`json.loads(...read_text())`, comment "Re-read so feature scaffolding can use the same JSON the agent sees") and feeds it to `scaffold_features` (`:197-204`) → `builder.py:76` groups nodes by `community`. `community` is written **only** into the serialized node-link data (`export/graph.py:29-31`), never onto the in-memory graph `G`, and `build_graph` returns no in-memory dict — so the re-read is **structurally forced**. Strip `community` from the committed file → all 4212 nodes collapse to one `community-unassigned` bucket, **same build**. The spec's own gate condition for (c) ("confirm no consumer reads node `community`", spec.md:83) is therefore **false**.
  *Fix:* the GATE decision record must note (c) requires an unscoped re-route of `runner.py`/`builder.py` to consume an in-memory partition; **strategies (a)/(b) keep the field and are safe** for this consumer. *(Also: `_split_community`'s recursive second partition, `cluster.py:113-128`, compounds cross-backend divergence — the (a)/(b) test should exercise a graph large enough to hit the split.)*

### MEDIUM

- **F8 · Task 9 — re-proposes a change two committed in-code NOTEs explicitly decided against, without rebutting them.** · `dummyindex/context/domains/audit/log.py:169-176`, `dummyindex/context/domains/council.py:337-344`
  `c574d41` added NOTE blocks to both `latest_status` bodies stating they are *"deliberately **not** extracted into a shared helper"* (cross-domain dependency; the council copy *"load-bearing for resumption; keep its semantics exact"*). Task 9 extracts them into a new `context/domains/log_scan.py` and **silently reverses** this. Architecture **ruled the design is sound** — `context/domains/atomic_io.py` is a sanctioned shared-domain-helper precedent (imported across ≥9 domains), `folder-organization.md:69-73` *prescribes* such cross-cutting peers, and a no-domain-object `last_matching(entries, predicate)` doesn't reach into another domain's internals; the dedup is verified test-safe (incompatible wrapper signatures correctly factored; resumption tests call the wrappers). So the **only** defect is procedural.
  *Fix:* the plan must **quote-and-rebut** the two NOTEs (and delete them as part of Task 9), not silently reverse them. *(Severity: correctness/tests MEDIUM — safe change, documentation ask; **architecture dissents HIGH** on "the code wins — an unrebutted reversal of an explicit in-code decision.")*

- **F9 · Task 8 — partly stale: the trailing `--top-k`/`--budget` guard already shipped in `c574d41`.** · `dummyindex/cli/query.py:60-68`
  `c574d41` already added the trailing value-flag guard (exits 2). Only the **unknown-`--flag`** rejection (`:69-71` folds it into the search string), the `usage_error` routing of the existing exit-2 sites, and the USAGE exit-1 doc are net-new; spec.md:74 + checklist.md:33 wrongly imply both halves are broken.
  *Fix:* re-scope Task 8 to unknown-flag rejection + `usage_error` refactor + USAGE doc (+ a regression test for the already-fixed trailing case).

- **F10 · Task 11 — not constructible from the existing return value.** · `dummyindex/context/domains/reality_check/confidence.py:26,61,64,94`, `dummyindex/cli/reality_check.py:65-69`
  `demote_feature_on_contradiction`/`promote_feature_on_clean` return a bare `bool` the CLI discards; a bool cannot distinguish the three transition strings the spec demands (spec.md:71 — `demoted X→AMBIGUOUS` / `restored …→Y` / `unchanged`), and the prior value `X` is never returned.
  *Fix:* widen the return type (e.g. `(transition, from_value, to_value) | None`) or read `feature.json` in the CLI; "emit at the CLI from the existing return value" understates the change.

- **F11 · Task 2 — retiring `_atomic_write` touches THREE sites, not two.** · `dummyindex/context/domains/reality_check/__init__.py:74`, `render.py:16-17`, `confidence.py:16`
  `_atomic_write` is re-exported at `__init__.py:74` **and** used in-file by `write_report` (`render.py:16-17`), not only imported by `confidence.py:16`.
  *Fix:* repoint `render.py:16-17` + `confidence.py:16` at `write_text_atomic`, drop the `__init__.py:74` re-export, then delete the def — else a `NameError` / dangling re-export.

- **F12 · Task 4c acceptance — the immutability test must capture the cached-dict reference BEFORE build.** · `dummyindex/pipeline/extract/__init__.py:177,189-197`
  `id_remap` mutates in place dicts aliased from `load_cached` (`all_nodes.extend(...)` at `:177` shares refs; re-consumed by later passes at `:201,210,224-225`). The acceptance (spec.md:55) only proves non-mutation if the test holds the object from the **first** `load_cached` call — a re-`load_cached` returns a fresh copy (false pass).
  *Fix:* name the mechanism in Task 4c ("patch `load_cached` to return a sentinel dict; assert its `id` untouched post-`extract`").

- **F13 · Task 7b acceptance — the nested-`.context/` fixture needs a real `.git` (or patched `is_git_repo`).** · `dummyindex/context/domains/reality_check/verify.py:63,376-384`, `tests/context/domains/test_reality_check.py:47-110`
  The existing `fake_context` fixture sets `meta["root"] == context_dir.parent`, so it cannot exercise the nested case; the positive control (spec.md:67, honor a genuine root) needs an actual git toplevel.
  *Fix:* name "new fixture + `.git` dir (or patched `is_git_repo`/`resolve_git_dir`)" in Task 7b, and anchor the equality check to the **resolved** git toplevel (not string-equality), else a trailing-slash/symlinked-but-genuine root regresses to fallback.

- **F14 · Task 5 acceptance — pin a TOTAL hyperedge sort key.** · `dummyindex/export/graph.py:36`, `dummyindex/context/build/validate.py:81-82`
  The plan says "stable key" without naming one; the open hyperedge schema (extra optional fields) makes a single field insufficient.
  *Fix:* pin a total key (e.g. `json.dumps(h, sort_keys=True)`) in spec.md:58. *(Latent today — committed `hyperedges == []` — but Task 5 is genuinely outstanding and correctly scoped.)*

### LOW / INFO — fix-in-place, not blocking

- **F15 · Task 10 citation drift.** · `confidence.py` — the stash pop is `:90` (not `:91-93`), the no-match loop `:108-110`; re-cite promote `:85-94` + demote `:55-61`. The atomic fault-injection seam is **`Path.replace`** (`atomic_io.py:24`), **not** `os.replace` (the plan's check #1 mis-names it). Meaning unchanged.
- **F16 · `plan.md:39` typo** — "Tasks 5/5" should name the community (Task 6) + hyperedge (Task 5) pair driving the one-time committed-bytes change.
- **F17 · spec.md:19-20 loose generalization** — calls all six pre-existing guards "inline `resolve().relative_to()`" but `cli/common.py:42` and `reconcile_gate.py:66` operate on **already-resolved** paths; `resolve_under_root` must handle both already-resolved and not-yet-resolved candidates uniformly.
- **F18 · Audit report citation drift (informational, read-only history)** — the report's P2 cites `references.py:99-111`; after `c574d41`'s rewrite the read moved to `_read_text_safely` (`:164-176`). And `3d7d539`'s "mark C2/C3 resolved" message overstates C2 (single-backend resolved; cross-backend GATE remains open).

---

## Confirmations — the plan is RIGHT here (recorded so they are not re-litigated)

- **Determinism scoping is accurate.** Task 5 (hyperedges) genuinely outstanding; nodes/links already sorted (`graph.py:40-41`), `sort_keys=True` (`:43`). Single-backend seed+tiebreak (C2/C3) landed in `c574d41`; the **GATE is genuinely still-open** (cross-backend Leiden-vs-Louvain, no injectable seam) and consistently marked across plan/spec/checklist. The one-time committed-bytes change is correctly flagged (Wave-4 compares two post-change rebuilds); **no existing committed-golden test breaks** (verified across `test_graph_determinism`, `test_output_hygiene`, `test_graph`, `test_reality_check`).
- **The four trust-boundary threats are REAL and the fixes are sound at the noted seams** — read-oracle (`verify.py:179-202`→`:144`), `meta["root"]` whole-FS join (`:376-384`,`:63`), `--feature` out-of-`features/` write primitive (`cli/reality_check.py:62`→`render.py:12-13`), symlink-escape read — subject to F2 (symlink seam) and F4 (test payloads).
- **Atomic mirror (Task 10) targets 3 real defects** — non-atomic two-file write, pop-before-mirror data-loss ordering (`confidence.py:90`), silent no-INDEX-match no-op (`:108-111`) — plus missing `sort_keys`; honestly scoped as best-effort.
- **Cache schema (Task 3b) won't mass-invalidate** (`id`-string on nodes only, not edges); but it is **anti-corruption, not anti-poisoning** (a well-formed poisoned graph passes — the real lever is dir confinement, F1). **`_body_content` (Task 3c) is real and sharper than framed** — a loose `text.find("\n---")` substring match truncates at a non-bare `---hack` (`cache.py:13-15`), serving a stale cache.
- **`paths.py` (Task 1) layering is clean and cycle-free** (`pipeline/io` lowest; `context→pipeline.io` arrow live at `context/__init__.py:64`); the six-guard consolidation list verifies; `paths.py`/`log_scan.py`/`last_matching` are genuinely net-new. **Wave-2 intra-wave file sets are pairwise disjoint** (safe to fan out); cross-wave reuse is correctly serialized.
- **No NEW trust-boundary hole is missed** beyond the four targeted; the git module is injection-free; ReDoS is not present in the single-pass matcher (Task 12 must preserve the `re.escape` + lookahead-only construction).

## Refuted / overturned during this meta-audit (recorded so they aren't re-raised)

- **The round-1 "just confine the env var, nothing legitimate is lost" remedy for F1 — REFUTED** by the refutation pass: `DUMMYINDEX_CACHE_DIR` is a documented user-facing opt-out (`cache.py:47`, `CHANGELOG.md:1095`). The *finding* stands; its remedy was upgraded to a trusted-channel re-route.
- **"GATE (c) may be safe because `community` is in-memory" — REFUTED (CONFIRMED breaking)** by the refutation pass: feature-grouping consumes a same-build on-disk re-read (`runner.py:182-187`), and `community` exists only in the persisted file.

---

## Verdict

**On the audit results (`report.md`):** sound. Its findings were accurate when written and `c574d41` correctly resolved most (C2/C3 single-backend, M1/C5/M2/M3 dead code, M6 split, C4-trailing, P1). A couple of citations are now stale post-rewrite (informational — read-only history). `3d7d539`'s "C2/C3 resolved" overstates C2.

**On the plan:** a strong, mostly-accurate plan that correctly scopes genuinely-outstanding work — but **not ready to implement as written.** Fix the **6 HIGH** defects first (F1 cache trust-model, F2 symlink anchor, F3 Task-12 scope, F4/F5/F6 three false-pass/non-constructible acceptance tests), record the GATE-(c)-breaking input (F7) in the GATE decision, and fold in the 9 MEDIUM scoping/acceptance corrections. None are fatal — all are revisions of mechanism, scope, or test wording, not of the plan's direction.

*Read-only audit. Fixes are a separate `/dummyindex-plan` → `/dummyindex-build` cycle seeded from this report.*
