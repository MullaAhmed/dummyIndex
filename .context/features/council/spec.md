# Multi-agent council — spec

`confidence: INFERRED`

## Intent

The council is dummyindex's per-feature documentation pipeline: for every non-trivial feature it drives a fixed sequence of LLM stages — dev drafts `spec.md`, an architect reorganises `plan.md`, critics file `concerns.md`, dev narrates flows, and (optionally) a tree-enrich pass — fanning *independent* features out to parallel Task subagents. The code in this feature is the **deterministic plumbing** the LLM skill calls between dispatches; it runs no LLM. From the append-only per-feature audit logs alone it computes the *earliest incomplete stage* across all features and the concrete dispatch units (which agent, for which feature, in which role) to launch for it, then records each invocation's outcome so a crashed or partial run resumes without re-doing finished work.

## User-visible behavior

### `council-batch --next` (frontier)

`dummyindex context council-batch --next` prints the next parallel dispatch frontier (`cli/council_batch.py:65-209`). It loads every feature id from `features/INDEX.json` (`cli/council_batch.py:54-62`), optionally scopes via repeatable `--feature ID`, then asks the domain for the earliest incomplete stage and its units.

Flags:
- `--next` — required; absent → usage error (`cli/council_batch.py:93-94`).
- `--depth light|standard|deep` — canonical effort selector; `--mode` is a back-compat alias. Passing **both** is rejected (`cli/council_batch.py:108-112`).
- `--cap N` — feature-granular unit cap, default `8`; a non-integer is a usage error (`cli/council_batch.py:120-124`).
- `--tree-enrich` — appends the stage-5 tree pass to the active stages.
- `--json` — machine-readable payload instead of the human listing.
- `--feature ID --force` — scoped forced re-council; `--force` without any `--feature` is a usage error (`cli/council_batch.py:96-102`).

**Depth/error handling (current, two-layer).** The depth flag is validated *up front* against `CouncilMode` values: an unknown value prints `error: --depth/--mode must be light|standard|deep, got <value>` and returns `2` (`cli/council_batch.py:113-119`). Only after that does it call `config.resolve_depth(repo_root/".context", DepthCommand.BUILD, depth_flag)` (`cli/council_batch.py:129-130`). Because the flag is already validated, any `ConfigError` raised there can *only* mean a malformed `config.json` — so the CLI now surfaces that real error verbatim (`error: <exc>`, return `2`) instead of always reprinting the `--depth/--mode` message (`cli/council_batch.py:131-134`). Precedence inside `resolve_depth`: `--depth`/`--mode` flag → `config.command_depths[build]` → `config.mode` → `standard` (`config.py:323-342`); the flag is a one-run override and is never written to config.

Unknown `--feature` ids (not in `INDEX.json`) → `error: unknown --feature id(s): ...`, return `2` (`cli/council_batch.py:149-157`). A missing `features/INDEX.json` → `error: ... not found. Run dummyindex ingest first.`, return `2` (`cli/council_batch.py:136-141`).

Output shapes:
- Human: a header `council-batch: stage N — K parallel unit(s) (dispatch concurrently, barrier, then re-run --next):` then one `  feature_id: role → subagent_type [framework]` line per unit (`cli/council_batch.py:198-208`). A forced run first prints `council-batch: forced re-council for: <ids>` (`cli/council_batch.py:196-197`). When every active stage is done: `council-batch: all features complete for this mode.`, return `0` (`cli/council_batch.py:198-200`).
- `--json`: `{ "complete": bool, "stage": int|null, "mode": str, "cap": int, "forced": [ids], "units": [unit, ...] }` (`cli/council_batch.py:185-194`).

Before dispatching it warns on stderr when **more than half** the scoped features carry enrichment artifacts but empty logs — the pre-v0.20 shape that the frontier would re-run and clobber (`cli/council_batch.py:27-51`, `council.needs_artifact_backfill`).

### `council-log`

`dummyindex context council-log --feature ID --stage N --agent NAME --status STATUS [--note ...]` appends one audit entry (validated status / non-negative stage / agent name with no `/`) to `features/<id>/council/_council-log.json` via `council.append_log` (`council.py:105-162`). The `council-log backfill [--feature ID]` subverb synthesises `complete` entries for stages whose council-authored artifacts already exist on disk but have no log records, so a pre-v0.20 index is not wrongly rescheduled from stage 1 (`council.backfill_log_from_artifacts`, `council.py:253-294`).

### `dev-pick`

The dev-stage picker resolves *which* stack-specialist authoring persona writes a feature's docs, deterministically and first-match-wins over a precedence table (`dev_pick.py:255-273`), from the feature's file list plus the repo's harvested dependency tokens. It always returns a persona (the constant-true fallback rule guarantees it) and supplies an ordered `fallbacks` ladder of alternative agents to try when the primary subagent isn't installed (`dev_pick.py:52-63`).

## Contracts

Batch frontier (`context/domains/council_batch.py`):
- `class CouncilStage(IntEnum)` — `SPECIFY=1, PLAN=2, CRITIQUE=3, FLOW=4, TREE=5` — `council_batch.py:31-38`
- `class CouncilMode(str, Enum)` — `LIGHT, STANDARD, DEEP` — `council_batch.py:41-46`
- `active_stages(mode, *, tree_enrich) -> tuple[CouncilStage, ...]` — `council_batch.py:64-77`
- `earliest_incomplete_stage(features_dir, feature_ids, *, mode, tree_enrich) -> Optional[CouncilStage]` — `council_batch.py:91-111`
- `force_recouncil(features_dir, feature_ids, *, mode, tree_enrich) -> tuple[str, ...]` — `council_batch.py:114-137`
- `next_batch(features_dir, repo_root, feature_ids, *, mode, cap, tree_enrich) -> Batch` — `council_batch.py:249-289`
- `@dataclass(frozen=True) class DispatchUnit(feature_id, stage, role, subagent_type, framework)` + `to_dict()` — `council_batch.py:166-183`
- `@dataclass(frozen=True) class Batch(complete, stage, units)` — `council_batch.py:186-192`
- `CRITIC_ROSTER: dict[CouncilMode, tuple[tuple[str, str], ...]]` — `council_batch.py:53-61`

The council-batch dispatch-unit JSON (one entry per `units[]`, `DispatchUnit.to_dict`, `council_batch.py:176-183`):
```json
{ "feature_id": "auth", "stage": 1, "role": "dev",
  "subagent_type": "Backend Architect", "framework": "FastAPI" }
```
`stage` is the int wire form of `CouncilStage`; `role` doubles as the `council-log --agent` value and the persona-file selector; `framework` is non-null only for dev-authored stages (specify/flow/tree), `null` for architect/critic units.

**Stage ordering** (`active_stages`, `council_batch.py:64-77`): always `SPECIFY`; `STANDARD`/`DEEP` add `PLAN` then `CRITIQUE`; then `FLOW`; `TREE` appended only when `tree_enrich`. The frontier advances strictly in this order — a stage is the frontier iff at least one pipeline feature has not completed it (`earliest_incomplete_stage`, `council_batch.py:91-111`), and a feature only joins a stage once its prior active stage is complete (`_feature_ready_for`, `council_batch.py:149-163`).

Council audit log (`context/domains/council.py`):
- `append_log(features_dir, *, feature_id, stage, agent, status, note=None, now=None) -> LogEntry` — `council.py:105-162`
- `read_log(features_dir, feature_id) -> list[LogEntry]` — `council.py:165-185`
- `is_stage_complete(features_dir, feature_id, stage) -> bool` — `council.py:188-205`
- `append_reset_marker(features_dir, feature_id, *, now=None) -> LogEntry` — `council.py:212-229`
- `is_standalone_complete(features_dir, feature_id) -> bool` — `council.py:232-250`
- `backfill_log_from_artifacts(features_dir, feature_id, *, now=None) -> tuple[int, ...]` — `council.py:253-294`
- `needs_artifact_backfill(features_dir, feature_id) -> bool` — `council.py:297-308`
- `latest_status(features_dir, feature_id, stage, agent) -> Optional[str]` — `council.py:334-346` (delegates to the shared `log_scan.last_matching`)
- `@dataclass(frozen=True) class LogEntry(timestamp, stage, agent, status, note)` + `to_dict()` — `council.py:87-102`
- `class CouncilLogError(ValueError)` — `council.py:83-84`

Dev picker (`context/domains/dev_pick.py`):
- `pick_dev(*, feature_files, dep_tokens) -> DevPick` — `dev_pick.py:255-273`
- `harvest_dep_tokens(repo_root) -> frozenset[str]` — `dev_pick.py:306-325`
- `read_feature_files(features_dir, feature_id) -> tuple[str, ...]` — `dev_pick.py:328-337`
- `@dataclass(frozen=True) class DevPick(persona_id, subagent_type, framework, fallbacks)` + `to_dict()` — `dev_pick.py:102-120`
- `class SubagentType(str, Enum)` / `class PersonaId(str, Enum)` — `dev_pick.py:28-40`, `dev_pick.py:66-76`
- `class DevPickError(ValueError)` — `dev_pick.py:123-124`

Effort resolution (`context/domains/config.py`):
- `resolve_depth(context_dir, command, depth_flag) -> CouncilMode` — `config.py:323-342` — the single seam every depth caller shares; raises `ConfigError` on an invalid flag or malformed `config.json`.

## Examples

```bash
# Next parallel frontier for the standard-mode pipeline, machine-readable.
dummyindex context council-batch --next --json
# -> {"complete": false, "stage": 1, "mode": "standard", "cap": 8,
#     "forced": [], "units": [{"feature_id":"auth","stage":1,"role":"dev",
#     "subagent_type":"Backend Architect","framework":"FastAPI"}, ...]}

# Record a dev stage-1 invocation's lifecycle.
dummyindex context council-log --feature auth --stage 1 --agent dev --status started
dummyindex context council-log --feature auth --stage 1 --agent dev --status complete
```

Happy-path trace — scoped forced re-council of one already-complete feature `dummyindex context council-batch --next --feature auth --force`:

1. Flags parse: `feature_values=("auth",)`, `force=True`, `--next` present (`cli/council_batch.py:80-102`).
2. `auth` resolved against `INDEX.json`; depth flag absent -> `resolve_depth(.., BUILD, None)` -> `command_depths[build]` or `config.mode` or `standard` (`cli/council_batch.py:126-160`).
3. `force_recouncil(features_dir, ("auth",), mode=..., tree_enrich=False)` (`council_batch.py:114-137`): `auth` has no incomplete active stage, so it gets a stage-0 `recouncil` reset marker; `forced=("auth",)` (`council.append_reset_marker`, `council.py:212-229`).
4. `next_batch` recomputes the frontier; entries before the marker no longer count (`is_stage_complete`, `council.py:188-205`), so `auth` re-surfaces at `SPECIFY` with one dev unit.
5. Output: `council-batch: forced re-council for: auth`, then `council-batch: stage 1 — 1 parallel unit (...)` and `  auth: dev -> <subagent> [<framework>]` (`cli/council_batch.py:196-208`). Re-running the same command mid-run is idempotent — `auth` now has an incomplete stage, so `force_recouncil` leaves it alone and the loop converges (`council_batch.py:129-135`).
