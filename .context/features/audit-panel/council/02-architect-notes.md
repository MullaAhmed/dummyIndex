# Architect notes — audit-panel (stage 2)

## What I changed
- Replaced the vague "Where it lives / Architecture in three sentences" framing with an explicit **Bounded context** section up top that names the two-context split and the exact two-fact seam (shared enum alphabet + model/mode fallback) joining them.
- Renamed the architecture section to **the plumbing-vs-orchestration boundary** and made the boundary the single load-bearing decision: enumerated what sits *below the line* (Python plumbing) vs *above the line* (the `/dummyindex-audit` skill), and named the crossing point as `resolve_catalog` (`catalog.py:159-187`), with the debate-log as the only state flowing back down.
- Added a dedicated **Dependencies** section surfacing upstream (config→audit, install→config), downstream (skill, non-audit config consumers), lateral (audit→equip), and an explicit **no-cycles / DAG** statement.
- Tightened `Where it lives` to carry def-line anchors verified against `map/symbols.json`.
- Promoted two decisions and cut filler (dropped the "three sentences" gimmick; folded the model-asymmetry rationale into the never-default decision).
- Sharpened the Open question into an actionable architect recommendation to split config into its own feature.

## Patterns named (path:range)
- Plumbing/orchestration boundary contract: `workspace.py:1-13`, `catalog.py:5-9`, `log.py:10-13`.
- Boundary crossing point: `resolve_catalog` (`catalog.py:159-187`).
- Shared enum kernel: `config.py:42-64` ← `enums.py:1-8`, `workspace.py:23`.
- Model/mode fallback seam: `resolve_model`/`resolve_mode` (`workspace.py:85-128`).
- Atomic byte-stable persistence: `write_text_atomic` per `.context/conventions/data-access.md`; `models.py:36-45`.
- Marketplace-plugin roster guard: `catalog.py:133-138`.
- Evidence-gated roster identity: `catalog.py:111-118`, `171-172`.

## Dependencies surfaced
- Upstream: `config.read_config` (`config.py:197`) feeds `resolve_model`/`resolve_mode`; `_write_default_config` (`install.py:326`) seeds the fallback.
- Downstream: `/dummyindex-audit` skill consumes `catalog.json`/`audit.json`, writes back only via `append_log`.
- Lateral: `collect_roster` reads `equipment.json` (`catalog.py:133-138`).
- Cycles: none — DAG `install → config ← audit ← skill`, with `audit → equip` lateral. Config is a sink-leaning shared kernel.

## Decisions promoted
- "Deterministic plumbing; orchestrator drives the panel" elevated to the feature's defining constraint.
- "Config is a shared kernel, not an audit member" promoted from buried Open-question aside to a Key decision, with the `--defaults` CI path (`config.py:182-194`) and multi-consumer read surface as evidence.
- Model-vs-mode never-default asymmetry promoted with its rationale (expensive/unrecoverable model vs cheap mode).

## Open-questions verdict
Confirmed the Leiden community fuses **two distinct concerns**. Audit + onboarding/config share only a vocabulary and a fallback, not a responsibility; config's blast radius (council, equip, drift hook) exceeds audit. Recommended split: promote config/onboarding to its own platform-kernel feature doc, audit-panel cites it as an upstream dependency.
