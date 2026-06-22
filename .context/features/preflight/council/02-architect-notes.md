# Architect notes — preflight (stage 2)

## What I changed

- Replaced the loose "Where it lives" + "Architecture in three sentences" prose with a **Bounded context** section that states the single question the domain answers and its three owned probes, then a tight file ownership map (one bullet per module at path:range). Cut the inline equip-caller list out of "Where it lives" — it belongs under Dependencies.
- Extracted the implicit architecture into an explicit **Patterns named** section: single-pass fan-out to private inspectors, report-as-pure-data with rendering/JSON as projections, tri-state collapse, lock-step imported markers, never-raises probing — each anchored at a verified path:range and, where relevant, tied to the repo conventions (`coding-practices.md`, `data-access.md`).
- Split the old single "Key decisions" blob into **Patterns named** (mechanism) vs **Decisions promoted** (each rewritten as "X because Y").
- Promoted **Dependencies** into its own section with explicit Consumes / Consumed-by, including the equip/adopt symbols and the skill Phase 0 contract.
- Trimmed the data-model section (dropped the redundant tri-state restatement, now covered as a named pattern).
- Demoted the doc-rot bullet (broken `docs.md` refs) out of Open questions — it was inventory noise, not an architectural question — and kept only the two genuine design questions (glob asymmetry, hook-collision visibility).

## Patterns named

- Single read-only pass, fan-out to four private inspectors — `inventory.py:28-62` (inspectors at `:77`, `:140`, `:155`, `:162`).
- Report-as-pure-data; markdown + JSON are side-effect-free projections — `render.py:27-65`, `models.py:23-29,48-60`.
- Tri-state collapse of the ownership enum (`_owned_flag`) and `git_clean: Optional[bool]` — `inventory.py:65-74,169-194`.
- Lock-step markers imported, never re-spelled — `inventory.py:17-19`, `ownership.py:1-7`.
- Tolerant, never-raises probing — `ownership.py:34-53,64-70`, `inventory.py:103-137,190-194`.

All path:range citations re-verified against source and `.context/map/symbols.json` before promoting them.

## Dependencies surfaced

- Consumes: `context.hooks` (`SENTINEL`, `CURRENT_CLAUDE_EVENTS`), `context.output.bootstrap` (`BEGIN_MARKER`), `pipeline.io` (`is_git_repo`) — `inventory.py:17-19`.
- Consumed by equip/adopt — `resolve_coverage` / `adopt_existing` read `preflight.project_agents` (`adopt.py:31,81-159`); equip CLI callers `cli/equip/common.py:203-206`, `cli/equip/dispatch.py:68,278-286`.
- Consumed by the `/dummyindex` skill Phase 0 — `SKILL.md:21,110-138`; preflight reports, never blocks.

## Decisions promoted

- Read-only/additive **because** the promise is "show before touch"; `.context/` fields defaulted **because** back-compat constructions must keep working (`inventory.py:1-7`, `models.py:33-46`).
- Never-raises **because** a crashing preflight can't preflight (`ownership.py:64-70`, `inventory.py:103-137,190-194`).
- Newer-schema tolerance **because** a newer-written `.context/` is still ours; avoids strict `read_meta` (`ownership.py:9-15`).
- Legacy-sentinel scrub **because** a stale sentinel must not suppress a fresh install (`inventory.py:121-137`).
- `GIT_OPTIONAL_LOCKS=0` **because** a killed hook must not strand `index.lock` (`inventory.py:169-194`).
