# Multi-agent council — spec

`confidence: INFERRED`

## Intent

For every non-trivial feature, the council runs a fixed sequence of LLM stages. Dev drafts `spec.md`. An architect reorganises `plan.md`. Critics file `concerns.md`. Dev narrates flows. A tree-enrich pass runs last. It is on by default. Opt out per run with `--no-tree-enrich`. Independent features fan out to parallel Task subagents.

The code in this feature is the **deterministic plumbing** between dispatches. It runs no LLM.

One stage sits outside this machinery. `council/58-codebase-scan.md` (skill phase 4.8) authors the repo-wide scan at `features/graph.json`. It edits the PageRank-ranked deterministic seed, never an invent-from-scratch rewrite (`dummyindex/skills/council/58-codebase-scan.md:11-33`). Each ranked node is kept, reworked, or dropped. Nodes carry `evidence` and `symbolRef`. Groups are grounded in `features/graph-communities.json`. Caps are 120 nodes and 240 edges, aim 40–80.

The scan is whole-repo and single-agent, not per-feature. So it is not a `CouncilStage`. It never appears in `active_stages`. It has no `_council-log.json` entry. Its completion marker is the artifact's own `confidence: INFERRED`. Its feedback loop is `dummyindex context scan-check`, not a critic.

From the append-only per-feature audit logs alone, the code computes the earliest incomplete stage across all features. It also computes the dispatch units to launch for that stage: which agent, for which feature, in which role. It records each invocation's outcome. A crashed or partial run then resumes without redoing finished work.

## User-visible behavior

### `council-batch --next` (frontier)

`dummyindex context council-batch --next` prints the next parallel dispatch frontier (`cli/council_batch.py:65-209`). It loads every feature id from `features/INDEX.json` (`cli/council_batch.py:54-62`). Repeatable `--feature ID` scopes the run. It then asks the domain for the frontier.

Flags:
- `--next` — required. Absent is a usage error (`cli/council_batch.py:93-94`).
- `--depth light|standard|deep` — canonical effort selector. `--mode` is a back-compat alias. Passing **both** is rejected (`cli/council_batch.py:108-112`).
- `--cap N` — feature-granular unit cap, default `8`. A non-integer is a usage error (`cli/council_batch.py:120-124`).
- `--no-tree-enrich` — drops the stage-5 tree pass. The pass is **on by default** in every depth (`cli/council_batch.py:104-108`). `--tree-enrich` stays as an accepted no-op for older callers. The domain takes `tree_enrich` as a required keyword. The default lives only at the CLI boundary.
- `--json` — machine-readable payload instead of the human listing.
- `--feature ID --force` — scoped forced re-council. `--force` without any `--feature` is a usage error (`cli/council_batch.py:96-102`).

**Depth/error handling (current, two-layer).** The depth flag is validated first, against `CouncilMode` values. An unknown value prints `error: --depth/--mode must be light|standard|deep, got <value>` and returns `2` (`cli/council_batch.py:113-119`). Only then does it call `config.resolve_depth(repo_root/".context", DepthCommand.BUILD, depth_flag)` (`cli/council_batch.py:129-130`). The flag is already valid. So any `ConfigError` raised there can only mean a malformed `config.json`. The CLI prints that real error verbatim: `error: <exc>`, return `2` (`cli/council_batch.py:131-134`). It no longer reprints the `--depth/--mode` message. Precedence inside `resolve_depth`: the `--depth`/`--mode` flag, then `config.command_depths[build]`, then `config.mode`, then `standard` (`config.py:323-342`). The flag is a one-run override, never written to config.

Unknown `--feature` ids (not in `INDEX.json`) print `error: unknown --feature id(s): ...` and return `2` (`cli/council_batch.py:149-157`). A missing `features/INDEX.json` prints `error: ... not found. Run dummyindex ingest first.` and returns `2` (`cli/council_batch.py:136-141`).

Output shapes:
- Human: a header `council-batch: stage N — K parallel unit(s) (dispatch concurrently, barrier, then re-run --next):`, then one `  feature_id: role → subagent_type [framework]` line per unit (`cli/council_batch.py:198-208`). A forced run first prints `council-batch: forced re-council for: <ids>` (`cli/council_batch.py:196-197`). When every active stage is done, it prints `council-batch: all features complete for this mode.` and returns `0` (`cli/council_batch.py:198-200`).
- `--json`: `{ "complete": bool, "stage": int|null, "mode": str, "cap": int, "forced": [ids], "units": [unit, ...] }` (`cli/council_batch.py:185-194`).

Before dispatching, it warns on stderr when **more than half** the scoped features have enrichment artifacts but empty logs. That is the pre-v0.20 shape. The frontier would re-run those features and clobber them (`cli/council_batch.py:27-51`, `council.needs_artifact_backfill`).

### `council-log`

`dummyindex context council-log --feature ID --stage N --agent NAME --status STATUS [--note ...]` appends one audit entry. It validates the status, a non-negative stage, and an agent name with no `/`. The entry goes to `features/<id>/council/_council-log.json` via `council.append_log` (`council.py:105-162`). The `council-log backfill [--feature ID]` subverb synthesises `complete` entries. It targets stages whose council-authored artifacts exist on disk but have no log records. A pre-v0.20 index is then not wrongly rescheduled from stage 1 (`council.backfill_log_from_artifacts`, `council.py:253-294`).

### `dev-pick`

The dev-stage picker decides which stack-specialist authoring persona writes a feature's docs. It is deterministic and first-match-wins over a precedence table (`dev_pick.py:255-273`). Inputs: the feature's file list and the repo's harvested dependency tokens. It always returns a persona, via the constant-true fallback rule. It also returns an ordered `fallbacks` ladder. The orchestrator tries these when the primary subagent is not installed (`dev_pick.py:52-63`).

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
`stage` is the int wire form of `CouncilStage`. `role` doubles as the `council-log --agent` value and the persona-file selector. `framework` is non-null only for dev-authored stages (specify, flow, tree). It is `null` for architect and critic units.

**Stage ordering** (`active_stages`, `council_batch.py:64-77`): always `SPECIFY`. `STANDARD` and `DEEP` add `PLAN`, then `CRITIQUE`. Then `FLOW`. `TREE` is appended whenever `tree_enrich` is set. The CLI sets it **on by default** (opt out with `--no-tree-enrich`). So stage 5 is part of every depth, including `light`.

The frontier advances strictly in this order. A stage is the frontier only if at least one pipeline feature has not completed it (`earliest_incomplete_stage`, `council_batch.py:91-111`). A feature joins a stage only once its prior active stage is complete (`_feature_ready_for`, `council_batch.py:149-163`).

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
- `resolve_depth(context_dir, command, depth_flag) -> CouncilMode` — `config.py:323-342` — the single seam every depth caller shares. It raises `ConfigError` on an invalid flag or malformed `config.json`.

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

Happy-path trace: scoped forced re-council of one already-complete feature, `dummyindex context council-batch --next --feature auth --force`.

1. Flags parse: `feature_values=("auth",)`, `force=True`, `--next` present (`cli/council_batch.py:80-102`).
2. `auth` resolves against `INDEX.json`. The depth flag is absent, so `resolve_depth(.., BUILD, None)` runs. It returns `command_depths[build]`, else `config.mode`, else `standard` (`cli/council_batch.py:126-160`).
3. `force_recouncil(features_dir, ("auth",), mode=..., tree_enrich=False)` runs (`council_batch.py:114-137`). `auth` has no incomplete active stage. So it gets a stage-0 `recouncil` reset marker. `forced=("auth",)` (`council.append_reset_marker`, `council.py:212-229`).
4. `next_batch` recomputes the frontier. Entries before the marker no longer count (`is_stage_complete`, `council.py:188-205`). So `auth` re-surfaces at `SPECIFY` with one dev unit.
5. Output: `council-batch: forced re-council for: auth`, then `council-batch: stage 1 — 1 parallel unit (...)`, then `  auth: dev -> <subagent> [<framework>]` (`cli/council_batch.py:196-208`). Re-running mid-run is idempotent: `auth` now has an incomplete stage, so `force_recouncil` leaves it alone (`council_batch.py:129-135`).
