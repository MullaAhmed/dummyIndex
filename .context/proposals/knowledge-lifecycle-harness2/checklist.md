# Checklist — Knowledge lifecycle: lesson records, doc budget, reusable specialists, citation guard

## Wave 1 — new standalone modules (disjoint files)
- [x] Lesson package and tests (dummyindex/context/domains/lesson/, tests/context/domains/test_lesson.py)
- [x] Doc budget package and tests (dummyindex/context/domains/docbudget/, tests/context/domains/docbudget/test_ratchet.py)
- [x] Citation helper and tests (dummyindex/context/domains/docguard/citations.py, tests/context/domains/docguard/test_citations.py)
- [x] Checklist live-step lint and tests (dummyindex/context/domains/buildloop/checklist_lint.py, tests/context/domains/test_checklist_lint.py)
- [x] Specialist library and tests (dummyindex/context/domains/equip/lifecycle/library.py, tests/context/domains/equip/test_equip_library.py)

## Wave 2 — wire into existing code (disjoint files)
- [x] Wire learning: required lesson, persisted status, retry, legacy path, shared DISPOSABLE_REF (dummyindex/context/domains/evolve_learning.py, dummyindex/context/domains/proposals/closeout.py, dummyindex/context/domains/proposals/retirement.py, tests/context/domains/test_evolve_learning.py, tests/context/domains/test_closeout.py)
- [x] Write-time citation guard for Write, Edit, MultiEdit (dummyindex/cli/guard_doc_write.py, dummyindex/context/hooks.py, tests/cli/test_guard_doc_write.py)
- [x] check --budget and --refs verbs (dummyindex/cli/check.py, tests/cli/test_check_budget.py, tests/cli/test_check_refs.py)
- [x] Refuse live items in waves; scaffold states the rule (dummyindex/cli/build_loop/waves.py, dummyindex/context/domains/proposals/store.py, tests/context/domains/test_propose.py, tests/context/domains/test_build_loop.py)
- [x] Specialist dimensions and four new capability templates (dummyindex/context/domains/equip/generate/specialists.py, dummyindex/skills/equip/templates/, pyproject.toml, tests/context/domains/equip/test_equip_specialists.py, tests/context/domains/equip/test_equip_specialist_invariants.py, tests/context/domains/equip/test_equip_apply_merge.py)
- [x] Remove stale proposal citation (dummyindex/context/domains/memory/miner/__init__.py)

## Wave 3 — CLI surfaces, skill text, docs
- [x] Print learning status, exit 1 only on failed (dummyindex/cli/gc.py, dummyindex/cli/build_loop/dispatch.py, dummyindex/cli/evolve.py, tests/cli/test_closeout_exit_codes.py)
- [x] Equip CLI stores and reuses library specialists (dummyindex/cli/equip/dispatch.py, tests/cli/equip/test_equip_reuse.py)
- [x] Skill text edits, net word count not growing, budget check in own gate (dummyindex/skills/skill.md, dummyindex/skills/plan/SKILL.md, dummyindex/skills/audit/SKILL.md, dummyindex/skills/audit/closeout.md, dummyindex/skills/equip/SKILL.md)
- [x] Closeout guide for lesson record and statuses (docs/guide/closeout.md)

## Wave 4 — ratchet + acceptance
- [x] Write ratchet files and extend skills hygiene test (tests/data/skill-budget.txt, .context/doc-budget.txt, tests/test_skills_doc_hygiene.py)
- [x] Acceptance: every spec Acceptance criterion has its named passing test and `python -m pytest tests/ -q` passes
