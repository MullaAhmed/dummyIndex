# Multi-agent council — spec

confidence: INFERRED

## Intent

The council is dummyindex's per-feature documentation pipeline: for every non-trivial feature it drives a fixed sequence of LLM stages — dev drafts `spec.md`, an architect reorganises `plan.md`, critics file `concerns.md`, dev narrates flows, and (optionally) a tree-enrich pass — fanning *independent* features out to parallel Task subagents. The implementation here is the **deterministic plumbing** the LLM skill calls between dispatches: it has no LLM. It computes, from the append-only per-feature audit logs alone, the *earliest incomplete stage* across all features and the concrete dispatch units (which agent, for which feature, in which role) to launch for it, then records each invocation's outcome so a crashed or partial run resumes without re-doing finished work. `council.py:1-34` states the three log purposes — resume, surface failures, audit. `council_batch.py:1-10` frames it as the council twin of build's `next_wave`.

## User-visible behavior

### `council-batch --next` (frontier)

`dummyindex context council-batch --next` prints the next parallel dispatch frontier (`cli/council_batch.py:65-188`). It loads every feature id from `features/INDEX.json` (`cli/council_batch.py:54-62`), optionally scopes via repeatable `--feature ID`, then asks the domain for the earliest incomplete stage and its units. Flags: `--depth light|standard|deep` (canonical; `--mode` is a back-compat alias — passing both is rejected), `--cap N` (default 8), `--tree-enrich`, `--json`, and `--feature ID --force` for a scoped forced re-council (`cli/council_batch.py:75-129`). The effort is resolved through `config.resolve_depth(.., DepthCommand.BUILD, depth_flag)` — precedence `--depth`/`--mode` flag → `config.command_depths[build]` → `config.mode` → `standard` — so an unset flag now honours a per-command `command_depths` override instead of a bare `standard` default (`cli/council_batch.py:105-129`). Human output names stage, unit count, and one `feature: role → subagent_type [framework]` line per unit (`cli/council_batch.py:177-188`); `--json` emits `{complete, stage, mode, cap, forced, units[]}` (`cli/council_batch.py:164-173`). When every active stage is complete it prints `all features complete for this mode.` (`cli/council_batch.py:177-179`). Before dispatching, it warns on stderr when more than half the scoped features carry enrichment artifacts but empty logs — the pre-v0.20 shape that would re-run and clobber curated docs (`cli/council_batch.py:27-51`).

### `council-log`

`dummyindex context council-log --feature ID --stage N --agent NAME --status STATUS [--note ...]` appends one audit entry (validated status / non-negative stage / agent name) to `features/<id>/council/_council-log.json` via `council.append_log` (`council.py:103-160`). The `council-log backfill [--feature ID]` subverb (`cli/council.py:77-142`) synthesises `complete` entries for stages whose council-authored artifacts already exist on disk but have no log records, so a pre-v0.20 index is not wrongly rescheduled from stage 1.

### `dev-pick`

The dev-stage picker resolves *which* stack-specialist authoring persona writes a feature's docs, deterministically and first-match-wins over a precedence table (`dev_pick.py:255-273`), from the feature's file list plus the repo's harvested dependency tokens. It always returns a persona (the constant-true fallback rule guarantees it), and supplies an ordered `fallbacks` ladder of alternative agents to try when the primary subagent isn't installed (`dev_pick.py:52-63`).

## Contracts

Council audit log (`context/domains/council.py`):
- `append_log(features_dir, *, feature_id, stage, agent, status, note=None, now=None) -> LogEntry` — `council.py:103-160`
- `read_log(features_dir, feature_id) -> list[LogEntry]` — `council.py:163-183`
- `is_stage_complete(features_dir, feature_id, stage) -> bool` — `council.py:186-203`
- `append_reset_marker(features_dir, feature_id, *, now=None) -> LogEntry` — `council.py:210-227`
- `is_standalone_complete(features_dir, feature_id) -> bool` — `council.py:230-248`
- `backfill_log_from_artifacts(features_dir, feature_id, *, now=None) -> tuple[int, ...]` — `council.py:251-292`
- `needs_artifact_backfill(features_dir, feature_id) -> bool` — `council.py:295-306`
- `latest_status(features_dir, feature_id, stage, agent) -> Optional[str]` — `council.py:334-346` (delegates to the shared `log_scan.last_matching` scan)
- `class LogEntry` (frozen: `timestamp, stage, agent, status, note`) + `to_dict()` — `council.py:85-100`
- `class CouncilLogError(ValueError)` — `council.py:81-82`

Shared resumption-scan helper (`context/domains/log_scan.py`):
- `last_matching(entries, predicate, attr="status") -> Optional[str]` — `log_scan.py:20-37` — pure, domain-neutral peer (no domain object) that returns `getattr(attr)` of the *last* entry satisfying `predicate`, or `None`. Both `council.latest_status` and `audit/log.latest_status` delegate to it, so the "keep the last entry matching a (key, agent) pair" semantics stay byte-identical across the two resumption logs. Lives top-level in `domains/` (not inside one domain) following the sanctioned `atomic_io.py` shared-domain-helper shape (`conventions/folder-organization.md:69-73`).

Batch frontier (`context/domains/council_batch.py`):
- `class CouncilStage(IntEnum)` — `SPECIFY=1, PLAN=2, CRITIQUE=3, FLOW=4, TREE=5` — `council_batch.py:31-38`
- `class CouncilMode(str, Enum)` — `LIGHT, STANDARD, DEEP` — `council_batch.py:41-46`
- `active_stages(mode, *, tree_enrich) -> tuple[CouncilStage, ...]` — `council_batch.py:64-77`
- `earliest_incomplete_stage(features_dir, feature_ids, *, mode, tree_enrich) -> Optional[CouncilStage]` — `council_batch.py:91-111`
- `force_recouncil(features_dir, feature_ids, *, mode, tree_enrich) -> tuple[str, ...]` — `council_batch.py:114-137`
- `next_batch(features_dir, repo_root, feature_ids, *, mode, cap, tree_enrich) -> Batch` — `council_batch.py:249-289`
- `class DispatchUnit` (frozen: `feature_id, stage, role, subagent_type, framework`) + `to_dict()` — `council_batch.py:166-183`
- `class Batch` (frozen: `complete, stage, units`) — `council_batch.py:186-192`
- `CRITIC_ROSTER: dict[CouncilMode, tuple[tuple[str, str], ...]]` — `council_batch.py:53-61`

Dev picker (`context/domains/dev_pick.py`):
- `pick_dev(*, feature_files, dep_tokens) -> DevPick` — `dev_pick.py:255-273`
- `harvest_dep_tokens(repo_root) -> frozenset[str]` — `dev_pick.py:306-325`
- `read_feature_files(features_dir, feature_id) -> tuple[str, ...]` — `dev_pick.py:328-337`
- `class DevPick` (frozen: `persona_id, subagent_type, framework, fallbacks`) + `to_dict()` — `dev_pick.py:102-120`
- `class SubagentType(str, Enum)` / `class PersonaId(str, Enum)` — `dev_pick.py:28-40`, `dev_pick.py:66-76`
- `class DevPickError(ValueError)` — `dev_pick.py:123-124`

Audit-debate log twin (`context/domains/audit/log.py`), ported from the council log:
- `append_log(workspace, *, round_num, persona, status, note=None, now=None) -> LogEntry` — `audit/log.py:61-118`
- `read_log(workspace) -> tuple[LogEntry, ...]` — `audit/log.py:121-141`
- `is_round_complete(workspace, round_num) -> bool` — `audit/log.py:144-157`
- `completed_rounds(workspace) -> tuple[int, ...]` — `audit/log.py:160-163`
- `class LogStatus(str, Enum)` (`started/complete/failed/skipped`) — `audit/enums.py:19-31`

## Examples

```bash
# Next parallel frontier for the standard-mode pipeline, machine-readable.
dummyindex context council-batch --next --json
# → {"complete": false, "stage": 1, "mode": "standard", "cap": 8,
#    "forced": [], "units": [{"feature_id":"auth","stage":1,"role":"dev",
#    "subagent_type":"Backend Architect","framework":"FastAPI"}, ...]}

# Record a dev stage-1 invocation's lifecycle.
dummyindex context council-log --feature auth --stage 1 --agent dev --status started
dummyindex context council-log --feature auth --stage 1 --agent dev --status complete

# Forced, scoped re-council of an already-complete feature.
dummyindex context council-batch --next --feature auth --force

# One-time fixup of a pre-v0.20 index before the first frontier call.
dummyindex context council-log backfill
```
