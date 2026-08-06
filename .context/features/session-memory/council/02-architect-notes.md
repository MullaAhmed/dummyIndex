# Architect notes — session-memory (stage 2)

## What I changed

- **"Where it lives" reorganised from a file inventory into three named nested
  contexts** (A tier store / B miner subpackage / C staleness readers) with the
  boundary invariant stated first. The dev's list was accurate but flat — a
  reader could not tell which modules are separable. The A↔B coupling is now
  quantified (two edges, one of them only in the unwired half), which is what
  makes the miner's future reversible.
- **Added a `### Dependency direction` subsection.** The draft had no dependency
  view at all. This is where the substantive correction landed — see below.
- **Corrected "no in-tree Python callers" (implied by the draft's
  "Boundary. `cli/memory.py` (wire-only)").** Four in-tree modules import this
  feature: `context/build/runner.py:245-249`, `cli/gc.py:181-182`,
  `cli/guard_doc_write.py:27`, `cli/reconcile_gate.py:13`. The build runner one
  matters most — the store is seeded on every rebuild, not only by `memory init`.
- **Promoted the hook wiring from two line-refs to an event→verb table**
  (`hooks.py:110-145,147-198,200-227,229-243`). That map *is* the downstream
  contract; two citations did not convey that SessionStart runs four commands.
- **Promoted the miner-half distinction from prose into a two-row table** with an
  explicit `Wired?` column, so the wired/unwired split survives skimming. The
  dev's flag is preserved and sharpened, not softened.
- **Added the map-staleness caveat.** `.context/map/symbols.json` is anchored at
  `1d54184`, three commits behind `ef038c0`; it contains zero miner symbols and
  `feature.json.members` therefore lists none. Any future reader checking miner
  citations against the map will find nothing. This also explains the "map noise"
  the dev noted (`enums_confidencelevel` → `dummyindex/pipeline/enums.py:17`),
  which I demoted from a standalone paragraph to one clause.
- **Key decisions: added #2 (miner as nested subpackage) and trade-off clauses on
  #1, #3, #6, #10, #12.** Several draft entries stated mechanism without stating
  the cost. Renumbered 12 → 13.
- **Cut filler:** the attribution paragraph went from six lines to two (the
  license artifact and the correction survive; the audit narrative does not);
  "Architecture in three sentences" tightened and each clause given a citation;
  the `.context/conventions/data-access.md` conflict moved into Data model as a
  flagged ⚠ line instead of a mid-paragraph aside, and its second staleness (the
  range, not just the mechanism) added.

## Patterns named

- **Repository over a closed-alphabet file set** — `store.py:11-31` (locate +
  non-destructive create) with `parse.py:24-49` as the (de)serializer and
  `enums.py:8-39` as the alphabet.
- **Age-partitioned tier cascade** — `roll.py:44-108`, partition `roll.py:22-31`,
  date key `parse.py:52-55`.
- **Verb dispatcher over a closed enum** — `cli/memory.py:59-180`, alphabet
  `memory/enums.py:17-26`.
- **Pipeline (resolve → scan → group → write), two instances** —
  `miner/pipeline.py:40-109` (unwired) and `:112-152` (wired); the composition
  rule is stated in the module docstring at `miner/pipeline.py:1-12`.
- **Port + override seam to the host store** — `miner/resolve.py:44-67`
  (`override` is exclusive by design, `resolve.py:40-45`); the live-session
  counterpart is `transcript.py:52-86`.
- **Validating parser, fail-closed** — `feedback.py:136-200`: parses to
  `tuple[RecurringSkillCorrection, ...]` or returns `()`; no partial accept.
- **Cache-aside with write-elision** — `feedback.py:101-133` (compare-then-write),
  mirrored by `roll.py:81-82`.
- **Emit-only hook adapter (decide → render → exit 0)** — `cli/memory.py:87-155`,
  `emit.py:33-61`, `nudge.py:103-131`, `breadcrumb.py:118-127`,
  `plan_update.py:54-79`.
- **Idempotent side effect via LRU-pruned session memo** — `nudge.py:56-67`,
  `reconcile_gate.py:250-264` (both prune to 100).
- **One read model, two policies** — `compute_drift` (`drift.py:126-191`) read
  advisorily by `render_drift_summary` (`drift.py:194-234`) and authoritatively
  by `_gate_relevant` → `decide_block` (`reconcile_gate.py:321-399`).
- **Content-addressed cross-filter (three-oracle staleness)** —
  `drift.py:383-414` + `reconcile_gate.py:267-276`.
- **Feature-detect stand-down** — `detect.py:8-15`, gated at `emit.py:34`,
  `nudge.py:115`, `breadcrumb.py:121`.
- **Redact-by-default sanitizing renderer** — `scope.py:52-71`.
- **Canonicalization key with asymmetric branches** — `signatures.py:68-99`
  (structured input byte-faithful; shell input lossy).

## Dependencies surfaced

- **Upstream:** `build/manifest.read_manifest`,
  `build/reconcile.compute_reconcile_report`, `pipeline/io/detect.detect`
  (`drift.py:35-37`); `pipeline/io.submodule_paths` (`reconcile_gate.py:36`);
  `domains/atomic_io.write_text_atomic` (every writer). External read-only: the
  host transcript store; `git` via subprocess (`breadcrumb.py:57-95`).
- **Downstream (corrected):** `context/build/runner.py:245-249` →
  `ensure_memory_store`; `cli/gc.py:181-182` → `resolve_session_id`;
  `cli/guard_doc_write.py:27` and `cli/reconcile_gate.py:13` →
  `read_hook_stdin` / `resolve_transcript` from `cli/memory.py:26-56`. Plus the
  generated `.claude/settings.json` hooks. `cli/memory.py` is therefore a shared
  hook-stdin adapter, not a private wire — a signature change there breaks three
  other CLIs.
- **Fan-in:** `read_session_signal` (`transcript.py:137-175`) ← `nudge.py:124`,
  `breadcrumb.py:97`, `reconcile_gate.py:387`. Exactly three.
- **Miner ↔ parent coupling:** outward `feedback.py:10` and `render.py:29`
  (`atomic_io`), `render.py:30` (`..store.memory_dir`); inward
  `memory/__init__.py:18-23`. The `..store` edge exists only in the unwired
  failure-pattern half.
- **Deliberate non-edge:** `transcript.py:5-8` refuses `usage`, preserving
  `cli → context → analysis → pipeline`.
- **Cycles: none.** `reconcile_gate.py:33-35` imports `memory.nudge`,
  `memory.transcript`, `drift`; grep confirms no back-reference from any of the
  three. No `memory/*.py` imports `miner` except the `__init__` re-export.

## Decisions promoted

1. decided **the miner is a nested subpackage, not a peer domain**, because it
   feeds the same store over the same transcript substrate — and the near-zero
   import coupling keeps that reversible (was implicit at
   `memory/__init__.py:18-23` + `miner/pipeline.py:1-12`). New entry #2.
2. decided **the conservative direction on staleness doubt**: `_content_unchanged`
   returns `False` when the file cannot be hashed, so a hashing failure reports
   drift rather than hiding it (was implicit at `drift.py:400-414`). Added to #12.
3. decided **the miner verbs skip the `remember` stand-down** because
   skill-compliance feedback is orthogonal to handoff injection — there is no
   competing-block problem to solve (the draft noted the asymmetry but not the
   reason; `detect.py:8-15` vs `cli/memory.py:87-128`). Sharpened in #13.
4. decided **Bash keeps headroom's lossy normalization** because a shell command
   genuinely is opaque text, unlike structured JSON input (was implicit at
   `signatures.py:71-83`). Added to #10.
5. Trade-off clauses added where the draft asserted a choice without its cost:
   #1 (tiers cannot self-compress), #3 (no cross-transcript dedup), #6 (recall
   bounded by five regex patterns).

## Verification

Every `path:range` in the revised plan was checked against source. The map could
not be used for the miner at all — `.context/map/symbols.json` is anchored at
`1d54184` and contains **zero** `domains/memory/miner/` symbols, so all eleven
miner modules were verified by reading them. Corrections applied to draft
citations: `miner/enums.py:39-40` → `38-40`; `miner/scan.py:29-40` → `29-41`
(the 1000-char window constant is line 41); `feedback.py:14-19` → `14-23` (the
key frozensets are 22-23); `feedback.py:227-236` → `226-236`;
`miner/render.py:11-19` → `11-17`; `breadcrumb.py:122` → `121`;
`reconcile_gate.py:223-264` narrowed to `250-264` for the prune claim.

Doc conflicts flagged, code wins in both:
- `.context/conventions/data-access.md:7` (uncatalogued convention doc) claims
  `write_text_atomic` writes to `path + ".tmp"` at `atomic_io.py:11-24`. Both the
  mechanism and the range are wrong: `_replace_bytes:13-34` uses
  `NamedTemporaryFile` with a unique suffix, and `write_text_atomic` is at
  `atomic_io.py:37-47`.
- `SessionMemoryError`, referenced by three `DocConfidence.MEDIUM` plans
  catalogued in `docs.md`, does not exist anywhere in the domain (confirmed by
  grep). The draft's flag is retained.

`spec.md` untouched; no source file edited.
