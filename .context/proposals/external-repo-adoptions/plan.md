# External-repo adoptions — plan

`status: planned` · companion to `spec.md`

Sequencing principle: **ship the deterministic test-truth artifact first** (everything else is
downstream), then the cheap S-effort hardening wins, then the gated PILOTs. Each item is an
independent PR with its own TDD cycle (RED → GREEN → review → full-suite gate). Items are not a
single mega-branch.

## Phase 0 — anchor (deliverable #1: build-loop test gate)

The only item specified to checklist depth here; see `spec.md` → "Deliverable #1".

1. **RED** — failing tests:
   - reporter writes normalized `.context/build/test.json` for pass / fail / collection-error fixtures;
   - `parse_test_state` + `test_gate` pure-function unit tests (red ⇒ block, green ⇒ allow, absent ⇒ fail-open);
   - schema contract test (locks the `test.json` shape);
   - end-to-end: a failing fixture flips the wave gate via the CLI runner.
2. **GREEN** —
   - `context/domains/build/test_state.py` (frozen dataclasses + `parse_test_state` + `test_gate`);
   - `pytest11` reporter plugin + `pyproject.toml` entry-point;
   - CLI runner step that invokes pytest **before** reading (closes "who runs pytest");
   - `cli/build_loop/waves.py:do_next_wave` conductor instruction on red suite.
3. **REVIEW** — `python-reviewer` vs `CONVENTIONS.md` (purity, frozen dataclasses, CLI-boundary I/O, file size).
4. **RECONCILE** — update `.context/features/build-loop/*`; `dummyindex context reconcile` → stamp.

## Phase 1 — cheap deterministic wins (S effort, parallelizable)

- **#2 provenance-in-frontmatter** — stamp repo/ref/tree-sha into vendored `SKILL.md`
  (`cli/equip/install.py` vendor write).
- **#3 anatomy lint gate** — deterministic frontmatter/section validator failing the
  vendor-install (`cli/equip/install.py` + `plugins/sources.py`).
- **#4 managed-region sentinels** — region-level doc-guard with fail-safe append
  (`cli/guard_doc_write.py` + `docguard/`). Includes the corrupted-fence survival test.

## Phase 2 — medium ADAPTs

- **#6 anatomy emission + Verification/Red-Flags** in `context/domains/equip/generate/`.
- **#5 opt-in fail-open PreToolUse test-gate hook** (`context/hooks.py`), gated behind Phase 0.
- **#7 fire-and-forget Stop-hook idiom** (shared hooks helper; precompute reconcile delta —
  NOT a detached `.context` writer).

## Phase 3 — gated PILOTs (falsifiable)

- **#8 doc↔code conflict detection** in `equip/generate/gaps.py`, scoped to vendored skills.
  *Pre-req:* verify Skill_Seekers' license. *Kill if:* prose skills expose no usable claimed-API.
- **#9 deterministic failure-miner** → `core-memories.md`. *Pre-req:* Phase 1 #4.
  *Kill if:* no useful signal without an LLM analyzer.

## Out of scope (SKIP)

LLM-judge hard block; per-language reporter "marketplace"; cowork AST-author; skilluse.dev;
karpathy-skills; aiwithremy-council (no-license byte-identical dup). Rationale in `spec.md`.

## Tracking

- Council source-of-truth: memory `dummyindex-repo-adoption-verdict.md`.
- Convention: planning docs live here under `.context/proposals/` (managed-doc-homes); never
  user-facing `docs/`.
