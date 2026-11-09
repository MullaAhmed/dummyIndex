# Plan — Knowledge lifecycle: lesson records, doc budget, reusable specialists, citation guard

Reuse: `living_rules.plan_rule/rules_in`, `evolve_learning.prepare_learning/finish_learning/enqueue_learning`,
`proposals/retirement.DISPOSABLE_REF/durable_references`, `docguard/classify` (path-only, stays pure),
`buildloop/checklist.parse_checklist`, `equip/generate/specialists.SpecialistTemplate/specialist_spec`,
`equip/lifecycle/hashing.py`, `equip/identity.py`, `domains/config.py` (untouched).
Tests live flat under `tests/context/domains/` and `tests/cli/` per existing layout.

## Dependency order

Tasks 1–5 independent. 6–11 need 1–5. 12–15 need 6–11. 16 needs 12–15.

## Tasks

1. **Lesson package.** New `dummyindex/context/domains/lesson/{__init__,models,enums}.py`: `Lesson`, `Verdict`, `Confidence`, `validate_lesson`, `lesson_to_delta` (returns `plan_rule` kwargs; no merge code). Test `tests/context/domains/test_lesson.py`.
2. **Doc budget package.** New `dummyindex/context/domains/docbudget/{__init__,models,constants,ratchet}.py`: `measure`, `read_ratchet`, `check`, `update_ratchet` (lower only). Test `tests/context/domains/docbudget/test_ratchet.py`.
3. **Citation helper.** New `dummyindex/context/domains/docguard/citations.py`: `DISPOSABLE_REF`, `cites_disposable`, `added_citations(old, new)`, `scan_durable(root)`; imports nothing from `proposals/` (avoids a cycle). Test `tests/context/domains/docguard/test_citations.py`.
4. **Checklist lint.** New `dummyindex/context/domains/buildloop/checklist_lint.py`: `live_items(items)` with the pinned regex, `live-ok` escape, ticked grandfathering. Test `tests/context/domains/test_checklist_lint.py`.
5. **Specialist library.** New `dummyindex/context/domains/equip/lifecycle/library.py`: `store`, `reuse`, `reverify` over `hashing.py`/`identity.py`. Test `tests/context/domains/equip/test_equip_library.py`.
6. **Wire learning.** Edit `dummyindex/context/domains/evolve_learning.py` (call `validate_lesson`, `lesson_to_delta`, persist status in the event file, legacy-shape path) and `dummyindex/context/domains/proposals/closeout.py` (replace in-memory `unavailable`, write `.context/gc/learning/<kind>-<slug>.failed.json` on pre-event failure, retry on re-run, injectable learner parameter, import `DISPOSABLE_REF` from `docguard/citations.py`) and `dummyindex/context/domains/proposals/retirement.py` (same re-import). Tests `tests/context/domains/test_evolve_learning.py`, `tests/context/domains/test_closeout.py`.
7. **Write guard.** Edit `dummyindex/cli/guard_doc_write.py` (read content/`new_string`/`edits[]`, scope rules, 1 MB cap, fail-open) and `dummyindex/context/hooks.py` (matcher `Write|Edit|MultiEdit`, install rewrites the matcher). Test `tests/cli/test_guard_doc_write.py`.
8. **Check verbs.** Edit `dummyindex/cli/check.py`: `--budget [--update-ratchet]`, `--refs`, wire-only. Tests `tests/cli/test_check_budget.py`, `tests/cli/test_check_refs.py`.
9. **Checklist rule.** Edit `dummyindex/cli/build_loop/waves.py` (refuse + list via task 4) and `dummyindex/context/domains/proposals/store.py` (`_checklist_template` states the rule). Tests `tests/context/domains/test_propose.py`, `tests/context/domains/test_build_loop.py` (adds the pin for unchanged moved-live-item closeout handling).
10. **Specialist templates.** Edit `dummyindex/context/domains/equip/generate/specialists.py` (`dimension`, frontend/api/migration/ci entries, invariants), add `dummyindex/skills/equip/templates/{frontend,api,migration,ci}-{procedure,domain}-agent.md.tmpl`, confirm `pyproject.toml` package-data covers them. Tests `tests/context/domains/equip/test_equip_specialists.py`, `test_equip_specialist_invariants.py`, `test_equip_apply_merge.py`.
11. **Stale citation.** Edit `dummyindex/context/domains/memory/miner/__init__.py` docstring.
12. **Exit codes + printing.** Edit `dummyindex/cli/gc.py` (`_gc_closeout` only), `dummyindex/cli/build_loop/dispatch.py`, `dummyindex/cli/evolve.py` (`_evolve_learning`): print status, exit 1 only on `failed`. Test `tests/cli/test_closeout_exit_codes.py`.
13. **Equip CLI.** Edit `dummyindex/cli/equip/dispatch.py`: store adopted specialists in the library on apply/patch; new `reuse <capability_id> [--force]`. Tests `tests/cli/equip/test_equip_reuse.py`.
14. **Skill text, net-zero words.** Edit `dummyindex/skills/skill.md` (placement rule), `dummyindex/skills/plan/SKILL.md` (no live-testing items, no proposal/audit citations), `dummyindex/skills/audit/SKILL.md` + `closeout.md` (lesson record, statuses), `dummyindex/skills/equip/SKILL.md` (library, dimensions). Named cuts that pay for the additions: compress the "Generated vs adopted" section in `skills/equip/SKILL.md` and audit `SKILL.md` steps 5–6 prose. Run `check --budget` in this item's own gate.
15. **Closeout doc.** Edit `docs/guide/closeout.md` (lesson record, statuses).
16. **Ratchet + hygiene.** Write `tests/data/skill-budget.txt` and `.context/doc-budget.txt` via `--update-ratchet`; extend `tests/test_skills_doc_hygiene.py` for the ratchet and heading checks.
