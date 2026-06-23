# 02 — Architect notes (stage 2, cli-dispatch)

## What I changed

- Added a **`## Bounded context`** section at the top, stating the three owned responsibilities (resolve token → alphabet, intercept help, route to one handler) and the explicitly disowned one (handler business logic lives in `context/domains/...`). The dev draft implied the boundary in the "Architecture in three sentences" prose; I made it the first thing a reader sees and named what is *out* of scope, so the per-command features (audit/equip/build/query) own their own handlers.
- Split the dense **"Architecture in three sentences"** paragraph into separate **`## Patterns`** and **`## Dependencies`** sections — the original folded pattern-naming, the acyclic-graph rationale, and the lazy-import mechanism into one run-on block where none could be cited individually. Cut the paragraph as filler once its content was redistributed.
- Promoted **"Key decisions"** → **`## Decisions`** with an explicit *decided X because Y, trade-off Z* shape on every bullet. The dev draft already carried strong rationale; I made the trade-off explicit on each instead of leaving it implied (per-invocation import cost of lazy imports; silent-degrade cost of hook handlers returning 0).
- **Corrected cited line anchors** against `map/symbols.json` + source: `usage_for` is `help.py:447` (draft said `:449`), `_line_starts_subcommand` is `help.py:434` (draft said `:436`). Kept the `:447-469` / `:434-446` spans that bound the bodies; only the start anchors moved.
- **Pinned the depth call sites** the draft left generic: `init` resolves with `DepthCommand.INGEST` (`init.py:50`), `reconcile` with `DepthCommand.RECONCILE` (`reconcile.py:64`).
- Kept `confidence: INFERRED` header and the `## Open questions` section (both still accurate). Left `spec.md` untouched.

## Patterns named

- **Command-enum → handler-table dispatch** — `__init__.py:84-126` (`_HANDLERS`) + `:135-139` (the `ContextSubcommand(subcmd)` / `ValueError` membership check).
- **Central help interception** — `__init__.py:58-81` (`_wants_help`) + `:144-146` (the short-circuit in `dispatch`).
- **Wire-only command handler** — each `cli/<sub>.py`; canonical example `init.py:38-56`.
- **Lazy-import table** — the deferred domain import inside `run()`, e.g. `init.py:38-40`.
- **Doc-as-data parity** — `help.py:447-469` (`usage_for`) + `:434-446` (`_line_starts_subcommand`).

Every pattern cites the exact span where it lives, per "no naming a pattern without showing where it lives".

## Dependencies surfaced

- **Upstream:** `__main__` → `dispatch(argv)` is the single entry; `__main__` also owns the `ingest`→`init` alias (`enums.py:41-45`), so the alias is *not* a dispatcher concern.
- **Downstream:** every handler lazy-imports `context/domains/...`; `init`/`reconcile` additionally bind `config.resolve_depth` + `CouncilMode`/`DepthCommand`/`ConfigError` (`config.py:68,84,104,323`).
- **No cycles, by enforcement:** the cli→domains edge is one-directional because domains never import `cli`; framed as a structural invariant (not a style convention), since the lazy-import pattern is what keeps `import cli` cheap and the graph acyclic.
- **Single shared set:** `_FLAGS_TAKING_VALUE` (`common.py:64-75`) is read by both `_wants_help` and `parse_path_and_root` — one source the two readers can't disagree on; also feeds the `--status` ambiguity in Open questions.

## Decisions promoted

- **Help wins everywhere** (`__init__.py:75-77`) — rationale kept (bare-equip-mutates hazard); trade-off made explicit (literal-`--help`-as-value is a sacrificed non-use-case).
- **Enum constructor as validator** (`__init__.py:135-139`) — "decided … because one source of truth feeds validation + dispatch + doc-sync"; trade-off is the failure-mode shift from runtime to `test_every_enum_member_has_a_handler` / doc-sync.
- **O(1) table + lazy imports** — split into its own decision; trade-off made explicit (per-invocation import cost, acceptable: one subcommand per process).
- **Depth validated before `resolve_depth`** (`init.py:42-56`, `reconcile.py:56-68`) — the load-bearing change; verified the up-front `CouncilMode` guard (`init.py:43`, `reconcile.py:57`) and the verbatim `ConfigError` surfacing (`init.py:51-56`, `reconcile.py:65-68`). Rejected alternative (string-matching the message) retained.
- **`usage_for` slices the canonical block, word-bounded** (`help.py:447-469`, boundary `:434-446`) — trade-off promoted: prefix collisions excluded by the boundary check, not naming discipline.
- **Hook-fed handlers return 0 unconditionally** (`memory`, `reconcile-gate`) — trade-off promoted: these handlers cannot signal failure via exit code and must degrade silently.

## Audit trail (code wins)

- Cited identifiers spot-checked against `map/symbols.json`: `_wants_help` (`__init__.py:58`), `dispatch` (`:129`), `ContextSubcommand` (`enums.py:40`; member count **41**, verified `len(list(ContextSubcommand)) == 41`), `usage_for` (`help.py:447`), `_line_starts_subcommand` (`help.py:434`), `resolve_depth` (`config.py:323`), `CouncilMode` (`:68`), `DepthCommand` (`:84`), `ConfigError` (`:104`), `parse_kv_flags` (`common.py:183`), `usage_error` (`:47`), `parse_path_and_root` (`:104`) — all resolve to their stated paths.
- `map/symbols.json` `range` is the def line only, so I read the source spans directly to confirm the load-bearing seams (`__init__.py:75-77`, `:135-139`; `init.py:42-56`; `reconcile.py:56-68`).
- **No code/doc conflict** on any load-bearing claim. Only corrections: two help.py start-anchor off-by-2/3 errors, fixed; `usage_for`/`_line_starts_subcommand` confirmed as distinct symbols (447 vs 434) so they are not transposed.
- `overview.md` lists `docs/specs/2026-06-10-parallel-council-dispatch-design.md` (DocConfidence.HIGH) — it concerns *council* parallel dispatch, not CLI dispatch; not authority for this feature, so not quoted.
