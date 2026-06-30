# Auto-equip skills — plan

`status: planned`

## Bounded context

Extends the existing `equip` feature; touches `build-loop` (the missing-capability
signal) and the `plan`/`build` skills (prose orchestration). Honors equip's hard
rules verbatim: **pure policy in `context/domains/equip/`, every read/write at the
`cli/equip/` boundary, hash-baselined never-clobber, trust-tier + blast-radius
gate, `sources.py` the one isolated impure leaf.** Nothing here weakens a gate;
it *reaches* code that already exists (`vendored_item`, `build_install_plan`'s
VENDOR branch, `is_safe_to_write`) but had no caller.

## Architecture in three sentences

A new pure `generate/gaps.py` computes `required(stack,proposal) − covered(manifest)`
so discovery and planning act on a real capability gap instead of a 2-tag stub.
The `cli/equip/discover.py` wire layer stops skipping collection seeds and adds the
documented-but-missing `pi.mechanism is VENDOR` branch to `run_install`, which
fetches a `SKILL.md` at a **pinned commit sha** (`sources.resolve_ref`), stamps it
(`stamp_vendored`), writes it under `is_safe_to_write`, and records a VENDORED item
(`vendored_item` → new `_record_vendored`). The build loop emits a structured
missing-capability signal and the plan/build skills run the gated
discover→approve→vendor loop — discovery automatic, every install user-approved.

## Where it lives

- **Policy (pure):** `context/domains/equip/generate/gaps.py` (new); a `SkillRef`
  frozen model in `plugins/sources.py` (or `models.py` if it must be shared).
- **Impure leaf:** `context/domains/equip/plugins/sources.py` — `resolve_ref`,
  `list_skills`, `ref=` on `fetch_file`. Still the only shell-out module.
- **Wire:** `cli/equip/discover.py` (`_needed_caps` rewrite, `_collect_catalogs`
  collection admit, `run_install` VENDOR branch, `_record_vendored`).
- **Build loop:** `cli/build_loop/waves.py` (`map_task_to_equipment` /
  `_entry_for` missing-capability signal; `_dispatchable` unchanged — vendored
  skills surface via `— via <tool>` annotation, not the agent dispatch pool).
- **Skills/docs:** `dummyindex/skills/plan/SKILL.md`, `dummyindex/skills/build/SKILL.md`,
  `dummyindex/skills/equip/SKILL.md`; `.context/features/equip/{spec,plan,concerns}.md`.

## Key decisions (decided X because Y)

- **Decided the gap analysis is pure and stack-derived** (no LLM in the policy
  core) because `apply`/`discover` must stay reproducible; the LLM only
  orchestrates approval. Mirrors the existing wire-only/pure split
  (`adopt.py:resolve_coverage`).
- **Decided to pin `origin_ref` to a resolved commit sha at vendor time** because
  a moving-HEAD fetch is both a supply-chain hazard and a determinism hazard —
  the same `install` could yield different bytes over time. This directly answers
  the Security HIGH at `.context/features/equip/concerns.md:13` (`origin_ref=None`
  / moving HEAD) for the vendor path, and makes `refresh` an explicit diffable
  bump.
- **Decided to reuse the existing trust gate unchanged** (`install_plan.py:43
  requires_approval = not candidate.trusted`) so vendored skills inherit the same
  `--yes` + usage-doc gating for free — "installation is never silent" holds
  (`plan-plugin-annotation`, `equip-plugin-usage-interview`).
- **Decided vendored skills are NOT added to the agent dispatch pool**
  (`waves.py:_dispatchable`) because a skill is consumed via its tool annotation,
  not dispatched as a subagent — keeping the agent-only dispatch contract intact.
- **Decided to add an integration test that drives `run_install` end-to-end to a
  file on disk** because today's green vendor tests exercise only the pure helpers
  and *mask* the unwired path (`test_equip_install_plan.py:52-54`,
  `test_equip_vendor.py`).

## Dependencies & risks

- Upstream consumed read-only: `detect_stack`, `read_manifest`,
  `extract_proposal_capabilities`. Impure boundary: `gh api` via the `Runner`
  seam (fake-runner tested; never raises on non-zero).
- **Security:** vendored content is executable instruction text. Mitigation:
  pinned ref + trust gate + mandatory usage-doc + per-skill user approval; never
  auto-write trusted-but-unreviewed content silently (policy: discovery auto,
  install gated).
- **Interaction:** sits on the two equip open questions and *resolves* them
  rather than adding debt. Must not disturb the separate, hardcoded
  `superpowers-default-wiring` path.
- **Schema:** no `equipment.json` schema bump needed — `EquipmentSource.VENDORED`,
  `InstallMechanism.VENDOR`, and the `origin_*` fields already exist (SCHEMA v4).

## Wave map

1. Pure gap core + rewire `_needed_caps`.
2. `sources.py` pinned-ref enumeration/fetch.
3. `run_install` VENDOR branch + `_record_vendored` + collection admit.
4. Lifecycle parity tests + build-loop signal + plan/build/equip SKILL.md.
5. `.context/features/equip/*` reconcile + full-suite acceptance GATE.

See `checklist.md` for the task-level breakdown.
