# Spec — Ponytail-derived improvements: debt ledger, equip invariant canary, audit over-engineering lens, correctness-gated retrieval eval, .context freshness statusline

## Intent

Five mechanisms mined from the **ponytail** repo (`DietrichGebert/ponytail`) map cleanly onto seams dummyindex already owns. Each **extends a current feature**; none adopts ponytail's "lazy dev" persona or its multi-host rendered-copy distribution (out of scope — dummyindex is single-platform).

For **dummyindex maintainers** (internal Python changes) and, downstream, every repo dummyindex indexes/equips.

| # | Improvement | Current feature it extends | Primary seam |
|---|---|---|---|
| 1 | **Debt ledger** | rationale extraction + drift signal (community-8) | `pipeline/extract/python_rationale.py`, new `context/domains/debt/`, `cli/debt.py` |
| 2 | **Equip invariant canary** | hash-baselined equip lifecycle (community-0/6) | `equip/lifecycle/status.py`, `cli/equip/dispatch.py`, `equip/models.py`, `equip/enums.py` |
| 3 | **Audit over-engineering lens** | argue-and-audit persona catalog (community-0) | `skills/audit/agents/*.md`, `audit/catalog.py` |
| 4 | **Correctness-gated retrieval eval** | deterministic `context query` retrieval | `context/domains/query.py` (reuse only), new `tests/eval/` |
| 5 | **`.context/` freshness statusline** | SessionStart drift hook (community-8/3) | `context/drift.py`, `cli/plan_update.py`, new `cli/statusline.py`, `context/hooks.py` |

**Approach:** TDD per task; honor `conventions/naming.md` and the repo's frozen-dataclass / enum-constant / typed-exception / strict-layering / CLI-boundary-I/O conventions. Every change is **additive and backward-compatible** — absent/empty new state reproduces today's behaviour exactly. Revised once after a critique panel; see **Decisions** for the resolved risks.

## Decisions (resolved by the critique panel — read before implementing)

- **D1 — `.context/` is fully gitignored in *this* repo** (root `.gitignore:19` = bare `.context/`; `git ls-files .context` = 0). So the debt ledger **prints to stdout by default** (like `query`) and only writes `.context/debt.md` under an explicit `--write`. Whether that file is committed is the *host* repo's `.context/` policy, not ours. Independently, **every ledger row uses a repo-relative POSIX path** (reuse `drift._rel_or_none`) so the output is reproducible across machines and never leaks a home dir — true regardless of commit status. The badge cache lives under `.context/cache/` (scratch, gitignored in every repo via `.context/.gitignore`).
- **D2 — never-clobber is enforced by *callers*, not `classify_item`.** The guard `state is ItemState.USER_MODIFIED` is duplicated in `refresh` + `uninstall` (`status.py`) and `apply` (`cli/equip/dispatch.py`). The canary therefore adds an `is_user_owned(state)` predicate (`{USER_MODIFIED, CUSTOMIZED, INVARIANT_BROKEN}`) and replaces **every** such guard, in one task, so the new states are skipped from auto-rewrite/re-baseline exactly as `USER_MODIFIED` is today.
- **D3 — `EquipmentItem.to_dict` omits `invariants` when empty** → a v3 manifest is byte-identical to today; **no `SCHEMA_VERSION` bump** (the new states are computed at runtime, not persisted). Documented inline.
- **D4 — `invariants` is manifest metadata, like `grounded_in`** — assembled in the `GenerateSpec`/`specialists.py` → `EquipmentItem` path, **never written into the rendered bytes** (so it can't perturb the `origin_hash` lifecycle).
- **D5 — the retrieval eval runs on a frozen index, not the live `.context/`.** The live index is un-enriched (`community-N`, `summary: null`) and re-clusters on rebuild, so gating on its ids is brittle. The eval **reuses the `SAMPLE_REPO` + `build_all` fixture** already used by `tests/context/domains/test_query.py`, giving a deterministic, stable index with authored ids; the gate threshold is derived from a **committed baseline** (`tests/eval/BASELINE.md`).

## Contracts

### 1. Debt ledger
- **Seams:** factor a `DEBT_PREFIXES` subset (`# TODO:`, `# FIXME:`, `# HACK:`, `# DEBT:`) out of `_RATIONALE_PREFIXES` in `pipeline/extract/python_rationale.py` (also add `# DEBT:` to the rationale set); new deterministic `context/domains/debt/` (`harvest.py` + frozen-dataclass `models.py`); new CLI `dummyindex context debt` (`cli/debt.py`).
- **Scope (v1):** **Python `.py` files only** — the markers are Python `#`-comment syntax. Enumerate via `detect()` filtered to `.py` under `files["code"]`; inherit `detect()`'s ignore/sensitive exclusions by design. TS/other-language debt is explicitly out of v1 (documented, not a silent miss).
- **Matching:** a marker counts only when the **stripped line is a true comment** beginning with a `DEBT_PREFIXES` entry (parse the **raw line**, not the truncated rationale node). Structured form `# DEBT: <ceiling>; upgrade: <trigger>`.
- **I/O:** prints the ledger to stdout (default) and writes `.context/debt.md` under `--write` (+ `--json`). Rows **repo-relative**, grouped by file in **path-sorted** order, rows in **line order**: `path:line — <ceiling>. upgrade: <trigger>.`; ends `N markers, M with no trigger.`
- **`no-trigger` rule (exact):** a plain `# TODO`/`# FIXME`/`# HACK` (no `upgrade:` clause) ⇒ `no-trigger`; a `# DEBT: <ceiling>; upgrade: <t>` ⇒ trigger captured; a `# DEBT:` with a ceiling but no `upgrade:` ⇒ `no-trigger`; a malformed/empty `# DEBT:` ⇒ degrade to `no-trigger`, never raise. `M` in the tally equals the count of `no-trigger` rows.
- **Invariants:** read-only over source; deterministic (no LLM; re-run on an unchanged tree ⇒ byte-identical output); skips an unreadable file without raising; clean repo prints the no-debt message.

### 2. Equip invariant canary
- **Seams:** `EquipmentItem` (`equip/models.py`) gains `invariants: tuple[str, ...] = ()`, **omitted from `to_dict` when empty** (D3), assembled as metadata (D4); `ItemState` (`equip/enums.py`) gains `CUSTOMIZED` (hash differs, all invariants present) and `INVARIANT_BROKEN` (hash differs, ≥1 invariant missing); `classify_item` (`status.py`) consults invariants **only when the hash differs** (empty invariants ⇒ `USER_MODIFIED`, byte-identical to today); the new `is_user_owned(state)` predicate replaces the `USER_MODIFIED` guard in `refresh`/`uninstall` (`status.py`) and `apply` (`cli/equip/dispatch.py`) (D2).
- **Invariant (CRITICAL):** the never-clobber contract is preserved across **all** call sites — `apply`, `refresh`, `uninstall` all leave `CUSTOMIZED`/`INVARIANT_BROKEN` files byte-untouched and **do not re-baseline** them (so an `INVARIANT_BROKEN` alarm is never laundered to `PRISTINE` on the next `apply`). Empty invariants ⇒ the two new states are **unreachable** ⇒ today's exact behaviour.
- **Output:** `status` (and `equip status --json`) report the new states; `RefreshReport` gains an `alarm_invariant_broken` tuple. Any golden fixture asserting the closed `ItemState`/`--json` value set is updated.

### 3. Audit over-engineering lens
- **Seams:** new persona file `skills/audit/agents/over-engineering.md` mirroring the `PersonaCard` frontmatter schema and `maintainability.md`'s section layout; register `"over-engineering": ("review",)` in `_PERSONA_CAPABILITY_PREFS` (`audit/catalog.py`).
- **Body contract (enforced by test — `parse_persona` only reads frontmatter):** the five tags `delete:`/`stdlib:`/`native:`/`yagni:`/`shrink:`; one line per finding `path:Lstart-Lend — <tag> <what>. <replacement>.`; ranked biggest-cut-first; footer `net: -N lines, -M deps possible.`; complexity-only carve-out (correctness/security/perf belong to the other auditors); never flag the one sanctioned self-check as bloat. `subagent_type: Code Reviewer`.
- **Invariant:** additive — `load_catalog` globs `*.md` so it's auto-discovered; existing personas unchanged. `resolve_catalog` maps the card onto a `Code Reviewer` roster agent when present, else a `review`-capable agent (the pref), else `general-purpose` — all three paths tested.

### 4. Correctness-gated retrieval eval
- **Seams:** new `tests/eval/` (`retrieval_fixtures.json`, `test_retrieval_eval.py`, committed `BASELINE.md`), reusing `query()`/`tokenize()` and the `SAMPLE_REPO`+`build_all` harness from `tests/context/domains/test_query.py` (D5). **No retrieval-logic change.**
- **Fixtures (≥12):** `{question, expected_feature_id, expected_path}` against the sample-repo index. Each question shares **≥1 non-stopword token with a file basename or symbol name** of its expected feature (verified, not assumed — since `summary` is null, name/summary weights contribute nothing). Assertions key on the **stable expected file path** appearing in the top-K match's files/citations (paths survive re-clustering; ids do not).
- **Metrics (paired, mirroring ponytail's `loc.js` + `correctness.js`):** *recording* — MRR + mean `total_estimated_tokens`, always printed; *gate* — **hit-rate@3 ≥ T_hit AND MRR ≥ T_mrr**, K=3, with `T_hit`/`T_mrr` set one documented margin below the baseline recorded in `BASELINE.md`. Deterministic (no LLM).
- **Negative control (permanent test):** a fixture pointing at a known-wrong id/path is asserted to score 0 / rank ∞ — proving the gate is non-vacuous.

### 5. `.context/` freshness statusline
- **Seams:** a **pure** `compute_badge(report) -> str` helper in `context/drift.py`; the **write** happens at the CLI boundary in `cli/plan_update.py` (the SessionStart `plan-update` path) via `atomic_io.write_text_atomic` after `mkdir(parents=True, exist_ok=True)` on `.context/cache/`, wrapped in its own try/except that never propagates into drift reporting; new CLI `dummyindex context statusline` + a shipped `statusline.sh`/`.ps1` that **reads the cache file directly** (no Python on the per-prompt hot path), with the Python command as a cold-path fallback that catches every exception → empty stdout, `exit 0`; `context/hooks.py` emits an **emit-only nudge** (writes nothing to settings) when no `statusLine` is configured.
- **Invariants (CRITICAL):** the nudge **never writes `statusLine`** (a scalar has no sentinel to make a write idempotent) — so no clobber is even attempted; it checks **both** global and local settings and stays silent if either defines `statusLine`; it swallows `MalformedSettingsError` like the other hook paths. The badge write is best-effort (a missing/unwritable cache never fails the hook). The statusline command is fast (reads a cached count; never recomputes drift).

## Acceptance

**Debt ledger**
- [ ] `dummyindex context debt` prints a per-file, path-sorted, repo-relative ledger of `# TODO:`/`# FIXME:`/`# HACK:`/`# DEBT:` markers found **only in `.py` source**; `--write` persists `.context/debt.md` and `--json` emits a stable sorted structure; re-running on an unchanged tree is byte-identical; a clean repo prints the no-debt message. (unit + CLI test)
- [ ] No rendered row contains an absolute path (`/home/`, `/Users/`, `/mnt/`). (test)
- [ ] `no-trigger` classification matches the exact rule (plain marker ⇒ `no-trigger`; `# DEBT: c; upgrade: t` ⇒ trigger; `# DEBT: c` ⇒ `no-trigger`; malformed ⇒ `no-trigger`, no raise) and the trailing `M` equals the `no-trigger` count; an unreadable/binary file is skipped without raising and excluded from the tally; a `# TODO:` inside a markdown heading is **not** counted. (unit test)

**Equip invariant canary**
- [ ] With `invariants=()`, `classify_item` returns only `PRISTINE`/`USER_MODIFIED`/`MISSING` (the two new states are **unreachable**) and `refresh`/`apply`/`uninstall` make identical decisions to today; `EquipmentItem.to_dict` omits the `invariants` key, so a v3 manifest is byte-identical. (backward-compat test)
- [ ] With invariants set, a cosmetic edit ⇒ `CUSTOMIZED`, a convention-deleting edit ⇒ `INVARIANT_BROKEN`; `apply`, `refresh`, and `uninstall` each leave both files **byte-untouched** and do **not** re-baseline them (re-running `apply` still reports `INVARIANT_BROKEN`, not `PRISTINE`). (unit test across all three call sites)
- [ ] Rendering a generated specialist produces an `EquipmentItem` whose `invariants` is **non-empty**, each entry a literal substring of the rendered body and **absent from the rendered bytes' hashed metadata**; deleting one such substring from the file and re-classifying yields `INVARIANT_BROKEN`. (render round-trip test — proves the canary isn't a no-op)
- [ ] `equip status --json` consumers / golden fixtures handle the new `ItemState` values. (test audit)

**Audit over-engineering lens**
- [ ] `load_catalog` returns an `over-engineering` `PersonaCard` with `subagent_type: Code Reviewer` and `role`/`triggers`/`description` set, whose **body** contains all five tag tokens, the `net: -N lines` footer, and the complexity-only carve-out sentence; `_PERSONA_CAPABILITY_PREFS["over-engineering"] == ("review",)`; `resolve_catalog` resolves to a `Code Reviewer` agent when present, to a `review`-capable agent otherwise, and to `general-purpose` when neither exists. (catalog test, all three paths)

**Retrieval eval**
- [ ] `pytest tests/eval/test_retrieval_eval.py` asserts **hit-rate@3 ≥ T_hit AND MRR ≥ T_mrr** (floors in `BASELINE.md`, set below the recorded baseline) over ≥12 fixtures against the `SAMPLE_REPO` index, and prints MRR + hit-rate@3 + mean tokens; a permanent negative-control case asserts a known-wrong target scores 0 / rank ∞. (eval test)
- [ ] Every fixture question shares ≥1 non-stopword token with a file basename or symbol name of its expected feature. (fixture-validation assertion in the test)

**Freshness statusline**
- [ ] `dummyindex context statusline` prints `[ctx ✓]` when the badge cache shows fresh and `[ctx: N drift]` when it shows N; a missing `.context/`, missing cache, or malformed cache ⇒ empty stdout, `exit 0`. (unit test)
- [ ] Given a settings.json that already defines `statusLine` (local **or** global), the SessionStart hook emits no nudge and the file's bytes are unchanged; given neither, it emits exactly one nudge and still writes nothing to settings. (hook test, both directions)
- [ ] A missing/unwritable `.context/cache/` does not fail the SessionStart hook and does not affect the drift report. (test)

**Whole**
- [ ] ≥80% coverage on each new module. (coverage gate)
- [ ] The new files are folded into `.context/` via the **reconcile procedure** (place/enrich the drifted features, then `reconcile-stamp`) — afterwards `compute_drift` reports no `unassigned_new_files`/`awaiting_enrichment` for them. (`rebuild --changed` only refreshes the deterministic backbone; it does **not** author the feature docs.)

> Process (not acceptance): run `/code-review` over the full diff and resolve CRITICAL/HIGH before merge.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `community-0`
- `community-3`
- `community-6`
- `community-1`
- `community-8`

**Conventions to honor:**

- `conventions/naming.md`

<!-- dummyindex:consistency:end -->
